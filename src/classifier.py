"""
Classifie et résume chaque mail via Gemini.
Retourne None si le mail n'est pas lié à une candidature.
"""
import os
import json
import time
from google import genai
from google.genai import errors as genai_errors

MODEL = "gemini-2.5-flash-lite"


class QuotaExhausted(Exception):
    """
    Levée quand le quota journalier (RPD free tier) est épuisé.
    Porte les résultats déjà obtenus avant l'épuisement (partial_results / partial_processed)
    pour qu'ils ne soient pas perdus.
    """
    def __init__(self, message="", partial_results=None, partial_processed=None):
        super().__init__(message)
        self.partial_results = partial_results or []
        self.partial_processed = partial_processed or []

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

BATCH_PROMPT_HEADER = """Tu es un assistant spécialisé dans le suivi de candidatures d'emploi.

Tu reçois PLUSIEURS mails numérotés. Analyse-les TOUS et réponds UNIQUEMENT par un tableau JSON valide.
Chaque élément du tableau correspond à un mail et contient exactement ces champs :
{{
  "index": <numéro du mail, entier>,
  "est_candidature": true/false,
  "entreprise": "nom de l'entreprise ou null",
  "categorie": "une des catégories ci-dessous ou null",
  "resume": "résumé en 1-2 phrases en français ou null",
  "positif": "oui" / "non" / "—"
}}

Catégories possibles : {categories}

Règles :
- "est_candidature" = true si le mail est lié de près ou de loin à une candidature d'emploi (offre, réponse RH, entretien, relance, refus, accusé réception). Sinon false.
- Si "est_candidature" = false, mets entreprise/categorie/resume à null et "positif" à "—".
- "positif" = "oui" pour Entretien et Réponse positive, "non" pour Refus, "—" pour le reste.
- Le résumé doit être en français, factuel, 1-2 phrases maximum.
- "entreprise" : extrait le nom de l'entreprise si possible, sinon null.
- Renvoie EXACTEMENT un objet par mail, avec le bon "index". Ne fusionne ni n'omets aucun mail.

Mails à analyser :
"""

BATCH_MAIL_BLOCK = """
--- Mail {index} ---
Expéditeur : {sender}
Objet : {subject}
Corps :
{body}
"""

# Au-delà, on découpe en sous-lots pour garder une réponse JSON fiable.
MAX_BATCH_SIZE = 15


def _get_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Variable d'environnement GEMINI_API_KEY manquante.")
    return genai.Client(api_key=api_key)


def _generate_with_retry(client, prompt: str, max_output_tokens: int = 512) -> str:
    """
    Appelle Gemini avec gestion des erreurs. Retourne le texte brut.
    Lève QuotaExhausted si le quota journalier (RPD) est épuisé.
    """
    for attempt in range(4):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={"temperature": 0.1, "max_output_tokens": max_output_tokens},
            )
            return response.text.strip()
        except genai_errors.ClientError as e:
            msg = str(e)
            if "429" not in msg and "RESOURCE_EXHAUSTED" not in msg:
                raise
            # Quota journalier épuisé (RPD) : inutile de réessayer aujourd'hui.
            if "PerDay" in msg or "GenerateRequestsPerDay" in msg:
                raise QuotaExhausted(msg)
            # Sinon : rate limit par minute (RPM), on attend et on réessaye.
            if attempt == 3:
                raise QuotaExhausted(msg)
            wait = 30 * (attempt + 1)
            print(f"    Rate limit Gemini (RPM), attente {wait}s (tentative {attempt + 1}/4)...")
            time.sleep(wait)
        except genai_errors.ServerError:
            # 503/500 : surcharge serveur temporaire, on réessaye après une courte pause.
            if attempt == 3:
                raise
            wait = 10 * (attempt + 1)
            print(f"    Serveur Gemini indisponible (503), attente {wait}s (tentative {attempt + 1}/4)...")
            time.sleep(wait)


def _strip_json_fence(raw: str) -> str:
    """Retire les éventuelles balises markdown ```json ... ``` autour du JSON."""
    if raw.startswith("```"):
        parts = raw.split("```")
        # le contenu utile est dans le 2e segment
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return raw


def _to_result(data: dict, email: dict) -> dict | None:
    """Convertit la réponse Gemini d'un mail en ligne de résultat, ou None si hors candidature."""
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


def classify_email(email: dict) -> dict | None:
    """
    Classifie UN mail (1 requête Gemini). Conservé comme fallback unitaire.
    Retourne un dict enrichi, ou None si hors candidature.
    """
    client = _get_client()
    prompt = PROMPT_TEMPLATE.format(
        categories=", ".join(CATEGORIES),
        sender=email.get("sender", ""),
        subject=email.get("subject", ""),
        body=email.get("body", ""),
    )
    raw = _strip_json_fence(_generate_with_retry(client, prompt))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {
            "est_candidature": False,
            "resume": f"[Erreur parsing Gemini] {raw[:200]}",
            "positif": "—",
        }
    return _to_result(data, email)


def _classify_chunk(client, emails: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Classifie un sous-lot (<= MAX_BATCH_SIZE) en UNE requête Gemini.
    Retourne (résultats_candidatures, message_ids_traités).
    Un mail absent de la réponse n'est PAS marqué traité (il repassera).
    """
    blocks = "".join(
        BATCH_MAIL_BLOCK.format(
            index=i + 1,
            sender=e.get("sender", ""),
            subject=e.get("subject", ""),
            body=e.get("body", ""),
        )
        for i, e in enumerate(emails)
    )
    prompt = BATCH_PROMPT_HEADER.format(categories=", ".join(CATEGORIES)) + blocks

    # ~200 tokens/mail de marge pour la réponse.
    raw = _strip_json_fence(_generate_with_retry(client, prompt, max_output_tokens=220 * len(emails) + 256))

    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError("La réponse n'est pas un tableau JSON.")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"    [batch] Parsing JSON échoué ({e}). Sous-lot non marqué, sera repris au prochain run.")
        return [], []

    # index Gemini (1-based) -> données
    by_index = {}
    for item in parsed:
        if isinstance(item, dict) and "index" in item:
            by_index[item["index"]] = item

    results = []
    processed_ids = []
    for i, email in enumerate(emails):
        data = by_index.get(i + 1)
        if data is None:
            # Mail absent de la réponse : on ne le marque pas, il repassera.
            print(f"    [batch] Mail {i + 1} absent de la réponse Gemini, reporté.")
            continue
        processed_ids.append(email["message_id"])
        res = _to_result(data, email)
        if res is not None:
            results.append(res)
    return results, processed_ids


def classify_batch(emails: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Classifie TOUS les mails en lots (1 requête Gemini par lot de MAX_BATCH_SIZE).
    Retourne (résultats_candidatures, message_ids_réellement_traités).
    Propage QuotaExhausted : les mails déjà traités avant l'épuisement sont conservés.
    """
    client = _get_client()
    all_results = []
    all_processed = []

    for start in range(0, len(emails), MAX_BATCH_SIZE):
        chunk = emails[start:start + MAX_BATCH_SIZE]
        try:
            results, processed = _classify_chunk(client, chunk)
        except QuotaExhausted as e:
            # On remonte ce qui a déjà été traité avant l'épuisement du quota.
            raise QuotaExhausted(
                str(e),
                partial_results=all_results,
                partial_processed=all_processed,
            )
        all_results.extend(results)
        all_processed.extend(processed)

    return all_results, all_processed
