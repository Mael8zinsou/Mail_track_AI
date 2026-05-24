"""
Écrit les résultats dans Google Sheets.
Structure :
  - Ligne 1 : compteurs (formules)
  - Ligne 2 : en-têtes
  - Lignes 3+ : données (les plus récentes en haut, insérées après la ligne 2)
"""
import os
import json
from datetime import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADERS = ["Date", "Expéditeur", "Entreprise", "Catégorie", "Résumé IA", "Positif"]

COUNTER_LABELS = {
    "A1": "Total candidatures",
    "B1": "Entretiens",
    "C1": "Réponses positives",
    "D1": "Refus",
    "E1": "Relances",
    "F1": "Accusés réception",
}


def _load_credentials() -> Credentials:
    token_json = os.environ.get("GMAIL_TOKEN_JSON")
    if not token_json:
        raise RuntimeError("Variable d'environnement GMAIL_TOKEN_JSON manquante.")
    token_data = json.loads(token_json)
    creds = Credentials.from_authorized_user_info(
        token_data,
        ["https://www.googleapis.com/auth/gmail.readonly",
         "https://www.googleapis.com/auth/spreadsheets"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def _get_service():
    creds = _load_credentials()
    return build("sheets", "v4", credentials=creds)


def _ensure_headers(service, sheet_id: str, sheet_name: str) -> None:
    """Initialise ligne 1 (compteurs) et ligne 2 (en-têtes) si la feuille est vide."""
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{sheet_name}!A1:F2",
    ).execute()
    values = result.get("values", [])

    if not values or len(values) < 2:
        counter_row = [
            "=COUNTA(A3:A)",
            '=COUNTIF(D3:D,"Entretien")',
            '=COUNTIF(D3:D,"Réponse positive")',
            '=COUNTIF(D3:D,"Refus")',
            '=COUNTIF(D3:D,"Relance")',
            '=COUNTIF(D3:D,"Accusé réception")',
        ]
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A1:F2",
            valueInputOption="USER_ENTERED",
            body={"values": [counter_row, HEADERS]},
        ).execute()


def append_results(results: list[dict]) -> int:
    """
    Insère les lignes en position 3 (après les en-têtes) pour avoir les plus récents en haut.
    Retourne le nombre de lignes insérées.
    """
    if not results:
        return 0

    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    sheet_name = os.environ.get("GOOGLE_SHEET_NAME", "Suivi candidatures")
    if not sheet_id:
        raise RuntimeError("Variable d'environnement GOOGLE_SHEET_ID manquante.")

    service = _get_service()
    _ensure_headers(service, sheet_id, sheet_name)

    rows = []
    for r in results:
        date_val = r.get("date", "")
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_val)
            date_val = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass

        rows.append([
            date_val,
            r.get("sender", ""),
            r.get("entreprise", ""),
            r.get("categorie", ""),
            r.get("resume", ""),
            r.get("positif", "—"),
        ])

    # Insère après la ligne 2 (ligne 3 = index 2, 0-based)
    service.spreadsheets().values().insert(
        spreadsheetId=sheet_id,
        range=f"{sheet_name}!A3",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()

    return len(rows)
