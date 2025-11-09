import google.generativeai as genai
import os

# --- METS TA CLÉ API SECRÈTE ICI ---
API_KEY = "AIzaSyClpHCtvV8rA89DJWu2ZWx6sNiMd-zJJuQ"
# --- --------------------------- ---

try:
    genai.configure(api_key=API_KEY)
    print("Clé API configurée. Tentative de listage des modèles...\n")
    
    # On demande à Google de lister les modèles auxquels cette clé a accès
    for m in genai.list_models():
        # On affiche tous les modèles qui supportent la "génération de contenu"
        if 'generateContent' in m.supported_generation_methods:
            print(f"Modèle compatible trouvé: {m.name}")

    print("\n--- Fin de la liste ---")
    print("Si tu vois des modèles (ex: models/gemini-pro), le test a réussi.")
    print("Si le script plante, l'erreur vient de la clé ou de la bibliothèque.")

except Exception as e:
    print(f"\n--- ERREUR LORS DU DIAGNOSTIC ---")
    print("L'appel a échoué. Cela confirme que le problème est soit la clé, soit la bibliothèque.")
    print(f"Détail de l'erreur: {e}")