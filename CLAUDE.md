# CLAUDE.md — Notes de travail

> Fichier de suivi pour Claude. Garde le fil du travail en cours, l'historique du debug, et l'état actuel.

## Résumé du projet

Voir [doc.md](doc.md) pour le contexte complet. En bref : pipeline GitHub Actions qui lit Gmail → classifie via Gemini → écrit dans Google Sheets, déclenché par cron quotidien.

## État actuel : PIPELINE VALIDÉ DE BOUT EN BOUT (run réussi)

Premier run complet réussi : Gmail → dédup → Gemini → écriture Sheets (2 lignes ajoutées).
La gestion `QuotaExhausted` fonctionne en réel : quota 20 RPD touché → arrêt propre, exit 0,
données déjà classifiées écrites, reste reporté au prochain run.

### Historique des bugs successifs résolus (tous réglés)
1. `gemini-2.0-flash` → `limit: 0` (modèle sans quota free tier). Réglé : bascule `gemini-2.5-flash-lite`.
2. SDK `google-generativeai` (v1beta, noms obsolètes) → migration `google-genai` (v1).
3. 503 ServerError → retry dédié + arrêt propre.
4. 403 Sheets → la Sheet n'était pas partagée avec le compte du token (multi-comptes Google). Réglé : partage en éditeur.
5. `values().insert` inexistant → remplacé par `batchUpdate` (insertDimension) + `values().update` + helper `_get_sheet_gid`.

### LIMITE CONNUE : 20 RPD trop juste
1 requête Gemini par mail → 20 mails/jour sature le quota. **Amélioration recommandée : batcher N mails en 1 requête** (1 prompt = tableau de mails → tableau JSON de classifications). Diviserait le nb de requêtes par ~N.

---

## Diagnostic résolu (archive) : mauvais modèle

**`gemini-2.0-flash` n'a plus de quota free tier** (retiré/remplacé). D'où `limit: 0` : aucun quota alloué à ce modèle. Confirmé via le dashboard AI Studio de l'utilisateur, qui ne montre AUCUNE donnée pour `2.0-flash`, mais des quotas pour les modèles actuels :

| Modèle free tier | RPD (jour) | RPM (minute) |
|---|---|---|
| gemini-2.5-flash | 20 | 5 |
| gemini-2.5-flash-lite | 20 | 10 |
| gemini-3.0-flash | (à vérifier) | — |

**Correctif appliqué : bascule sur `gemini-2.5-flash-lite`** (meilleur RPM : 10/min).

### Contrainte critique : 20 RPD

20 requêtes/jour = pile la limite du volume cible (10-20 mails/jour). Chaque retry échoué consomme une requête. D'où les protections ajoutées (voir ci-dessous).

### Symptôme historique (résolu)

```
429 RESOURCE_EXHAUSTED ... limit: 0, model: gemini-2.0-flash
```
`limit: 0` = le modèle 2.0-flash n'a aucun quota free tier, pas un dépassement.

## Historique du debug (chronologique)

1. **Erreur initiale** : 429 `limit: 0` sur `gemini-2.0-flash` avec SDK `google-generativeai==0.7.2`.
   - Hypothèse : clé liée au mauvais projet. → fausse piste.

2. **Bascule vers `gemini-1.5-flash`** + ajout retry backoff (30/60/90s).
   - Nouvelle erreur : `404 models/gemini-1.5-flash is not found for API version v1beta`.
   - Le SDK `google-generativeai` utilise l'API `v1beta` avec des noms de modèles obsolètes.

3. **Migration SDK vers `google-genai==1.10.0`** (nouveau SDK officiel, API `v1`) + retour à `gemini-2.0-flash`.
   - Retour de l'erreur `429 limit: 0`. Le retry backoff fonctionne (attend bien 30/60/90s) mais finit par échouer.

4. **Ajout step debug "Vérification clé Gemini"** dans cron.yml.
   - Résultat : clé de **53 caractères**, **HTTP 200** sur l'endpoint `/v1beta/models?key=...`.
   - MAIS : lister les modèles ne consomme pas de quota → le 200 ne prouve pas que `generateContent` est autorisé.

## Correctifs appliqués (à tester)

1. **`src/classifier.py`** :
   - Modèle = `gemini-2.5-flash-lite` (constante `MODEL`).
   - Nouvelle exception `QuotaExhausted` levée quand le quota JOURNALIER (RPD) est touché → inutile de réessayer.
   - Le retry backoff ne s'applique plus qu'au rate limit PAR MINUTE (RPM).
2. **`main.py`** :
   - Délai de 7s entre chaque appel (respecte 10 RPM).
   - Si `QuotaExhausted` → arrêt PROPRE, on sauvegarde les mails déjà traités et on sort sans crash.
   - On ne marque comme traités QUE les mails réellement classifiés → le reste repassera au prochain run.

### Prochaine action (en attente)

Push + relance workflow. Résultats attendus :
- Soit ça passe (≤ ~20 mails, sous le RPD).
- Soit `QuotaExhausted` → exit 0 propre, reprise demain.

### Pistes si le 20 RPD est trop bas pour le besoin

- Le volume cible (10-20/jour) frôle la limite. Si insuffisant : envisager modèle alt gratuit (Groq, OpenRouter free tier) ou batcher plusieurs mails en 1 seule requête Gemini (1 prompt = N mails → divise le nb de requêtes).

## Fichiers à nettoyer avant prod

- **Retirer le step "Vérification clé Gemini"** de `.github/workflows/cron.yml` (debug temporaire).
