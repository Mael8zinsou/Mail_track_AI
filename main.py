"""
Point d'entrée principal. Appelé par GitHub Actions ou manuellement.
"""
from google.genai.errors import ServerError
from src.gmail_reader import fetch_new_emails, mark_as_processed
from src.classifier import classify_batch, QuotaExhausted
from src.sheets_writer import append_results


def run():
    print("=== Mail Track AI ===")
    print("Récupération des nouveaux mails...")

    emails, processed_ids = fetch_new_emails(hours_back=48)
    print(f"  {len(emails)} nouveau(x) mail(s) à analyser.")

    if not emails:
        print("Rien à faire.")
        return

    quota_hit = False

    # Classification en lot : 1 requête Gemini par lot (au lieu d'1 par mail).
    try:
        classified, processed_now = classify_batch(emails)
    except QuotaExhausted as e:
        print("  Quota journalier Gemini atteint (20 RPD free tier).")
        print("  Arrêt propre : les mails restants seront traités au prochain run.")
        classified = e.partial_results
        processed_now = e.partial_processed
        quota_hit = True
    except ServerError:
        print("  Serveur Gemini indisponible (503) malgré les retries.")
        print("  Arrêt propre : les mails restants seront traités au prochain run.")
        classified = []
        processed_now = []
        quota_hit = True

    skipped = len(processed_now) - len(classified)
    print(f"\n  {len(classified)} mail(s) lié(s) à des candidatures.")
    print(f"  {skipped} mail(s) ignoré(s) (hors candidature).")

    if classified:
        print("\nÉcriture dans Google Sheets...")
        inserted = append_results(classified)
        print(f"  {inserted} ligne(s) ajoutée(s).")

    # On ne marque QUE les mails réellement traités, pour réessayer le reste demain.
    if processed_now:
        mark_as_processed(processed_now, processed_ids)

    if quota_hit:
        print("\nTerminé partiellement (quota). Le reste passera au prochain run.")
    else:
        print("\nTerminé.")


if __name__ == "__main__":
    run()
