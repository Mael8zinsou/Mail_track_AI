"""
Point d'entrée principal. Appelé par GitHub Actions ou manuellement.
"""
import sys
from src.gmail_reader import fetch_new_emails, mark_as_processed
from src.classifier import classify_email
from src.sheets_writer import append_results


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

    for i, email in enumerate(emails, 1):
        subject = email.get("subject", "(sans objet)")
        print(f"  [{i}/{len(emails)}] Analyse : {subject[:60]}")
        result = classify_email(email)
        if result is None:
            skipped += 1
        else:
            classified.append(result)

    print(f"\n  {len(classified)} mail(s) lié(s) à des candidatures.")
    print(f"  {skipped} mail(s) ignoré(s) (hors candidature).")

    if classified:
        print("\nÉcriture dans Google Sheets...")
        inserted = append_results(classified)
        print(f"  {inserted} ligne(s) ajoutée(s).")

    all_ids = [e["message_id"] for e in emails]
    mark_as_processed(all_ids, processed_ids)

    print("\nTerminé.")


if __name__ == "__main__":
    run()
