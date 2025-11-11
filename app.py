import json
import sqlite3
import os
import time
import requests
import re
import math
import psycopg2
from urllib.parse import urlparse
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from flask_bcrypt import Bcrypt # <-- NOUVEAU
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required, JWTManager # <-- NOUVEAU

load_dotenv() 

# --- 1. Configuration ---
app = Flask(__name__)
CORS(app)

# --- CONFIGURATION DE LA SÉCURITÉ ---
# Change cette clé ! Ce peut être n'importe quelle chaîne secrète
app.config["JWT_SECRET_KEY"] = "ton-super-secret-jwt-change-moi" 
bcrypt = Bcrypt(app)
jwt = JWTManager(app)
# --- FIN SÉCURITÉ ---

# --- CONFIGURATION IA (inchangée) ---
API_KEY = os.environ.get("GEMINI_API_KEY") 
if not API_KEY:
    print("ERREUR FATALE : GEMINI_API_KEY n'est pas définie.")
IA_MODEL_NAME = "gemini-pro-latest" 
IA_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{IA_MODEL_NAME}:generateContent?key={API_KEY}"
print(f"Configuration IA : Prêt à appeler {IA_MODEL_NAME} via v1beta.")
IA_COOLDOWN_SECONDS = 31
LAST_IA_CALL_TIME = 0

# --- CONFIGURATION BDD (inchangée) ---
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("ERREUR FATALE : DATABASE_URL n'est pas définie.")

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# --- 2. Initialisation BDD (MISE À JOUR MAJEURE) ---
def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Table des Utilisateurs
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS utilisateurs (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
        """)
        
        # 2. Table des Règles Générales (le savoir collectif)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS regles_generales (
            id SERIAL PRIMARY KEY,
            mot_cle TEXT NOT NULL UNIQUE,
            libelle_nettoye TEXT NOT NULL,
            categorie TEXT NOT NULL,
            sous_categorie TEXT NOT NULL
        )
        """)
        
        # 3. Table des Règles Personnelles (le "veto" de l'utilisateur)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS regles_personnelles (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            mot_cle TEXT NOT NULL,
            libelle_nettoye TEXT NOT NULL,
            categorie TEXT NOT NULL,
            sous_categorie TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES utilisateurs (id),
            UNIQUE (user_id, mot_cle) -- Un utilisateur ne peut avoir qu'une règle par mot-clé
        )
        """)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Base de données PostgreSQL (3 tables) initialisée.")
    except Exception as e:
        print(f"ERREUR LORS DE L'INIT DB: {e}")

# --- NOUVEAU : On "remplit" la BDD avec nos règles de base ---
def seed_database():
    """Remplit la table regles_generales avec nos règles de base si elle est vide."""
    base_rules = {
        'NETFLIX': ('Netflix', 'Abonnements', 'Streaming'),
        'LOYER': ('Loyer', 'Charges Fixes', 'Logement'),
        'CARREFOUR': ('Courses (Carrefour)', 'Alimentation', 'Supermarché'),
        'SALAIRE': ('Salaire', 'Revenus', 'Salaire'),
        'PAUL': ('Boulangerie Paul', 'Alimentation', 'Boulangerie'),
        'AXA': ('Assurance AXA', 'Charges Fixes', 'Assurances'),
        'RESTAURANT': ('Restaurant', 'Sorties', 'Restaurant'),
        'AMAZON': ('Amazon', 'Shopping', 'En ligne'),
    }
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for mot_cle, details in base_rules.items():
            libelle, categorie, sous_categorie = details
            # ON CONFLICT DO NOTHING = ne fait rien si "NETFLIX" existe déjà
            cursor.execute("""
            INSERT INTO regles_generales (mot_cle, libelle_nettoye, categorie, sous_categorie)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (mot_cle) DO NOTHING
            """, (mot_cle, libelle, categorie, sous_categorie))
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Règles de base vérifiées et insérées.")
    except Exception as e:
        print(f"Erreur lors du 'seeding' de la BDD : {e}")

# On s'assure que tout est prêt au démarrage
init_db()
seed_database()
    

# --- 3. Logique Métier (Mise à jour) ---

# On n'a plus besoin de ce dictionnaire, il est dans la BDD !
# REGLES_DE_CATEGORISATION = { ... } 

def sauvegarder_regle_generale(mot_cle, libelle_nettoye, categorie, sous_categorie):
    # C'est la fonction pour l'apprentissage automatique de l'IA
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO regles_generales (mot_cle, libelle_nettoye, categorie, sous_categorie)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (mot_cle) DO NOTHING
        """, (mot_cle.upper(), libelle_nettoye, categorie, sous_categorie))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"--- 🧠 Règle GÉNÉRALE sauvegardée : {mot_cle.upper()} -> {categorie} ---")
        return True
    except Exception as e:
        print(f"Erreur BDD (sauvegarde générale) : {e}")
        return False

def sauvegarder_regle_personnelle(user_id, mot_cle, libelle_nettoye, categorie, sous_categorie):
    # C'est la fonction pour le "veto" de l'utilisateur
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # ON CONFLICT DO UPDATE = si l'utilisateur change d'avis, on met à jour sa règle
        cursor.execute("""
        INSERT INTO regles_personnelles (user_id, mot_cle, libelle_nettoye, categorie, sous_categorie)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id, mot_cle) DO UPDATE SET
            libelle_nettoye = EXCLUDED.libelle_nettoye,
            categorie = EXCLUDED.categorie,
            sous_categorie = EXCLUDED.sous_categorie
        """, (user_id, mot_cle.upper(), libelle_nettoye, categorie, sous_categorie))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"--- 🧑‍💻 Règle PERSONNELLE sauvegardée (User {user_id}) : {mot_cle.upper()} -> {categorie} ---")
        return True
    except Exception as e:
        print(f"Erreur BDD (sauvegarde personnelle) : {e}")
        return False

def extraire_json_de_reponse(texte_brut):
    match = re.search(r'\{.*\}', texte_brut, re.DOTALL)
    if match:
        try: return json.loads(match.group(0))
        except json.JSONDecodeError: return None
    return None

def appel_llm_ia(transaction):
    # ... (fonction identique, elle appelle l'IA)
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
    prompt = f"""
    Tu es un expert en finances personnelles... (le prompt est identique)
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
            resultat['categorie'] = 'A_VERIFIER'
        return {
            'libelle_nettoye': resultat.get('libelle_nettoye', transaction['libelle']),
            'categorie': resultat.get('categorie', 'A_VERIFIER'),
            'sous_categorie': "Analysé par IA"
        }
    except Exception as e:
        print(f"--- ERREUR lors de l'appel à l'IA (Requests) : {e} ---")
        return {'libelle_nettoye': transaction['libelle'], 'categorie': 'A_VERIFIER', 'sous_categorie': 'Erreur IA'}

# --- CLASSIFIER (MISE À JOUR MAJEURE) ---
def classifier_transaction(transaction, user_id): # <-- On a besoin de savoir QUI
    libelle_brut_upper = transaction['libelle'].upper()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # NIVEAU 1 : BDD Personnelle (Le "Veto")
    cursor.execute(
        "SELECT libelle_nettoye, categorie, sous_categorie FROM regles_personnelles WHERE user_id = %s AND %s LIKE '%%' || mot_cle || '%%'",
        (user_id, libelle_brut_upper)
    )
    regle_personnelle = cursor.fetchone()
    if regle_personnelle:
        conn.close()
        return {**transaction, 'libelle_nettoye': regle_personnelle[0], 'categorie': regle_personnelle[1], 'sous_categorie': regle_personnelle[2], 'methode': 'Regle (Perso)'}

    # NIVEAU 2 : BDD Générale (Le "Savoir Collectif" + Règles de Base)
    cursor.execute(
        "SELECT libelle_nettoye, categorie, sous_categorie FROM regles_generales WHERE %s LIKE '%%' || mot_cle || '%%'",
        (libelle_brut_upper,)
    )
    regle_generale = cursor.fetchone()
    if regle_generale:
        conn.close()
        return {**transaction, 'libelle_nettoye': regle_generale[0], 'categorie': regle_generale[1], 'sous_categorie': regle_generale[2], 'methode': 'Regle (Générale)'}

    cursor.close()
    conn.close()
            
    # NIVEAU 3 : Moteur LLM (Le "Dernier Recours")
    resultat_llm = appel_llm_ia(transaction)
    
    if resultat_llm['categorie'] != 'A_VERIFIER':
        # On apprend automatiquement dans la BDD GÉNÉRALE
        print(f"--- 🤖 APPRENTISSAGE AUTOMATIQUE (Général) ---")
        sauvegarder_regle_generale(
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

# --- 4. Routes de l'API ---

# --- NOUVEAU : Routes d'Authentification ---

@app.route('/api/signup', methods=['POST'])
def api_signup():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"msg": "Email et mot de passe requis"}), 400

    # On hash le mot de passe
    pw_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO utilisateurs (email, password_hash) VALUES (%s, %s)",
            (email, pw_hash)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"msg": "Utilisateur créé avec succès"}), 201
    except Exception as e:
        # "UniqueViolation" est l'erreur si l'email existe déjà
        print(f"Erreur BDD (signup) : {e}")
        return jsonify({"msg": "Cet email existe déjà"}), 409

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"msg": "Email et mot de passe requis"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash FROM utilisateurs WHERE email = %s", (email,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and bcrypt.check_password_hash(user[1], password):
        # Le mot de passe est correct ! On crée un token.
        user_id = user[0]
        access_token = create_access_token(identity=user_id)
        return jsonify(access_token=access_token)
    else:
        return jsonify({"msg": "Email ou mot de passe incorrect"}), 401

# --- FIN Routes d'Auth ---

@app.route('/')
def home():
    return render_template('index.html')

# --- Routes API (MAINTENANT SÉCURISÉES) ---

@app.route('/api/categorize', methods=['POST'])
@jwt_required() # <-- SÉCURISÉ
def api_categorize():
    user_id = get_jwt_identity() # On récupère l'ID de l'utilisateur connecté
    transaction_brute = request.json
    transaction_nettoyee = classifier_transaction(transaction_brute, user_id)
    return jsonify(transaction_nettoyee)

@app.route('/api/create_budget', methods=['POST'])
@jwt_required() # <-- SÉCURISÉ
def api_create_budget():
    # user_id = get_jwt_identity() # On n'en a pas besoin ici, mais on pourrait
    data = request.json
    transactions = data.get('transactions', [])
    objectif_epargne = data.get('objectif', 0)
    
    # ... (le reste du code create_budget est 100% identique) ...
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
@jwt_required() # <-- SÉCURISÉ
def api_learn_rule():
    user_id = get_jwt_identity() # On récupère l'ID
    data = request.json
    mot_cle = data.get('mot_cle')
    categorie = data.get('categorie')
    
    if not mot_cle or not categorie:
        return jsonify({'status': 'erreur', 'message': 'Données manquantes'}), 400
    
    # On sauvegarde dans la BDD PERSONNELLE de l'utilisateur
    success = sauvegarder_regle_personnelle(
        user_id=user_id,
        mot_cle=mot_cle,
        libelle_nettoye=mot_cle.capitalize(),
        categorie=categorie,
        sous_categorie="Validé (Utilisateur)"
    )
    if success:
        return jsonify({'status': 'ok', 'message': f"Règle PERSONNELLE '{mot_cle.upper()}' sauvegardée."})
    else:
        return jsonify({'status': 'erreur', 'message': 'Erreur BDD'}), 500

# --- 5. Lancement (On n'a plus besoin du 'if __name__ ...') ---
# Gunicorn va juste importer le fichier et trouver l'objet 'app'.
# L'appel à init_db() et seed_database() est maintenant aux lignes 66-67.