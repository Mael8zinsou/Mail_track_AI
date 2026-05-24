"""
Point d'entrée principal. Appelé par GitHub Actions ou manuellement.
"""
import time
from google.genai.errors import ServerError
from src.gmail_reader import fetch_new_emails, mark_as_processed
from src.classifier import classify_email, QuotaExhausted
from src.sheets_writer import append_results

# 10 RPM sur gemini-2.5-flash-lite => >=6s entre 2 appels.
DELAY_BETWEEN_CALLS = 7


def run():
    print("=== Mail Track AI ===")
    print("Récupération des nouveaux mails...")

    emails, processed_ids = fetch_new_emails(hours_back=48)
    print(f"  {len(emails)} nouveau(x) mail(s) à analyser.")

    if not emails:
        print("Rien à faire.")
        return

    classified = []
    skipped = 0
    processed_now = []  # mails effectivement traités (à marquer)
    quota_hit = False

    for i, email in enumerate(emails, 1):
        subject = email.get("subject", "(sans objet)")
        print(f"  [{i}/{len(emails)}] Analyse : {subject[:60]}")

        try:
            result = classify_email(email)
        except QuotaExhausted:
            print("  Quota journalier Gemini atteint (20 RPD free tier).")
            print("  Arrêt propre : les mails restants seront traités au prochain run.")
            quota_hit = True
            break
        except ServerError:
            print("  Serveur Gemini indisponible (503) malgré les retries.")
            print("  Arrêt propre : les mails restants seront traités au prochain run.")
            quota_hit = True
            break

        processed_now.append(email["message_id"])
        if result is None:
            skipped += 1
        else:
            classified.append(result)

        if i < len(emails):
            time.sleep(DELAY_BETWEEN_CALLS)

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
