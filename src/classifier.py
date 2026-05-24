"""
Classifie et résume chaque mail via Gemini 2.0 Flash.
Retourne None si le mail n'est pas lié à une candidature.
"""
import os
import json
import time
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

CATEGORIES = [
    "Entretien",
    "Réponse positive",
    "Refus",
    "Relance",
    "Accusé réception",
    "Hors candidature",
]

PROMPT_TEMPLATE = """Tu es un assistant spécialisé dans le suivi de candidatures d'emploi.

Analyse le mail suivant et réponds UNIQUEMENT en JSON valide avec exactement ces champs :
{{
  "est_candidature": true/false,
  "entreprise": "nom de l'entreprise ou null",
  "categorie": "une des catégories ci-dessous ou null",
  "resume": "résumé en 1-2 phrases en français ou null",
  "positif": "oui" / "non" / "—"
}}

Catégories possibles : {categories}

Règles :
- "est_candidature" = true si le mail est lié de près ou de loin à une candidature d'emploi (offre, réponse RH, entretien, relance, refus, accusé réception). Sinon false.
- Si "est_candidature" = false, tous les autres champs doivent être null sauf "positif" qui vaut "—".
- "positif" = "oui" pour Entretien et Réponse positive, "non" pour Refus, "—" pour le reste.
- Le résumé doit être en français, factuel, 1-2 phrases maximum.
- "entreprise" : extrait le nom de l'entreprise si possible, sinon null.

Mail à analyser :
Expéditeur : {sender}
Objet : {subject}
Corps :
{body}
"""


def _get_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Variable d'environnement GEMINI_API_KEY manquante.")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-1.5-flash")


def classify_email(email: dict) -> dict | None:
    """
    Retourne un dict avec les champs enrichis, ou None si hors candidature.
    """
    model = _get_client()

    prompt = PROMPT_TEMPLATE.format(
        categories=", ".join(CATEGORIES),
        sender=email.get("sender", ""),
        subject=email.get("subject", ""),
        body=email.get("body", ""),
    )

    for attempt in range(4):
        try:
            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.1, "max_output_tokens": 512},
            )
            break
        except ResourceExhausted as e:
            if attempt == 3:
                raise
            wait = 30 * (attempt + 1)
            print(f"    Rate limit Gemini, attente {wait}s (tentative {attempt + 1}/4)...")
            time.sleep(wait)

    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {
            "est_candidature": False,
            "entreprise": None,
            "categorie": None,
            "resume": f"[Erreur parsing Gemini] {raw[:200]}",
            "positif": "—",
        }

    if not data.get("est_candidature"):
        return None

    return {
        "message_id": email["message_id"],
        "date": email["date"],
        "sender": email["sender"],
        "subject": email["subject"],
        "entreprise": data.get("entreprise") or "",
        "categorie": data.get("categorie") or "Hors candidature",
        "resume": data.get("resume") or "",
        "positif": data.get("positif") or "—",
    }
