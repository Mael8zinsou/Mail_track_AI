"""
Script one-shot à exécuter UNE SEULE FOIS en local.
Génère token.json via le flux OAuth2 interactif,
puis affiche la valeur à copier dans le secret GitHub GMAIL_TOKEN_JSON.

Usage :
    python auth_setup.py
Prérequis :
    - credentials.json dans le même dossier (téléchargé depuis Google Cloud Console)
    - pip install google-auth-oauthlib
"""
import json
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def main():
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"ERREUR : fichier '{CREDENTIALS_FILE}' introuvable.")
        print("Télécharge-le depuis Google Cloud Console > APIs & Services > Credentials.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }

    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)

    print(f"\ntoken.json généré avec succès.")
    print("\n" + "=" * 60)
    print("COPIE CE JSON DANS LE SECRET GITHUB  -->  GMAIL_TOKEN_JSON")
    print("=" * 60)
    print(json.dumps(token_data))
    print("=" * 60)
    print("\nATTENTION : ne committe JAMAIS token.json ni credentials.json !")


if __name__ == "__main__":
    main()
