# Mail Track AI

Système de classification automatique des mails Gmail liés à des candidatures d'emploi.

**Stack :** Gmail API · Gemini 2.0 Flash · Google Sheets API · GitHub Actions

---

## Fonctionnement

```
GitHub Actions (cron 18h Paris)
  └─▶ Lit les mails Gmail (48h glissantes, nouveaux seulement)
        └─▶ Gemini classifie chaque mail
              └─▶ Résultats insérés dans Google Sheets
```

**Catégories :** Entretien / Réponse positive / Refus / Relance / Accusé réception / Hors candidature

**Google Sheets :**
| Ligne | Contenu |
|---|---|
| 1 | Compteurs automatiques (formules) |
| 2 | En-têtes : Date, Expéditeur, Entreprise, Catégorie, Résumé IA, Positif |
| 3+ | Données (plus récent en haut) |

---

## Setup complet (ordre important)

### Étape 1 — Projet Google Cloud

1. Va sur [console.cloud.google.com](https://console.cloud.google.com)
2. Crée un nouveau projet (ex : `mail-track-ai`)
3. Dans **APIs & Services > Bibliothèque**, active ces 3 APIs :
   - **Gmail API**
   - **Google Sheets API**
   - **Generative Language API** (pour Gemini)

### Étape 2 — Credentials OAuth2 (Desktop)

1. **APIs & Services > Identifiants > Créer des identifiants > ID client OAuth**
2. Type d'application : **Application de bureau**
3. Nom : `mail-track-ai-local`
4. Télécharge le fichier JSON → renomme-le `credentials.json` et place-le à la racine du projet
5. Dans **Écran de consentement OAuth** :
   - Mode : **Externe**
   - Ajoute ton adresse Gmail dans **Utilisateurs test**

> ⚠️ Ne committe jamais `credentials.json` ni `token.json` — ils sont dans `.gitignore`.

### Étape 3 — Clé API Gemini

1. Va sur [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Crée une clé API (projet `mail-track-ai`)
3. Copie la clé — tu en auras besoin à l'étape 5

### Étape 4 — Google Sheet

1. Crée une nouvelle Google Sheet vierge
2. Copie l'ID depuis l'URL : `https://docs.google.com/spreadsheets/d/**[CECI_EST_L_ID]**/edit`
3. Renomme l'onglet si tu veux (défaut : `Suivi candidatures`)

### Étape 5 — Génération du token OAuth (une seule fois, en local)

```bash
# Installe les dépendances
pip install -r requirements.txt

# Lance le flux OAuth (ouvre un navigateur)
python auth_setup.py
```

Le script :
- Ouvre ton navigateur pour l'autorisation Gmail
- Génère `token.json`
- **Affiche dans le terminal le JSON à copier dans GitHub Secrets**

### Étape 6 — Secrets GitHub

Dans ton repo GitHub : **Settings > Secrets and variables > Actions**

| Nom du secret | Valeur |
|---|---|
| `GMAIL_TOKEN_JSON` | Le JSON affiché par `auth_setup.py` |
| `GEMINI_API_KEY` | Ta clé API Gemini |
| `GOOGLE_SHEET_ID` | L'ID de ta Google Sheet |

Optionnel (variable, pas secret) :

| Nom | Valeur par défaut |
|---|---|
| `GOOGLE_SHEET_NAME` | `Suivi candidatures` |

### Étape 7 — Push et activation du cron

```bash
git add .
git commit -m "init: mail track ai"
git push
```

GitHub Actions se déclenche automatiquement chaque jour à **16h UTC (~18h Paris)**.  
Tu peux aussi lancer manuellement : **Actions > Mail Track AI > Run workflow**.

---

## Test en local

```bash
# Exporte les variables d'environnement
export GMAIL_TOKEN_JSON=$(cat token.json)
export GEMINI_API_KEY="ta_cle_gemini"
export GOOGLE_SHEET_ID="ton_sheet_id"

# Lance
python main.py
```

Sur Windows (PowerShell) :
```powershell
$env:GMAIL_TOKEN_JSON = Get-Content token.json -Raw
$env:GEMINI_API_KEY = "ta_cle_gemini"
$env:GOOGLE_SHEET_ID = "ton_sheet_id"
python main.py
```

---

## Déduplication

Les `Message-ID` des mails traités sont stockés dans `processed_ids.json`.  
Ce fichier est mis en cache entre les runs GitHub Actions (via `actions/cache`), ce qui garantit qu'un mail n'est jamais classifié deux fois.

---

## Structure du projet

```
mail_track_ai/
├── .github/
│   └── workflows/
│       └── cron.yml          # GitHub Actions (cron 16h UTC)
├── src/
│   ├── gmail_reader.py       # Lecture Gmail + déduplication
│   ├── classifier.py         # Classification Gemini
│   └── sheets_writer.py      # Écriture Google Sheets
├── main.py                   # Point d'entrée
├── auth_setup.py             # Génération token OAuth (one-shot local)
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Limites du free tier

| Service | Limite gratuite | Usage estimé |
|---|---|---|
| Gmail API | 1 milliard d'unités/jour | ~200 unités/jour |
| Gemini 2.0 Flash | 1 500 req/jour, 1M tokens/min | ~20 req/jour |
| Google Sheets API | 300 req/min | ~5 req/jour |
| GitHub Actions | 2 000 min/mois (privé) | ~2 min/jour | 
