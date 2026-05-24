"""
Lit les mails Gmail et retourne uniquement ceux non encore traités (par Message-ID).
"""
import os
import base64
import json
from datetime import datetime, timezone, timedelta
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
PROCESSED_IDS_FILE = "processed_ids.json"


def _load_credentials() -> Credentials:
    token_json = os.environ.get("GMAIL_TOKEN_JSON")
    if not token_json:
        raise RuntimeError("Variable d'environnement GMAIL_TOKEN_JSON manquante.")
    token_data = json.loads(token_json)
    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def _load_processed_ids() -> set:
    if os.path.exists(PROCESSED_IDS_FILE):
        with open(PROCESSED_IDS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def _save_processed_ids(ids: set) -> None:
    with open(PROCESSED_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids), f)


def _decode_body(payload: dict) -> str:
    """Extrait le texte brut du payload Gmail (multipart ou simple)."""
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                    break
        if not body:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/html":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                        break
    else:
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    return body[:4000]  # on tronque pour éviter les tokens excessifs


def _extract_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def fetch_new_emails(hours_back: int = 48) -> list[dict]:
    """
    Retourne les mails des dernières `hours_back` heures
    qui n'ont pas encore été traités (Message-ID inconnu).
    """
    creds = _load_credentials()
    service = build("gmail", "v1", credentials=creds)

    since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    after_ts = int(since.timestamp())
    query = f"after:{after_ts}"

    result = service.users().messages().list(userId="me", q=query, maxResults=200).execute()
    messages = result.get("messages", [])

    processed_ids = _load_processed_ids()
    new_emails = []

    for msg_ref in messages:
        msg = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="full"
        ).execute()

        headers = msg.get("payload", {}).get("headers", [])
        message_id = _extract_header(headers, "Message-ID")

        if not message_id:
            message_id = msg_ref["id"]

        if message_id in processed_ids:
            continue

        subject = _extract_header(headers, "Subject")
        sender = _extract_header(headers, "From")
        date_str = _extract_header(headers, "Date")
        body = _decode_body(msg.get("payload", {}))

        new_emails.append({
            "message_id": message_id,
            "subject": subject,
            "sender": sender,
            "date": date_str,
            "body": body,
        })

    return new_emails, processed_ids


def mark_as_processed(message_ids: list[str], existing_ids: set) -> None:
    existing_ids.update(message_ids)
    _save_processed_ids(existing_ids)
