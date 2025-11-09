import json
import sqlite3
import os
import time
import requests
import re
import math
import psycopg2 # <-- NOUVEAU "TRADUCTEUR"
from urllib.parse import urlparse # <-- Outil pour lire l'URL de la BDD

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

# --- 1. Configuration ---
app = Flask(__name__)
CORS(app)

# --- CONFIGURATION DE L'IA (REST API) ---
API_KEY = os.environ.get("GEMINI_API_KEY") 
if not API_KEY:
    print("ERREUR FATALE : GEMINI_API_KEY n'est pas définie.")
IA_MODEL_NAME = "gemini-pro-latest" 
IA_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{IA_MODEL_NAME}:generateContent?key={API_KEY}"
print(f"Configuration IA : Prêt à appeler {IA_MODEL_NAME} via v1beta.")
IA_COOLDOWN_SECONDS = 31
LAST_IA_CALL_TIME = 0

# --- NOUVELLE CONFIGURATION BDD POSTGRESQL ---
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("ERREUR FATALE : DATABASE_URL n'est pas définie.")

def get_db_connection():
    """Ouvre une nouvelle connexion à la BDD PostgreSQL."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn
# --- FIN NOUVELLE CONFIG BDD ---


# --- 2. Initialisation BDD (Mise à jour pour PostgreSQL) ---
def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # On utilise SERIAL PRIMARY KEY au lieu de INTEGER...
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS regles_utilisateurs (
            id SERIAL PRIMARY KEY,
            mot_cle TEXT NOT NULL UNIQUE,
            libelle_nettoye TEXT NOT NULL,
            categorie TEXT NOT NULL,
            sous_categorie TEXT NOT NULL
        )
        """)
        conn.commit()
        cursor.close()
        conn.close()
        print("Base de données PostgreSQL 'regles_utilisateurs' initialisée.")
    except Exception as e:
        print(f"ERREUR LORS DE L'INIT DB: {e}")

# --- CORRECTION : ON APPELLE LA FONCTION ! ---
# On s'assure que la table est créée au démarrage du serveur.
init_db()
# --- FIN CORRECTION ---
    

# --- 3. Logique Métier ---

REGLES_DE_CATEGORISATION = {
    'NETFLIX': ('Netflix', 'Abonnements', 'Streaming'),
    'LOYER': ('Loyer', 'Charges Fixes', 'Logement'),
    'CARREFOUR': ('Courses (Carrefour)', 'Alimentation', 'Supermarché'),
    'SALAIRE': ('Salaire', 'Revenus', 'Salaire'),
    'PAUL': ('Boulangerie Paul', 'Alimentation', 'Boulangerie'),
    'AXA': ('Assurance AXA', 'Charges Fixes', 'Assurances'),
    'RESTAURANT': ('Restaurant', 'Sorties', 'Restaurant'),
    'AMAZON': ('Amazon', 'Shopping', 'En ligne'),
}

# --- SAUVEGARDE BDD (Mise à jour pour PostgreSQL) ---
def sauvegarder_regle_en_bdd(mot_cle, libelle_nettoye, categorie, sous_categorie):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # "ON CONFLICT (mot_cle) DO NOTHING" est l'équivalent de "INSERT OR IGNORE"
        cursor.execute("""
        INSERT INTO regles_utilisateurs (mot_cle, libelle_nettoye, categorie, sous_categorie)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (mot_cle) DO NOTHING
        """, (mot_cle.upper(), libelle_nettoye, categorie, sous_categorie))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"--- 🧠 Règle sauvegardée (PostgreSQL) : {mot_cle.upper()} -> {categorie} ---")
        return True
    except Exception as e:
        print(f"Erreur de BDD (PostgreSQL) lors de la sauvegarde : {e}")
        return False
# --- FIN SAUVEGARDE BDD ---

def extraire_json_de_reponse(texte_brut):
    match = re.search(r'\{.*\}', texte_brut, re.DOTALL)
    if match:
        try: return json.loads(match.group(0))
        except json.JSONDecodeError: return None
    return None

# --- CORRECTION : LE PROMPT COMPLET EST DE RETOUR ---
def appel_llm_ia(transaction):
    global LAST_IA_CALL_TIME
    
    current_time = time.time()
    time_since_last_call = current_time - LAST_IA_CALL_TIME
    if time_since_last_call < IA_COOLDOWN_SECONDS:
        wait_time = IA_COOLDOWN_SECONDS - time_since_last_call
        print(f"--- ⚠️ RESPECT DU RATE LIMIT --- En attente de {round(wait_time, 1)}s...")
        time.sleep(wait_time)
    
    print(f"--- 🧠 Appel au VRAI LLM (via REST API) pour : '{transaction['libelle']}' ---")
    LAST_IA_CALL_TIME = time.time()
    
    categories_valides = [
        "Charges Fixes", "Alimentation", "Abonnements", "Sorties",
        "Shopping", "Santé", "Transport", "Épargne", "Autres"
    ]
    
    # Le prompt complet et strict
    prompt = f"""
    Tu es un expert en finances personnelles.
    Analyse la transaction : "{transaction['libelle']}"
    
    Tâches :
    1.  Propose un "libelle_nettoye" clair (ex: "Achat Fnac").
    2.  Choisis la "categorie" la plus pertinente parmi cette liste : {json.dumps(categories_valides)}
    
    RÈGLES CRITIQUES :
    -   Si tu ne peux pas deviner, utilise la catégorie "A_VERIFIER".
    -   Ta réponse DOIT commencer par {{" et finir par }}".
    -   Ne réponds RIEN d'autre. Pas de "Absolument", pas de "Voici", pas de markdown (trois accents graves).
    -   SEULEMENT l'objet JSON.
    """
    
    request_body = { "contents": [ { "parts": [ {"text": prompt} ] } ] }
    
    try:
        response = requests.post(IA_API_URL, json=request_body, headers={'Content-Type': 'application/json'})
        if response.status_code != 200:
            raise Exception(f"Erreur API {response.status_code}: {response.text}")
            
        reponse_brute_ia = response.json()['candidates'][0]['content']['parts'][0]['text']
        print(f"Réponse brute de l'IA : {reponse_brute_ia}")

        resultat = extraire_json_de_reponse(reponse_brute_ia)
        if resultat is None:
            raise Exception("Impossible d'extraire le JSON de la réponse de l'IA.")

        if resultat.get('categorie') not in categories_valides and resultat.get('categorie') != 'A_VERIFIER':
            print(f"Alerte : L'IA a proposé '{resultat.get('categorie')}', qui n'est pas valide. On force 'A_VERIFIER'.")
            resultat['categorie'] = 'A_VERIFIER'
            
        return {
            'libelle_nettoye': resultat.get('libelle_nettoye', transaction['libelle']),
            'categorie': resultat.get('categorie', 'A_VERIFIER'),
            'sous_categorie': "Analysé par IA"
        }
        
    except Exception as e:
        print(f"--- ERREUR lors de l'appel à l'IA (Requests) : {e} ---")
        return {'libelle_nettoye': transaction['libelle'], 'categorie': 'A_VERIFIER', 'sous_categorie': 'Erreur IA'}
# --- FIN DE LA FONCTION IA CORRIGÉE ---


# --- CLASSIFIER (Mise à jour pour PostgreSQL) ---
def classifier_transaction(transaction, regles_de_base):
    libelle_brut_upper = transaction['libelle'].upper()
    
    # NIVEAU 1 : Base de Données (PostgreSQL)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT mot_cle, libelle_nettoye, categorie, sous_categorie FROM regles_utilisateurs")
    regles_apprises = cursor.fetchall() # Récupère toutes les règles
    cursor.close()
    conn.close()

    for row in regles_apprises:
        mot_cle_db, libelle_nettoye, categorie, sous_categorie = row
        if mot_cle_db in libelle_brut_upper:
            return {**transaction, 'libelle_nettoye': libelle_nettoye, 'categorie': categorie, 'sous_categorie': sous_categorie, 'methode': 'Regle (Apprise)'}

    # NIVEAU 2 : Règles de Base (inchangé)
    for mot_cle_base, (libelle_nettoye, categorie, sous_categorie) in regles_de_base.items():
        if mot_cle_base in libelle_brut_upper:
            return {**transaction, 'libelle_nettoye': libelle_nettoye, 'categorie': categorie, 'sous_categorie': sous_categorie, 'methode': 'Regle (Base)'}
            
    # NIVEAU 3 : Moteur LLM (inchangé)
    resultat_llm = appel_llm_ia(transaction)
    
    if resultat_llm['categorie'] != 'A_VERIFIER':
        print(f"--- 🤖 APPRENTISSAGE AUTOMATIQUE ---")
        sauvegarder_regle_en_bdd(
            mot_cle=libelle_brut_upper,
            libelle_nettoye=resultat_llm['libelle_nettoye'],
            categorie=resultat_llm['categorie'],
            sous_categorie="Analysé par IA"
        )
        resultat_llm['methode'] = 'IA (Auto-Appris)'
    else:
        resultat_llm['methode'] = 'IA (A Vérifier)'

    return {
        **transaction,
        'libelle_nettoye': resultat_llm['libelle_nettoye'],
        'categorie': resultat_llm['categorie'],
        'sous_categorie': resultat_llm['sous_categorie'],
        'methode': resultat_llm['methode']
    }
# --- FIN CLASSIFIER ---

# --- 4. Routes de l'API (Toutes inchangées) ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/categorize', methods=['POST'])
def api_categorize():
    transaction_brute = request.json
    transaction_nettoyee = classifier_transaction(transaction_brute, REGLES_DE_CATEGORISATION)
    return jsonify(transaction_nettoyee)

@app.route('/api/create_budget', methods=['POST'])
def api_create_budget():
    data = request.json; transactions = data.get('transactions', []); objectif_epargne = data.get('objectif', 0)
    revenus = 0; charges_fixes = 0; depenses_variables_observees = {}; total_depenses_variables = 0
    for tx in transactions:
        categorie = tx.get('categorie'); montant = tx.get('montant', 0)
        if categorie == 'Revenus': revenus += montant
        elif categorie == 'Charges Fixes': charges_fixes += montant
        elif categorie not in ['A_VERIFIER', 'Revenus', 'Charges Fixes'] and montant < 0:
            if categorie not in depenses_variables_observees: depenses_variables_observees[categorie] = 0
            depenses_variables_observees[categorie] += montant
            total_depenses_variables += montant
    charges_fixes_abs = round(abs(charges_fixes), 2); revenus_observes = round(revenus, 2)
    total_depenses_variables_abs = round(abs(total_depenses_variables), 2)
    budget_variable_total_disponible = revenus_observes - charges_fixes_abs - objectif_epargne
    enveloppes_proposees = []
    if total_depenses_variables_abs > 0:
        for categorie, total_depense in depenses_variables_observees.items():
            pourcentage = abs(total_depense) / total_depenses_variables_abs
            montant_propose = budget_variable_total_disponible * pourcentage
            montant_propose_arrondi = math.floor(montant_propose / 5) * 5
            enveloppes_proposees.append({'categorie': categorie, 'depense_observee': round(abs(total_depense), 2), 'enveloppe_proposee': montant_propose_arrondi})
    total_alloue_enveloppes = sum(env['enveloppe_proposee'] for env in enveloppes_proposees)
    bonus_non_alloue = budget_variable_total_disponible - total_alloue_enveloppes
    if bonus_non_alloue > 0:
        enveloppes_proposees.append({'categorie': 'Bonus (Non Alloué)', 'depense_observee': 0, 'enveloppe_proposee': round(bonus_non_alloue, 2)})
    reste_a_vivre_total = budget_variable_total_disponible
    reste_a_vivre_jour = reste_a_vivre_total / 30
    message_ia = f"OK Julien ! Pour atteindre votre objectif de {objectif_epargne}€ d'épargne (sur {revenus_observes}€ de revenus), il nous reste {reste_a_vivre_total}€ à répartir. Je vous propose les enveloppes suivantes :"
    reponse_coach = { 'revenus_observes': revenus_observes, 'fixes_observes': charges_fixes_abs, 'enveloppes_proposees': enveloppes_proposees, 'message_ia': message_ia, 'reste_a_vivre_total': round(reste_a_vivre_total, 2), 'reste_a_vivre_jour': round(reste_a_vivre_jour, 2) }
    return jsonify(reponse_coach)

@app.route('/api/learn_rule', methods=['POST'])
def api_learn_rule():
    data = request.json; mot_cle = data.get('mot_cle'); categorie = data.get('categorie')
    if not mot_cle or not categorie:
        return jsonify({'status': 'erreur', 'message': 'Données manquantes'}), 400
    success = sauvegarder_regle_en_bdd(mot_cle=mot_cle, libelle_nettoye=mot_cle.capitalize(), categorie=categorie, sous_categorie="Validé (Utilisateur)")
    if success:
        return jsonify({'status': 'ok', 'message': f"Règle '{mot_cle.upper()}' sauvegardée."})
    else:
        return jsonify({'status': 'erreur', 'message': 'Erreur BDD'}), 500

# --- 5. Lancement (On n'a plus besoin du 'if __name__ ...') ---
# Gunicorn va juste importer le fichier et trouver l'objet 'app'.
# L'appel à init_db() est maintenant à la ligne 61.