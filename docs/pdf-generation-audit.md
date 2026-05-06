# Audit initial de génération PDF

Date d'audit : 2026-05-06  
Projet : `stock-analysis-pipeline`

## 1. Périmètre et état initial

### PDFs localisés

| Rôle | Fichier | Taille | Pages | Statut |
|---|---:|---:|---:|---|
| PDF modèle/template | `docs/specs/modele.pdf` | 421287 octets | 14 | Présent |
| PDF généré actuel | `docs/specs/genere.pdf` | 5257 octets | 2 | Présent |

Le fichier historique `docs/specs/Earnings Documents.pdf` apparaît supprimé dans `git status`, tandis que `docs/specs/modele.pdf` et `docs/specs/genere.pdf` sont non suivis. L'audit part donc des deux PDFs explicitement présents dans `docs/specs`, comme demandé.

### État Git constaté avant audit

Le workspace contient déjà des changements non liés à cet audit :

- Modifiés : `backend/async_dossier.py`, `backend/earnings_deep_dive/prompts.py`, `backend/pipeline.py`, `backend/sources_collector.py`, `fill_dossiers.py`, `frontend/src/components/AnalysisCard.jsx`.
- Supprimés : `.env.example`, `docs/specs/Earnings Documents.pdf`.
- Non suivis : plusieurs scripts `_*.py`, `backend/earnings_deep_dive/deep_dive_validator.py`, documents dans `docs/`, `docs/specs/gap-analysis.md`, `docs/specs/modele.pdf`, `docs/specs/genere.pdf`, `skills-starter-kit/`, `vercel.json`.

Je n'ai pas modifié ces fichiers existants pendant l'audit.

### Artefacts produits par l'audit

| Fichier / dossier | Rôle |
|---|---|
| `scripts/pdf_audit_extract.py` | Script local d'extraction texte/métadonnées/rendu PNG des PDFs |
| `reports/pdf-visual-diff/pdf-analysis.json` | Métadonnées, blocs texte, polices/couleurs détectées, métriques de diff |
| `reports/pdf-visual-diff/model-text.txt` | Texte extrait du modèle |
| `reports/pdf-visual-diff/generated-text.txt` | Texte extrait du PDF généré |
| `reports/pdf-visual-diff/model-page-*.png` | Pages du modèle rendues à 150 DPI |
| `reports/pdf-visual-diff/generated-page-*.png` | Pages du PDF généré rendues à 150 DPI |
| `reports/pdf-visual-diff/diff-page-*.png` | Diff visuel pages 1 et 2 |
| `reports/pdf-visual-diff/side-by-side-page-*.png` | Comparaison côte à côte pages 1 et 2 |

## 2. Stack et génération PDF identifiées

### Stack principale

- Backend : Python 3.11+ / FastAPI / Pydantic v2.
- Frontend : React + Vite.
- Tests : pytest.
- PDF principal : ReportLab via `backend/pdf_generator.py`.
- Conversion 10-K HTML -> PDF : WeasyPrint via `backend/tenk_pdf.py`.
- Extraction/rendu PDF d'audit : PyMuPDF (`fitz`) + Pillow, disponibles dans le venv WSL du projet.

### Librairies PDF dans le projet

| Librairie | Usage détecté | Fichier |
|---|---|---|
| ReportLab | Génération `report.pdf` et conversion Markdown -> PDF simple | `backend/pdf_generator.py` |
| WeasyPrint | Conversion HTML 10-K vers PDF | `backend/tenk_pdf.py` |
| PyMuPDF | Utilisé seulement par l'audit ajouté | `scripts/pdf_audit_extract.py` |

## 3. Architecture du pipeline PDF

### Rapport standard actuel

Flux observé :

1. Endpoints FastAPI dans `backend/main.py`.
2. Analyse ticker via `backend/pipeline.py`.
3. Collecte de données dans `backend/sources_collector.py` :
   - yfinance ;
   - Finnhub ;
   - SEC EDGAR ;
   - caches locaux ;
   - transcripts via modules dédiés.
4. Construction d'un `AnalysisResult` dans `backend/models.py`.
5. Génération Markdown standard par `_generate_report(...)` dans `backend/pipeline.py`.
6. Conversion Markdown -> PDF via `backend.pdf_generator.md_to_pdf(...)`.
7. Sorties attendues :
   - `07_final_report/report.md`
   - `07_final_report/report.pdf`
   - éventuellement `07_final_report/earnings_deep_dive.md`
   - éventuellement `07_final_report/earnings_deep_dive.pdf`

### Deep-dive earnings

Flux observé :

1. `backend/pipeline.py::_add_earnings_deep_dive_if_transcript(...)`
2. Recherche transcript via `backend.transcript_finder.find_transcripts(...)`
3. Mapping données -> `FinancialMetrics` via `backend/pipeline.py::_deep_dive_metrics(...)`
4. Génération section par section via `backend/earnings_deep_dive/generator.py`
5. Prompts alignés modèle via `backend/earnings_deep_dive/prompts.py`
6. Assemblage Markdown via `backend/earnings_deep_dive/markdown.py::assemble_final_report(...)`
7. Conversion Markdown -> PDF via `backend.pdf_generator.md_to_pdf(...)`

Point important : `generator.py` importe actuellement `backend.codex_provider._codex_chat as kimi_chat`, mais les noms d'erreur et métadonnées parlent encore de Kimi (`KimiFailureError`, `provider: "Kimi K2.6"`). C'est une incohérence de lisibilité/traçabilité.

## 4. Fichiers clés

| Fichier | Rôle |
|---|---|
| `backend/pdf_generator.py` | Générateur PDF ReportLab ; contient `generate_pdf(...)` et `md_to_pdf(...)` |
| `backend/pipeline.py` | Orchestration analyse, dossier, deep-dive, mapping metrics, génération des rapports |
| `backend/main.py` | Endpoints de téléchargement, génération dossier, génération rapport PDF |
| `backend/models.py` | DTOs de l'analyse standard |
| `backend/earnings_deep_dive/schemas.py` | DTOs deep-dive (`FinancialMetrics`, `DeepDiveRequest`, etc.) |
| `backend/earnings_deep_dive/prompts.py` | Ordre des sections, intitulés, questions EN/JP, exigences de tables |
| `backend/earnings_deep_dive/generator.py` | Génération LLM section par section, validation, sauvegarde Markdown/meta |
| `backend/earnings_deep_dive/markdown.py` | Assemblage final Markdown |
| `backend/earnings_deep_dive/validators.py` | Validateurs de heading, table, répétition, langue |
| `backend/transcript_finder.py` | Recherche transcripts |
| `backend/rapidapi_sa.py`, `backend/alpha_vantage.py`, `backend/seeking_alpha.py` | Sources transcripts |
| `tests/test_earnings_deep_dive.py` | Tests unitaires deep-dive |
| `tests/test_earnings_deep_dive_integration.py` | Tests intégration pipeline/deep-dive/PDF call |
| `docs/specs/modele.pdf` | Référence visuelle et documentaire |
| `docs/specs/genere.pdf` | Ancien PDF généré à comparer |
| `docs/specs/earnings-deep-dive-spec*.md` | Spécification textuelle dérivée du PDF modèle |
| `docs/specs/gap-analysis.md` | Écarts déjà listés avant cet audit |

## 5. Comparaison PDF modèle vs PDF généré

### Résumé factuel

| Critère | Modèle | Généré actuel | Écart |
|---|---|---|---|
| Nombre de pages | 14 | 2 | Critique |
| Taille page | 612 x 792 pt (Letter) | 595.28 x 841.89 pt (A4) | Critique |
| Police principale détectée | Arial / Arial Bold / MS-PGothic | Helvetica / Helvetica-Bold / Symbol / ZapfDingbats | Majeur |
| Type de document | Template earnings avec questions, exemples et tableaux | Rapport stock analysis standard MSFT | Critique |
| Société/exemple principal | GEV, Apple, SanDisk exemples | Microsoft Corporation (MSFT) | Critique si `genere.pdf` est censé valider le modèle |
| Structure | Questions earnings + sections exemples sur 14 pages | 9 sections standard : Executive Summary, Financial Data, Business, etc. | Critique |
| Tables | Tables visibles dès page 1, nombreuses sections tabulaires | Presque tout en bullets Markdown ; pas de vraies tables dans le rendu | Critique |
| Couleurs | Questions en rouge foncé, valeurs positives vertes, texte noir | Titres bleus, texte noir, bullets mal rendus | Majeur |
| Langue | Bilingue EN/JP dans le template | Mix EN/FR dans un rapport standard | Critique |
| Pagination | Longue pagination continue du modèle | 2 pages compactes | Critique |

### Comparaison visuelle

Artefacts :

- `reports/pdf-visual-diff/side-by-side-page-1.png`
- `reports/pdf-visual-diff/side-by-side-page-2.png`
- `reports/pdf-visual-diff/diff-page-1.png`
- `reports/pdf-visual-diff/diff-page-2.png`

Métriques automatiques :

| Page | Taille PNG modèle | Taille PNG généré | Diff moyen |
|---:|---|---|---:|
| 1 | 1275 x 1650 | 1241 x 1754 | 16.958 |
| 2 | 1275 x 1650 | 1241 x 1754 | 9.197 |

La métrique pixel n'est pas utilisée comme seuil de vérité car les documents ne partagent ni le format de page, ni la pagination, ni le type de rapport. Visuellement, les écarts sont structurels :

- modèle : mise en page type document officiel Word/PDF, marges Letter, Arial, questions en rouge, tables simples mais lisibles, japonais via MS-PGothic ;
- généré : rendu Markdown brut, A4, titres bleus, bullets avec caractères parasites (`I`/Symbol), sections d'analyse standard, pas de reproduction du template earnings.

## 6. Comparaison des données et structure

### Matrice de mapping modèle -> généré

| Élément dans le PDF modèle | Présent dans le PDF généré ? | Source actuelle identifiée | Problème détecté | Correction nécessaire |
|---|---|---|---|---|
| Page/source instructions Seeking Alpha | Non | `transcript_finder`, `rapidapi_sa`, `alpha_vantage`, `seeking_alpha` | Le rapport généré ne documente pas la collecte earnings/presentation/press release | Ajouter section source discipline au deep-dive PDF, sans inventer de liens |
| Official Website / Press Release instructions | Non | `sources_collector`, SEC/IR partiel | Pas de mapping explicite press release/IR dans le PDF généré | Ajouter champ source/IR si disponible, sinon marquer non disponible |
| EPS estimate | Non dans `genere.pdf` | `FinancialMetrics.eps_estimate`, `_deep_dive_metrics` | Le PDF standard ne l'affiche pas ; mapping deep-dive existe mais dépend des données disponibles | Générer le PDF deep-dive et tester le champ |
| EPS actual | Non dans `genere.pdf` | `FinancialMetrics.eps_actual`, yfinance quarterly data si disponible | Absent du PDF standard | Ajouter rendu tabulaire deep-dive |
| EPS vs estimate | Non | `FinancialMetrics.eps_vs_estimate` | Champ prévu mais pas garanti alimenté | Vérifier provider/mapping ; ne pas hardcoder |
| EPS YoY | Non | `FinancialMetrics.eps_yoy` | Champ prévu mais pas garanti alimenté | Vérifier provider/mapping |
| Revenue estimate | Non | `FinancialMetrics.revenue_estimate` | Champ prévu mais pas visible | Ajouter/tester table EPS & Revenue |
| Revenue actual | Partiel, sous `Quarterly Revenue` | `revenue_quarterly -> revenue_actual` | Nom et contexte différents ; pas estimate/variance/YoY comme modèle | Table dédiée conforme modèle |
| Revenue YoY | Partiel | `revenue_yoy_growth -> revenue_yoy` | Format présent en bullet standard, pas table modèle | Format table |
| Highlights | Non conforme | LLM deep-dive prompts existent | `genere.pdf` n'est pas le deep-dive | Générer/renderer `earnings_deep_dive.pdf` |
| Lowlights avec sévérité | Non | Prompts deep-dive | Absent du PDF standard | Table Highlights/Lowlights conforme |
| Operating Metrics table | Non | `FinancialMetrics` contient plusieurs champs | `md_to_pdf` saute toutes les tables Markdown ; le standard affiche bullets | Renderer les tables Markdown ou construire Platypus tables |
| Cash Flow table | Non | `operating_cash_flow`, `capex`, `free_cash_flow` | Champs partiels, non tabulaires dans `genere.pdf` | Table dédiée + fallback `DONNÉE NON DISPONIBLE` |
| Capital Efficiency ROE/ROTCE/ROA/ROIC | Non | Champs prévus dans `FinancialMetrics` | Pas dans PDF standard | Mapping + rendu table |
| Segments produit/géographie | Non | `FinancialMetrics.segments` | Structure source non garantie ; pas de renderer table nested | Définir format data -> tables produit/région |
| Forward P/E | Partiel | `ValuationData.pe_forward`, `FinancialMetrics.pe_forward` | Présent comme bullet standard, pas contexte modèle | Table modèle + contexte si sourcé |
| Backlog Quality | Non | `FinancialMetrics.backlog` | Donnée rarement disponible | Rendre conditionnel ; si absent : `DONNÉE NON DISPONIBLE` |
| Guidance | Partiel, sous `Official Guidance` | `guidance_official` / `guidance` | Format incorrect ; valeur brute ambiguë | Table guidance + normalisation |
| Verdict / overall earnings verdict | Non conforme | Prompts deep-dive + AnalysisResult decision standard | PDF standard donne décision d'investissement, pas verdict earnings modèle | Séparer verdict earnings de décision stock |
| One-line summary par section | Non | Prompts demandent blockquote | `md_to_pdf` ne rend pas un style spécifique | Ajouter style blockquote / résumé |
| EN + JP questions | Non dans `genere.pdf` | `prompts.py` sait les produire selon langue | Le PDF généré comparé n'utilise pas ce pipeline | Générer deep-dive comme sortie principale de validation |

## 7. Causes racines

### 7.1 Données

- Le PDF généré actuel compare MSFT avec un modèle qui contient des exemples GEV/AAPL/SanDisk. La comparaison de valeurs exactes ne peut pas être conforme tant que le scénario de validation n'est pas déterministe.
- Plusieurs champs nécessaires au template existent dans `FinancialMetrics`, mais leur alimentation dépend de `yf_data["financials"]` et de `AnalysisResult.financials`. Les champs estimates, segments, backlog, guidance détaillée et historiques YoY ne semblent pas garantis.
- Le modèle demande des sources Seeking Alpha / présentation / press release. Le pipeline sait chercher des transcripts, mais le PDF généré ne rend pas une matrice de sources comparable au modèle.
- Règle à respecter : toute donnée absente doit être rendue comme `DONNÉE NON DISPONIBLE`, pas inventée ni calculée sans base.

### 7.2 Template

- `genere.pdf` n'est pas le même type de document que `modele.pdf`. Il s'agit d'un rapport standard "AI Analysis", pas d'un deep-dive earnings aligné Nami.
- Les prompts deep-dive contiennent déjà une partie de la structure, mais la sortie PDF réelle passe par `md_to_pdf`, qui est un convertisseur Markdown très simple.
- `md_to_pdf` ignore explicitement les tables Markdown (`elif stripped.startswith("|"): continue`). C'est incompatible avec le modèle, qui repose lourdement sur les tableaux.
- L'assemblage `assemble_final_report` ajoute seulement un titre global, warnings, sections et source discipline. Il ne porte pas de logique de pagination ou de styles modèle.

### 7.3 Style

- Modèle : format Letter, Arial/MS-PGothic, questions en rouge foncé, valeurs positives vertes, tables sans style complexe, hiérarchie Word-like.
- Généré : A4, Helvetica, headings bleus, Markdown brut, caractères parasites pour bullets/emoji.
- ReportLab standard ne rend pas correctement certains caractères/emoji avec Helvetica/Symbol/ZapfDingbats.
- Aucun style spécifique pour questions EN/JP, tables, exemples, résumé final, source discipline.

### 7.4 Pagination

- Modèle : 14 pages, format Letter, grands blocs continus.
- Généré : 2 pages A4.
- Aucun contrôle identifié sur :
  - sauts avant/après sections earnings ;
  - répétition d'en-têtes de table ;
  - maintien des lignes de table ;
  - page footer/header spécifique au modèle.

### 7.5 Assets

- Aucun logo ou asset externe requis visible dans la page 1 du modèle.
- Les polices exactes détectées dans le modèle sont Arial et MS-PGothic. Le pipeline ReportLab utilise Helvetica par défaut.
- Il faudra vérifier si les polices Arial/MS-PGothic sont légalement et techniquement disponibles dans l'environnement de génération. Sans elles, l'objectif réaliste est une police métriquement proche.

### 7.6 Architecture

- Deux pipelines se superposent : rapport standard et deep-dive earnings. Le fichier `genere.pdf` fourni semble venir du pipeline standard, pas du pipeline deep-dive attendu.
- La génération visuelle est trop couplée à un convertisseur Markdown minimal.
- Les validations actuelles vérifient surtout la présence des sections/tables dans le Markdown généré, pas le rendu PDF final.
- Le provider est confus : import Codex sous alias `kimi_chat`, erreurs et métadonnées encore nommées Kimi.
- Les tests d'intégration mockent `md_to_pdf` en écrivant `b"pdf"` ; ils ne valident donc ni PDF réel, ni texte extrait, ni tables, ni pagination.

## 8. Problèmes évidents détectés

| Sévérité | Problème | Preuve | Impact |
|---|---|---|---|
| Critique | Le PDF généré actuel n'est pas le rapport earnings template | `generated-text.txt` commence par `Microsoft Corporation (MSFT) — AI Analysis` | Impossible d'atteindre la similarité en ajustant seulement les marges |
| Critique | Les tables Markdown sont supprimées en PDF | `backend/pdf_generator.py`, `md_to_pdf`, branche `stripped.startswith("|")`: skip | Toutes les sections tabulaires du modèle disparaissent |
| Critique | Page size différente | Modèle 612 x 792 pt, généré 595.28 x 841.89 pt | Pagination et alignements incompatibles |
| Majeur | Police différente | Modèle Arial/MS-PGothic ; généré Helvetica/Symbol/ZapfDingbats | Rendu visuel très éloigné et caractères parasites |
| Majeur | Tests PDF insuffisants | tests mockent `md_to_pdf` avec `b"pdf"` | Régression visuelle non détectée |
| Majeur | Incohérence provider Codex/Kimi | `generator.py` importe Codex en alias `kimi_chat`, meta indique Kimi | Traçabilité et diagnostic difficiles |
| Majeur | Données modèle non déterministes dans validation | Modèle exemples GEV/AAPL/SanDisk, généré MSFT live | Impossible de comparer valeurs sans fixture/scénario |

## 9. Hypothèses à vérifier avant correction

| Faits vérifiés | Hypothèses à vérifier |
|---|---|
| `modele.pdf` est un template/spec earnings de 14 pages | Le PDF final attendu doit probablement être `earnings_deep_dive.pdf`, pas `report.pdf` |
| `genere.pdf` est un rapport standard MSFT de 2 pages | `genere.pdf` a peut-être été généré par `/api/report/{ticker}/pdf` ou par `report.md`, pas par le deep-dive |
| `prompts.py` encode déjà les 10 sections du modèle | Le Markdown deep-dive actuel est peut-être plus proche que `genere.pdf`, mais son PDF perd tables/style |
| `md_to_pdf` ignore les tables Markdown | Corriger le renderer peut améliorer fortement le contenu, mais pas suffire pour la pagination 14 pages |
| Les tests deep-dive ne valident pas un PDF réel | Un test PDF réel peut être ajouté avec ReportLab + extraction PyMuPDF si dispo dans CI/dev |

## 10. Commandes exécutées

```powershell
git status --short
Get-ChildItem -LiteralPath '.\docs\specs' -Recurse -File -Force
Get-Content -Raw -LiteralPath '.\COMMANDS.md'
Get-Content -Raw -LiteralPath '.\requirements.txt'
Get-Content -Raw -LiteralPath '.\backend\pdf_generator.py'
Get-Content -Raw -LiteralPath '.\backend\earnings_deep_dive\markdown.py'
Get-Content -Raw -LiteralPath '.\backend\earnings_deep_dive\schemas.py'
Get-Content -Raw -LiteralPath '.\docs\specs\earnings-deep-dive-spec.md'
Get-Content -Raw -LiteralPath '.\docs\specs\earnings-deep-dive-spec-fr.md'
Get-Content -Raw -LiteralPath '.\docs\specs\gap-analysis.md'
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && .venv/bin/python scripts/pdf_audit_extract.py"
```

## 11. Recommandation de correction

Ne pas commencer par ajuster `genere.pdf` tel quel. La priorité doit être :

1. Décider que la sortie cible du template est `earnings_deep_dive.pdf`.
2. Ajouter des tests RED sur le rendu PDF réel :
   - tables Markdown conservées ;
   - page size Letter si modèle confirmé ;
   - présence des sections clés ;
   - texte extrait contenant EPS & Revenue, Highlights/Lowlights, Operating Metrics, Cash Flow, Guidance, Verdict ;
   - absence de caractères parasites de bullets.
3. Remplacer ou spécialiser `md_to_pdf` pour le deep-dive :
   - parser les tables Markdown ;
   - rendre des `Table` ReportLab ;
   - appliquer styles proches du modèle ;
   - gérer questions, exemples, résumés, spacing ;
   - contrôler la pagination.
4. Ajouter une fixture déterministe de deep-dive si le projet n'en a pas déjà une, pour ne pas dépendre de données live ou du LLM.
5. Documenter les données indisponibles explicitement avec `DONNÉE NON DISPONIBLE`.

Le prochain livrable avant correction doit être `docs/pdf-generation-fix-plan.md`.
