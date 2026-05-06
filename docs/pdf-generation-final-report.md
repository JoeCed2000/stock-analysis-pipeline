# Rapport final - génération PDF earnings

Date : 2026-05-06

## 1. Résumé exécutif

État initial :

- `docs/specs/modele.pdf` : 14 pages Letter, template earnings officiel avec sections, questions et tableaux.
- `docs/specs/genere.pdf` : 2 pages A4, rapport standard `report.pdf`, sans structure earnings fidèle.
- Le pipeline deep-dive convertissait un Markdown via `md_to_pdf`, qui ignore les tables Markdown.

État final de cette étape :

- Deux templates exécutables sont disponibles : `en` et `jp`.
- Le rapport deep-dive est généré depuis un modèle structuré et un renderer ReportLab dédié.
- Le pipeline ne génère plus un paquet bilingue implicite : une génération deep-dive produit la langue demandée.
- Le ZIP filtre les anciens sous-dossiers de langue et régénère les PDF dans la copie temporaire quand une langue non anglaise est demandée.
- PDFs de validation générés :
  - `reports/generated/final-report-en.pdf`
  - `reports/generated/final-report-jp.pdf`
  - `reports/generated/final-report.pdf`

Niveau de similarité atteint :

- Amélioration nette : Letter, 10 sections, tables extractibles, titres/questions, données du ticker, marqueur explicite des données manquantes.
- Écart restant : pagination encore à 10 pages contre 14 dans le modèle ; typographie/couleurs proches mais pas pixel-perfect ; absence confirmée des polices officielles Arial/MS-PGothic comme assets projet.

## 2. Pipeline compris

Flux cible désormais utilisé pour le deep-dive :

```text
FinancialMetrics + transcript + ticker + language
        |
        v
backend/earnings_deep_dive/template.py
        |
        v
backend/earnings_deep_dive/mapper.py
        |
        v
backend/earnings_deep_dive/report_model.py
        |
        v
backend/earnings_deep_dive/pdf_renderer.py
        |
        v
07_final_report/earnings_deep_dive.pdf
```

Fichiers principaux :

- `backend/earnings_deep_dive/template.py` : templates `en` et `jp`.
- `backend/earnings_deep_dive/report_model.py` : DTOs de rendu.
- `backend/earnings_deep_dive/mapper.py` : mapping déterministe des métriques.
- `backend/earnings_deep_dive/pdf_renderer.py` : rendu PDF Letter avec tables ReportLab.
- `backend/pipeline.py` : branchement du renderer structuré.
- `backend/main.py` : normalisation `ja/jp`, ZIP dépendant de la langue, régénération PDF en copie temporaire.
- `scripts/pdf_audit_extract.py` : audit modèle / ancien généré / final.
- `scripts/generate_sample_earnings_pdf.py` : fixture locale déterministe.

## 3. Comparaison modèle vs ancien PDF

Ancien PDF :

- Mauvais format : A4 au lieu de Letter.
- Mauvais type de document : rapport standard, pas template earnings.
- Seulement 2 pages contre 14.
- Tables absentes ou perdues par conversion Markdown.
- Sections earnings manquantes ou non alignées.
- Données d'exemple du modèle non remplacées par un mapping structuré.

Audit visuel généré dans `reports/pdf-visual-diff/` :

- `model-page-*.png`
- `generated-page-*.png`
- `final-page-*.png`
- `diff-page-*.png`
- `diff-final-page-*.png`
- `side-by-side-page-*.png`
- `side-by-side-final-page-*.png`
- `pdf-analysis.json`

## 4. Corrections appliquées

- `tests/test_earnings_pdf_template.py`
  - Ajout des tests RED sur les deux templates, ordre des sections, tables et mapping.

- `tests/test_earnings_pdf_renderer.py`
  - Ajout des tests PDF Letter, texte extractible, tables et variante japonaise.

- `tests/test_earnings_deep_dive_integration.py`
  - Mise à jour du contrat : une seule langue demandée, renderer structuré, plus de `md_to_pdf` pour le deep-dive.

- `backend/earnings_deep_dive/template.py`
  - Ajout des 10 sections officielles en deux variantes `en` et `jp`.

- `backend/earnings_deep_dive/report_model.py`
  - Ajout du modèle de rendu stable.

- `backend/earnings_deep_dive/mapper.py`
  - Mapping des métriques vers tables ; calcul de variance EPS/revenue quand possible ; `DONNÉE NON DISPONIBLE` quand la donnée manque.

- `backend/earnings_deep_dive/pdf_renderer.py`
  - Renderer ReportLab dédié, format Letter, pages extractibles, tables réelles.

- `backend/earnings_deep_dive/__init__.py`
  - Exports du mapper et du renderer.

- `backend/pipeline.py`
  - Génération deep-dive selon `language`, sans génération bilingue implicite.

- `backend/main.py`
  - Normalisation `ja`/`jp`.
  - Régénération des PDF depuis les contenus traduits en copie temporaire.
  - Filtrage des sous-dossiers `en`/`jp` hors langue demandée dans le ZIP.

- `scripts/generate_sample_earnings_pdf.py`
  - Génère deux PDFs de validation sans réseau.

- `scripts/pdf_audit_extract.py`
  - Ajout de l'analyse et des rendus du PDF final.

## 5. Tests et validations

Commandes exécutées :

```powershell
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && .venv/bin/python -m pytest tests/test_earnings_pdf_template.py tests/test_earnings_pdf_renderer.py tests/test_earnings_deep_dive.py tests/test_earnings_deep_dive_integration.py -v"
```

Résultat : 20 tests passés.

```powershell
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && .venv/bin/python scripts/generate_sample_earnings_pdf.py"
```

Résultat :

- `reports/generated/final-report-en.pdf` : 46 908 octets
- `reports/generated/final-report-jp.pdf` : 56 876 octets
- `reports/generated/final-report.pdf` : 46 908 octets

```powershell
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && .venv/bin/python scripts/pdf_audit_extract.py"
```

Résultat :

- modèle : 14 pages
- ancien généré : 2 pages
- final EN : 10 pages
- final EN rendu en images Letter 1275 x 1650 px à 150 DPI.

## 6. Limites restantes

- La similarité n'est pas encore parfaite : le modèle fait 14 pages, le nouveau rendu 10 pages.
- Les polices exactes du modèle ne sont pas ajoutées car aucun asset externe n'a été téléchargé.
- Les valeurs métier absentes restent explicitement `DONNÉE NON DISPONIBLE`.
- Les PDF secondaires du ZIP en japonais dépendent de la traduction locale disponible ; sans clé de traduction configurée, le fallback conserve le texte source.
- Le modèle JP est structurellement séparé, mais les paragraphes LLM restent fournis par `generate_deep_dive` selon la langue demandée.

## 7. Actions restantes recommandées

1. Ajuster finement pagination/espacements pour viser 14 pages comme le modèle.
2. Ajouter les polices officielles au repo si licence/asset validés.
3. Étendre le modèle structuré aux autres documents du ZIP pour supprimer la dépendance aux traductions Markdown/PDF secondaires.
4. Ajouter un test ZIP dédié qui vérifie qu'un ZIP `lang=jp` ne contient pas de sous-dossier `en` ni de PDF anglais recyclé.

## 8. Mise à jour seconde passe - 2026-05-06

Corrections ajoutées :

- Le bouton Download est bloqué tant que le dossier n'est pas `ready`, `verified` et `download_enabled`.
- L'endpoint `/api/dossier/{ticker}/download` refuse aussi le ZIP côté serveur si la validation n'est pas passée.
- Le cache dossier ne peut plus annoncer un état `complete` périmé sans relire `deep_dive_validation.json`.
- Les analyses multi-tickers utilisent désormais `run_analysis_parallel`, avec exécution concurrente bornée.
- La recherche transcript ajoute un fallback Google Custom Search configurable (`GOOGLE_SEARCH_API_KEY` + `GOOGLE_SEARCH_ENGINE_ID`) après RapidAPI, Alpha Vantage, Motley Fool et l'ancien fallback public.
- Le mapper PDF privilégie les tableaux Markdown générés par Codex quand ils sont présents, au lieu de les écraser par des métriques clairsemées.
- La validation deep-dive contrôle aussi le modèle structuré envoyé au renderer PDF, pour bloquer les placeholders introduits pendant le rendu.

Validation exécutée :

- Suite backend ciblée : 39 tests passés.
- Compilation Python `compileall backend tests` via WSL : passée.

Blocages restants :

- Le smoke réel MSFT reste non conforme si aucune clé de sourcing transcript/API n'est configurée. Dans l'environnement actuel, `GOOGLE_SEARCH_API_KEY`, `GOOGLE_SEARCH_ENGINE_ID`, `RAPIDAPI_KEY`, `ALPHA_VANTAGE_API_KEY` et `FINNHUB_API_KEY` sont absents.
- Le build frontend n'a pas pu être validé : `node_modules` est incomplet côté Rollup (`@rollup/rollup-win32-x64-msvc` manquant). Une réinstallation locale des dépendances frontend est nécessaire avant validation Vite.
- Le pipeline ne doit plus permettre le download dans cet état : si des chiffres restent indisponibles ou si le transcript/source URL manque, la validation bloque le ZIP.
