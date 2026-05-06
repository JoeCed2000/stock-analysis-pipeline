# Revue seconde passe - PDF, langue, ZIP, sécurité, qualité

Date : 2026-05-06

## Findings critiques

### P0 - Le ZIP japonais peut écraser le PDF deep-dive structuré

Fichier : `backend/main.py`

Lignes concernées : conversion `*.md` vers PDF dans `dossier_download`.

Cause : quand `lang != en`, `work_dir` est défini et `refresh_pdf = True`. La boucle reconvertit tous les `.md` en PDF, y compris `07_final_report/earnings_deep_dive.md`, avec `md_to_pdf`. Cela peut remplacer le PDF ReportLab structuré par un PDF Markdown simplifié qui perd les tables et le template.

Impact : régression directe sur l'objectif principal. Le ZIP final peut ne pas contenir le PDF fidèle au modèle.

Correction : ne jamais reconvertir `earnings_deep_dive.md` par `md_to_pdf` si `earnings_deep_dive.pdf` existe. À terme, régénérer ce PDF depuis le modèle structuré dans la langue demandée.

### P0 - Traduction Codex encore permissive si Codex est indisponible

Fichier : `backend/translator.py`

Lignes concernées : `translate_text`.

Cause : `translate_text` retourne le texte source si Codex ne renvoie rien. C'est acceptable pour un fallback bas niveau, mais pas pour un ZIP explicitement demandé en japonais.

Impact : un ZIP `lang=jp` peut sortir avec des documents anglais sans erreur visible.

Correction : ajouter un mode strict pour le ZIP. En mode strict, l'indisponibilité Codex doit échouer proprement ou remonter une erreur contrôlée.

### P0 - Les polices du modèle ne sont pas utilisées

Fichier : `backend/earnings_deep_dive/pdf_renderer.py`

Lignes concernées : `_font_for_language`, `_styles`.

Constat modèle : `modele.pdf` utilise principalement `ArialMT`, `Arial-BoldMT`, `MS-PGothic`.

Constat final actuel : `final-report-en.pdf` utilise `Helvetica`.

Impact : impossible d'obtenir une similarité "en tous points identique" sans charger Arial/MS-PGothic ou assets équivalents.

Correction : résoudre et enregistrer les polices locales/packagées, avec fallback documenté. Ajouter test qui vérifie que le PDF de sortie n'est pas en Helvetica quand les polices modèle sont disponibles.

## Findings élevés

### P1 - Données attendues encore très incomplètes

Fichier : `backend/earnings_deep_dive/mapper.py`

Cause : beaucoup de colonnes du modèle restent `DONNÉE NON DISPONIBLE` : prior year, quality, interpretation, margin guidance, EPS guidance, demand signal.

Impact : le PDF peut être visuellement structuré mais ne satisfait pas "tous les chiffres attendus présents".

Correction : créer une matrice exhaustive des champs attendus du modèle et des sources disponibles. Ajouter tests de couverture des valeurs non disponibles vs disponibles.

### P1 - Quarter deep-dive régénéré en Markdown seulement

Fichier : `backend/main.py`

Cause : la branche `quarter` appelle `generate_deep_dive(...)`, mais ne déclenche pas le renderer PDF structuré ensuite.

Impact : un ZIP demandé pour un quarter précis peut contenir un Markdown mis à jour mais un PDF obsolète ou régénéré par `md_to_pdf`.

Correction : factoriser une fonction de rendu deep-dive depuis `DeepDiveResponse + FinancialMetrics`.

### P1 - Provider nommé Kimi alors que Codex est utilisé

Fichier : `backend/earnings_deep_dive/generator.py`

Cause : import `from backend.codex_provider import _codex_chat as kimi_chat` et meta `"provider": "Kimi K2.6"`.

Impact : traçabilité fausse, audit impossible.

Correction : renommer l'alias et corriger `provider`.

### P1 - `codex_provider._codex_chat` utilise `tempfile.mktemp`

Fichier : `backend/codex_provider.py`

Cause : `tempfile.mktemp` est vulnérable au TOCTOU.

Impact : risque sécurité local faible mais réel.

Correction : remplacer par `NamedTemporaryFile(delete=False)` ou `mkstemp`.

## Findings moyens

### P2 - Exceptions de traduction avalées fichier par fichier

Fichier : `backend/main.py`

Cause : `except Exception: pass` dans les boucles `.txt` et `.md`.

Impact : échec silencieux, ZIP partiellement traduit.

Correction : journaliser fichier + erreur, accumuler les échecs, échouer en mode strict.

### P2 - Le PDF final a 10 pages contre 14 dans le modèle

Fichier : `backend/earnings_deep_dive/pdf_renderer.py`

Cause : une section par page, pas de reproduction fine du flux Google Docs. Le modèle mélange questions, japonais, exemples, tableaux et commentaires sur 14 pages.

Impact : similaire structurellement, pas "en tous points identique".

Correction : créer un layout renderer piloté par blocs du modèle : marges 72 pt, tailles Arial/MS-PGothic, couleurs extraites, breaks calibrés.

### P2 - Les tests visuels ne verrouillent pas encore un seuil

Fichiers : `scripts/pdf_audit_extract.py`, `tests/test_earnings_pdf_renderer.py`

Cause : le diff visuel est généré mais pas asserté en test.

Impact : régressions visuelles possibles.

Correction : test léger sur page size, nombre de pages cible, familles de polices, présence des sections/chiffres critiques.

## Workspace / hygiène Git

À clarifier avant commit :

- `.env.example` supprimé : à restaurer sauf décision contraire.
- `docs/specs/Earnings Documents.pdf` supprimé : confirmer renommage vers `docs/specs/modele.pdf`.
- Nombreux scripts `_check_*`, `_daily_run.py`, `_fast_run.py`, `_run_remaining.py` non suivis : décider s'ils sont temporaires.
- `reports/pdf-visual-diff/` et `reports/generated/` : probablement artefacts de validation à ne pas commiter entièrement.
- `skills-starter-kit/` et zip : source de guidelines utile localement, probablement à exclure du commit produit.

## Priorité de correction

1. Empêcher le ZIP de dégrader le PDF deep-dive structuré.
2. Rendre la traduction Codex stricte pour les ZIP non anglais.
3. Charger les polices du modèle.
4. Corriger la traçabilité provider Codex.
5. Sécuriser `codex_provider._codex_chat`.
6. Étendre la matrice de données/chiffres attendus.
7. Caler pagination/espacements vers les 14 pages du modèle.

## Statut après corrections seconde passe

Corrigé :

- ZIP : `earnings_deep_dive.md` ne peut plus écraser le PDF structuré existant.
- Traduction : le ZIP non anglais utilise `translate_text(..., strict=True)` via Codex local.
- Provider : la meta deep-dive annonce `Codex CLI local`.
- Sécurité : `tempfile.mktemp` supprimé du provider Codex.
- Polices : le renderer résout Arial/Arial-Bold/MS-PGothic depuis assets ou polices Windows locales.

Encore ouvert :

- Pagination et layout : final EN encore à 10 pages, modèle à 14 pages.
- Données : plusieurs colonnes restent non disponibles faute de mapping/source exhaustive.
- ZIP : le deep-dive structuré n'est plus dégradé, mais la génération native par langue doit être renforcée pour les dossiers déjà existants.
- Tests visuels : diff généré, seuils non bloquants.
