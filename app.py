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
from flask_bcrypt import Bcrypt 
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required, JWTManager 

load_dotenv() 

# --- 1. Configuration ---
app = Flask(__name__)
CORS(app)

# --- CONFIGURATION DE LA SÉCURITÉ ---
app.config["JWT_SECRET_KEY"] = "ton-super-secret-jwt-change-moi"
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# --- CONFIGURATION IA ---
API_KEY = os.environ.get("GEMINI_API_KEY") 
if not API_KEY:
    print("ERREUR FATALE : GEMINI_API_KEY n'est pas définie.")
IA_MODEL_NAME = "gemini-pro-latest" 
IA_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{IA_MODEL_NAME}:generateContent?key={API_KEY}"
print(f"Configuration IA : Prêt à appeler {IA_MODEL_NAME} via v1beta.")
IA_COOLDOWN_SECONDS = 31
LAST_IA_CALL_TIME = 0

# --- CONFIGURATION BDD ---
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("ERREUR FATALE : DATABASE_URL n'est pas définie.")

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# --- 2. Initialisation BDD ---
def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Table utilisateurs
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS utilisateurs (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
        """)
        
        # Table règles générales
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS regles_generales (
            id SERIAL PRIMARY KEY,
            mot_cle TEXT NOT NULL UNIQUE,
            libelle_nettoye TEXT NOT NULL,
            categorie TEXT NOT NULL,
            sous_categorie TEXT NOT NULL
        )
        """)
        
        # Table règles personnelles
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS regles_personnelles (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            mot_cle TEXT NOT NULL,
            libelle_nettoye TEXT NOT NULL,
            categorie TEXT NOT NULL,
            sous_categorie TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES utilisateurs (id),
            UNIQUE (user_id, mot_cle) 
        )
        """)
        
        # 🆕 NOUVELLE TABLE : Transactions utilisateur
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            libelle TEXT NOT NULL,
            libelle_nettoye TEXT NOT NULL,
            montant REAL NOT NULL,
            categorie TEXT NOT NULL,
            sous_categorie TEXT NOT NULL,
            methode TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES utilisateurs (id)
        )
        """)

        # 🆕 TABLE BUDGET (Pour ne pas perdre son objectif)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE,
            data TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES utilisateurs (id)
        )
        """)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Base de données PostgreSQL (4 tables) initialisée avec succès !")
    except Exception as e:
        print(f"ERREUR LORS DE L'INIT DB: {e}")

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

# Initialisation au démarrage
init_db()
seed_database()
    
# --- 3. Logique Métier ---
def sauvegarder_regle_generale(mot_cle, libelle_nettoye, categorie, sous_categorie):
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
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
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
    Tu es un expert en finances personnelles.
    Analyse la transaction : "{transaction['libelle']}"
    Tâches :
    1.  Propose un "libelle_nettoye" clair (ex: "Achat Fnac").
    2.  Choisis la "categorie" la plus pertinente parmi cette liste : {json.dumps(categories_valides)}
    RÈGLES CRITIQUES :
    -   Si tu ne peux pas deviner, utilise la catégorie "A_VERIFIER".
    -   Ta réponse DOIT commencer par {{"et finir par }}".
    -   Ne réponds RIEN d'autre.
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
            resultat['categorie'] = 'A_VERIFIER'
            
        return {
            'libelle_nettoye': resultat.get('libelle_nettoye', transaction['libelle']),
            'categorie': resultat.get('categorie', 'A_VERIFIER'),
            'sous_categorie': "Analysé par IA"
        }
        
    except Exception as e:
        print(f"--- ERREUR lors de l'appel à l'IA (Requests) : {e} ---")
        return {'libelle_nettoye': transaction['libelle'], 'categorie': 'A_VERIFIER', 'sous_categorie': 'Erreur IA'}

def classifier_transaction(transaction, user_id):
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

# --- 4. Routes de l'API ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/signup', methods=['POST'])
def api_signup():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    if not email or not password:
        return jsonify({"msg": "Email et mot de passe requis"}), 400
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
        user_id = user[0]
        access_token = create_access_token(identity=str(user_id))
        return jsonify(access_token=access_token)
    else:
        return jsonify({"msg": "Email ou mot de passe incorrect"}), 401

# 🆕 NOUVELLE ROUTE : Récupérer les transactions d'un utilisateur
@app.route('/api/transactions', methods=['GET'])
@jwt_required()
def api_get_transactions():
    user_id = get_jwt_identity()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, date, libelle, libelle_nettoye, montant, categorie, sous_categorie, methode
            FROM transactions
            WHERE user_id = %s
            ORDER BY date ASC
        """, (user_id,))
        
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        transactions = []
        for row in rows:
            transactions.append({
                'id': str(row[0]),
                'date': row[1],
                'libelle': row[2],
                'libelle_nettoye': row[3],
                'montant': row[4],
                'categorie': row[5],
                'sous_categorie': row[6],
                'methode': row[7]
            })
        
        return jsonify(transactions)
    except Exception as e:
        print(f"Erreur lors de la récupération des transactions : {e}")
        return jsonify({"msg": "Erreur serveur"}), 500

# 🆕 NOUVELLE ROUTE : Ajouter une transaction
@app.route('/api/transactions', methods=['POST'])
@jwt_required()
def api_add_transaction():
    user_id = get_jwt_identity()
    transaction_brute = request.json
    
    # Classifier la transaction
    transaction_nettoyee = classifier_transaction(transaction_brute, user_id)
    
    # Sauvegarder dans la BDD
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transactions (user_id, date, libelle, libelle_nettoye, montant, categorie, sous_categorie, methode)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            user_id,
            transaction_nettoyee['date'],
            transaction_nettoyee['libelle'],
            transaction_nettoyee['libelle_nettoye'],
            transaction_nettoyee['montant'],
            transaction_nettoyee['categorie'],
            transaction_nettoyee['sous_categorie'],
            transaction_nettoyee['methode']
        ))
        
        new_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        transaction_nettoyee['id'] = str(new_id)
        return jsonify(transaction_nettoyee), 201
        
    except Exception as e:
        print(f"Erreur lors de l'ajout de la transaction : {e}")
        return jsonify({"msg": "Erreur serveur"}), 500

@app.route('/api/categorize', methods=['POST'])
@jwt_required() 
def api_categorize():
    user_id = get_jwt_identity()
    transaction_brute = request.json
    transaction_nettoyee = classifier_transaction(transaction_brute, user_id)
    return jsonify(transaction_nettoyee)

@app.route('/api/create_budget', methods=['POST'])
@jwt_required() 
def api_create_budget():
    data = request.json
    transactions = data.get('transactions', [])
    objectif_epargne = data.get('objectif', 0)
    revenus = 0
    charges_fixes = 0
    depenses_variables_observees = {}
    total_depenses_variables = 0
    
    for tx in transactions:
        categorie = tx.get('categorie')
        montant = tx.get('montant', 0)
        if categorie == 'Revenus': 
            revenus += montant
        elif categorie == 'Charges Fixes': 
            charges_fixes += montant
        elif categorie not in ['A_VERIFIER', 'Revenus', 'Charges Fixes'] and montant < 0:
            if categorie not in depenses_variables_observees: 
                depenses_variables_observees[categorie] = 0
            depenses_variables_observees[categorie] += montant
            total_depenses_variables += montant
    
    charges_fixes_abs = round(abs(charges_fixes), 2)
    revenus_observes = round(revenus, 2)
    total_depenses_variables_abs = round(abs(total_depenses_variables), 2)
    budget_variable_total_disponible = revenus_observes - charges_fixes_abs - objectif_epargne
    enveloppes_proposees = []
    
    if total_depenses_variables_abs > 0:
        for categorie, total_depense in depenses_variables_observees.items():
            pourcentage = abs(total_depense) / total_depenses_variables_abs
            montant_propose = budget_variable_total_disponible * pourcentage
            montant_propose_arrondi = math.floor(montant_propose / 5) * 5
            enveloppes_proposees.append({
                'categorie': categorie, 
                'depense_observee': round(abs(total_depense), 2), 
                'enveloppe_proposee': montant_propose_arrondi
            })
    
    total_alloue_enveloppes = sum(env['enveloppe_proposee'] for env in enveloppes_proposees)
    bonus_non_alloue = budget_variable_total_disponible - total_alloue_enveloppes
    
    if bonus_non_alloue > 0:
        enveloppes_proposees.append({
            'categorie': 'Bonus (Non Alloué)', 
            'depense_observee': 0, 
            'enveloppe_proposee': round(bonus_non_alloue, 2)
        })
    
    reste_a_vivre_total = budget_variable_total_disponible
    reste_a_vivre_jour = reste_a_vivre_total / 30
    message_ia = f"OK ! Pour atteindre votre objectif de {objectif_epargne}€ d'épargne (sur {revenus_observes}€ de revenus), il nous reste {reste_a_vivre_total}€ à répartir. Je vous propose les enveloppes suivantes :"
    
    reponse_coach = { 
        'revenus_observes': revenus_observes, 
        'fixes_observes': charges_fixes_abs, 
        'enveloppes_proposees': enveloppes_proposees, 
        'message_ia': message_ia, 
        'reste_a_vivre_total': round(reste_a_vivre_total, 2), 
        'reste_a_vivre_jour': round(reste_a_vivre_jour, 2) 
    }
    return jsonify(reponse_coach)

@app.route('/api/learn_rule', methods=['POST'])
@jwt_required() 
def api_learn_rule():
    user_id = get_jwt_identity()
    data = request.json
    mot_cle = data.get('mot_cle')
    categorie = data.get('categorie')
    if not mot_cle or not categorie:
        return jsonify({'status': 'erreur', 'message': 'Données manquantes'}), 400
    
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

# 🆕 ROUTE : Mettre à jour une transaction spécifique (Fixe le bug de la boucle)
@app.route('/api/transactions/<int:transaction_id>', methods=['PUT'])
@jwt_required()
def api_update_transaction(transaction_id):
    user_id = get_jwt_identity()
    data = request.json
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # On vérifie que la transaction appartient bien à l'utilisateur
        cursor.execute("""
            UPDATE transactions 
            SET categorie = %s, sous_categorie = %s, methode = %s
            WHERE id = %s AND user_id = %s
        """, (data['categorie'], "Validé (Utilisateur)", "Utilisateur", transaction_id, user_id))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'status': 'ok'})
    except Exception as e:
        print(f"Erreur update transaction: {e}")
        return jsonify({"msg": "Erreur serveur"}), 500

# 🆕 ROUTE : Gérer le budget (Sauvegarde et Lecture)
@app.route('/api/budget', methods=['GET', 'POST'])
@jwt_required()
def api_budget_manager():
    user_id = get_jwt_identity()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        # Sauvegarder le budget
        budget_data = json.dumps(request.json)
        try:
            cursor.execute("""
                INSERT INTO budgets (user_id, data) VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET data = EXCLUDED.data, updated_at = CURRENT_TIMESTAMP
            """, (user_id, budget_data))
            conn.commit()
            return jsonify({'status': 'saved'})
        except Exception as e:
            return jsonify({"msg": str(e)}), 500
    
    elif request.method == 'GET':
        # Lire le budget
        cursor.execute("SELECT data FROM budgets WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        if row:
            return jsonify(json.loads(row[0]))
        else:
            return jsonify(None) # Pas de budget encore
    
    cursor.close()
    conn.close()      