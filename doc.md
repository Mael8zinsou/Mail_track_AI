# Mail Track AI — Contexte & Suivi du projet

## But du projet

Système de **classification automatique des mails Gmail liés aux candidatures d'emploi**.
Chaque jour, le script lit les mails reçus, les fait classifier/résumer par une IA, et écrit les résultats dans une Google Sheet servant de tableau de bord.

## Stack (100 % gratuite)

| Composant | Rôle |
|---|---|
| **Gmail API** (OAuth2) | Lecture des mails des dernières 48h |
| **Gemini API** (gemini-2.0-flash, free tier) | Classification + résumé en français de chaque mail |
| **Google Sheets API** | Stockage des résultats + compteurs |
| **GitHub Actions** (cron `0 16 * * *` UTC) | Déclenchement quotidien ~18h Paris |

## Catégories de classification

Entretien · Réponse positive · Refus · Relance · Accusé réception · Hors candidature

## Sortie Google Sheets

| Ligne | Contenu |
|---|---|
| 1 | Compteurs automatiques (formules COUNTIF) |
| 2 | En-têtes : Date, Expéditeur, Entreprise, Catégorie, Résumé IA, Positif |
| 3+ | Données (le plus récent inséré en haut) |

## Règles métier

- **Filtrage par l'IA** : c'est Gemini qui décide si un mail est lié à une candidature (pas de pré-filtrage manuel). Si non → mail ignoré.
- **Résumés et catégories en français.**
- **Déduplication** : chaque `Message-ID` traité est stocké dans `processed_ids.json`, mis en cache entre les runs GitHub Actions. Un mail n'est jamais classifié deux fois.
- **Volume estimé** : 10 à 20 mails/jour maximum.
- **Champ "Positif"** : "oui" pour Entretien/Réponse positive, "non" pour Refus, "—" sinon.

## Structure du projet

```
Mail_track_AI/
├── .github/workflows/cron.yml   # GitHub Actions (cron 16h UTC + workflow_dispatch)
├── src/
│   ├── __init__.py
│   ├── gmail_reader.py          # Lecture Gmail + déduplication par Message-ID
│   ├── classifier.py            # Classification Gemini (SDK google-genai)
│   └── sheets_writer.py         # Écriture Google Sheets
├── main.py                      # Orchestrateur
├── auth_setup.py                # Génération token OAuth (one-shot local)
├── requirements.txt
├── .gitignore                   # credentials.json + token.json exclus
├── doc.md                       # Ce fichier
└── README.md                    # Guide de setup utilisateur
```

## Secrets GitHub requis

| Secret | Contenu |
|---|---|
| `GMAIL_TOKEN_JSON` | Token OAuth généré par `auth_setup.py` |
| `GEMINI_API_KEY` | Clé API Gemini |
| `GOOGLE_SHEET_ID` | ID de la Google Sheet |

Variable optionnelle : `GOOGLE_SHEET_NAME` (défaut : `Suivi candidatures`).
