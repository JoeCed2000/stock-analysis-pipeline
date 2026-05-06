# Plan de correction du pipeline PDF

Date : 2026-05-06  
Objectif : produire un rapport earnings deep-dive généré proprement, très proche du PDF modèle `docs/specs/modele.pdf`, quel que soit le ticker analysé.

## Mise à jour langue / ZIP

La correction doit désormais traiter la langue comme une dimension structurante du pipeline, pas comme une traduction après coup.

Décision :

- créer deux templates exécutables séparés : `en` et `jp` ;
- générer le rapport earnings deep-dive depuis le template correspondant à la langue demandée ;
- éviter un PDF bilingue par défaut : le ZIP final doit contenir des documents cohérents avec la langue choisie ;
- conserver les mêmes clés de sections métier dans les deux langues pour permettre un mapping stable ;
- traduire les titres, questions, libellés de colonnes et résumés dans la variante `jp` ;
- garder les données financières identiques entre langues, sauf formatage explicitement dépendant de la langue ;
- documenter que les documents secondaires du ZIP doivent suivre le même paramètre `lang` dans le branchement pipeline.

Tests ajoutés :

- `test_template_has_distinct_english_and_japanese_variants`
- `test_pdf_renderer_generates_language_specific_japanese_report`

Critère d'acceptation supplémentaire :

- un appel `language="en"` ne doit produire que le template anglais ;
- un appel `language="jp"` doit produire le template japonais ;
- aucun document du ZIP final ne doit être généré en anglais si `lang=jp`, sauf donnée brute externe non traduisible ou nom propre.

## 1. Décision d'architecture

Le PDF cible ne doit pas être le rapport standard `report.pdf`. Le template de référence est le PDF earnings `modele.pdf`.

La correction doit donc créer un pipeline dédié :

```text
FinancialMetrics + transcript + sources
        |
        v
Template canonique earnings avec placeholders
        |
        v
Sections structurées déterministes
        |
        v
Renderer PDF ReportLab dédié au deep-dive
        |
        v
07_final_report/earnings_deep_dive.pdf
```

Principe retenu :

- partir de la structure du modèle original ;
- conserver les mêmes sections, titres, questions, tables, ordre, hiérarchie, couleurs et pagination cible ;
- remplacer les exemples GEV/AAPL/SanDisk par les données du vrai ticker ;
- ne jamais hardcoder silencieusement des valeurs métier ;
- remplir les trous par `DONNÉE NON DISPONIBLE` quand la donnée n'est pas sourcée ;
- générer du vrai texte et de vraies tables PDF, pas une capture d'écran du modèle.

## 2. Corrections à faire

### 2.1 Créer un modèle de document canonique

Fichiers concernés :

- Créer `backend/earnings_deep_dive/template.py`
- Modifier `backend/earnings_deep_dive/schemas.py`
- Modifier `backend/earnings_deep_dive/markdown.py` si besoin

Responsabilité :

- Définir les 10 sections officielles du modèle.
- Pour chaque section :
  - titre ;
  - question EN ;
  - question JP ;
  - colonnes attendues ;
  - lignes attendues ;
  - blocs d'analyse attendus ;
  - résumé final attendu ;
  - caractère conditionnel éventuel, par exemple backlog.

Structure cible proposée :

```python
@dataclass(frozen=True)
class ReportSectionTemplate:
    key: str
    title: str
    question_en: str
    question_jp: str
    table_columns: tuple[str, ...]
    table_rows: tuple[str, ...]
    analysis_blocks: tuple[str, ...]
    summary_label: str
    required: bool = True
```

Pourquoi :

- Le template doit être une spécification exécutable, pas seulement des prompts LLM.
- Les tests pourront vérifier que toutes les sections du modèle sont présentes.
- Le renderer PDF pourra utiliser cette structure sans parser du Markdown fragile.

### 2.2 Créer un DTO de rendu déterministe

Fichiers concernés :

- Modifier `backend/earnings_deep_dive/schemas.py`
- Créer `backend/earnings_deep_dive/report_model.py`

Responsabilité :

- Transformer les données disponibles en modèle de rendu stable :
  - `EarningsDeepDiveReport`
  - `RenderedSection`
  - `RenderedTable`
  - `RenderedTableRow`
  - `SourceRef`

Exemple de forme :

```python
class RenderedTableRow(BaseModel):
    cells: list[str]
    source: str = "DONNÉE NON DISPONIBLE"

class RenderedSection(BaseModel):
    key: str
    title: str
    question_en: str
    question_jp: str
    table: RenderedTable
    analysis: list[str]
    nami_takeaway: str
    one_line_summary: str

class EarningsDeepDiveReport(BaseModel):
    ticker: str
    company: str
    quarter: str
    generated_at: str
    sections: list[RenderedSection]
    sources: list[SourceRef]
```

Pourquoi :

- Éviter que le PDF dépende directement d'un Markdown LLM non structuré.
- Permettre des tests de mapping simples.
- Rendre le PDF reproductible même quand le LLM est indisponible ou incomplet.

### 2.3 Mapper les données métier vers les placeholders du modèle

Fichiers concernés :

- Créer `backend/earnings_deep_dive/mapper.py`
- Modifier `backend/pipeline.py::_deep_dive_metrics(...)`
- Modifier ou compléter `backend/earnings_deep_dive/generator.py`

Mapping prioritaire :

| Placeholder modèle | Source actuelle attendue | Règle |
|---|---|---|
| Ticker | `DeepDiveRequest.ticker` | Toujours disponible |
| Company | `DeepDiveRequest.company` ou ticker | Fallback ticker |
| Quarter | transcript quarter ou request quarter | Pas de date inventée |
| EPS estimate | `FinancialMetrics.eps_estimate` | Sinon `DONNÉE NON DISPONIBLE` |
| EPS actual | `FinancialMetrics.eps_actual` | Sinon `DONNÉE NON DISPONIBLE` |
| EPS vs estimate | `FinancialMetrics.eps_vs_estimate` | Calcul seulement si estimate + actual disponibles |
| EPS YoY | `FinancialMetrics.eps_yoy` | Sinon indisponible |
| Revenue estimate | `FinancialMetrics.revenue_estimate` | Sinon indisponible |
| Revenue actual | `FinancialMetrics.revenue_actual` | Fallback actuel : `revenue_quarterly` |
| Revenue YoY | `FinancialMetrics.revenue_yoy` | Fallback actuel : `revenue_yoy_growth` |
| Gross profit | `FinancialMetrics.gross_profit` | Sinon indisponible |
| Gross margin | `FinancialMetrics.gross_margin` | Format % |
| OpEx | `FinancialMetrics.opex` | Sinon indisponible |
| Operating income | `FinancialMetrics.operating_income` | Sinon indisponible |
| Operating margin | `FinancialMetrics.operating_margin` | Format % |
| Net income | `FinancialMetrics.net_income` | Format montant |
| OCF | `FinancialMetrics.operating_cash_flow` | Sinon indisponible |
| CapEx | `FinancialMetrics.capex` | Sinon indisponible |
| FCF | `FinancialMetrics.free_cash_flow` | Sinon indisponible |
| ROE | `FinancialMetrics.roe` | Format % |
| ROTCE/ROTE | `FinancialMetrics.rotce` | Sinon indisponible |
| ROA | `FinancialMetrics.roa` | Sinon indisponible |
| ROIC | `FinancialMetrics.roic` | Sinon indisponible |
| Segments | `FinancialMetrics.segments` | Normaliser produit/région si disponible |
| Forward P/E | `FinancialMetrics.pe_forward` | Format `x` |
| Backlog | `FinancialMetrics.backlog` | Section conditionnelle mais présente avec indisponible |
| Guidance | `FinancialMetrics.guidance` | Ne pas confondre pourcentage brut et guidance textuelle |
| Transcript source | `transcript_url` / `transcript_meta` | Cité dans sources |

Règles de sécurité données :

- Aucune valeur exemple du modèle ne doit survivre dans un rapport ticker réel.
- Si la donnée manque : `DONNÉE NON DISPONIBLE`.
- Si un calcul est possible, il doit être traçable et testé.
- Aucun appel externe nouveau sans autorisation.

### 2.4 Créer un renderer PDF deep-dive dédié

Fichiers concernés :

- Créer `backend/earnings_deep_dive/pdf_renderer.py`
- Modifier `backend/pipeline.py::_add_earnings_deep_dive_if_transcript(...)`
- Modifier éventuellement `backend/pdf_generator.py` uniquement pour helpers partagés, sans casser `report.pdf`

Responsabilité :

- Générer `earnings_deep_dive.pdf` directement depuis `EarningsDeepDiveReport`.
- Ne pas utiliser `md_to_pdf` pour ce rapport.
- Utiliser ReportLab Platypus avec :
  - page size `LETTER` pour correspondre au modèle (`612 x 792 pt`) ;
  - marges proches du modèle : environ 72 pt gauche/droite/top sur page 1 ;
  - police Arial si disponible, fallback Helvetica ;
  - police JP compatible si disponible, fallback documenté ;
  - questions en rouge foncé ;
  - titres section noirs ou rouges selon modèle ;
  - valeurs positives en vert ;
  - tables avec colonnes alignées et répétition d'en-tête ;
  - `keepWithNext`, `splitByRow`, `repeatRows=1` selon tables ;
  - footer/page number si nécessaire, mais modèle actuel ne montre pas de footer fort sur page 1.

Ne pas transformer le PDF en image.

### 2.5 Garder le Markdown comme artefact secondaire

Fichiers concernés :

- `backend/earnings_deep_dive/markdown.py`
- `backend/earnings_deep_dive/generator.py`

Responsabilité :

- Conserver `earnings_deep_dive.md` pour audit humain.
- Mais la fidélité PDF doit venir du modèle structuré + renderer dédié.
- Le Markdown LLM peut enrichir les paragraphes d'analyse, pas définir la structure.

### 2.6 Améliorer la génération LLM sans lui confier la mise en page

Fichiers concernés :

- `backend/earnings_deep_dive/generator.py`
- `backend/earnings_deep_dive/prompts.py`

Responsabilité :

- Le LLM peut produire :
  - commentaires d'analyse ;
  - lowlights/highlights ;
  - synthèse Nami ;
  - one-line summary.
- Le LLM ne doit pas être responsable des tables critiques.
- Les tables sont construites par mapper déterministe depuis les metrics.

Pourquoi :

- Le modèle exige une structure stable.
- Les données financières doivent rester auditables.
- Le PDF doit être reproductible quel que soit le ticker.

### 2.7 Corriger la traçabilité provider

Fichiers concernés :

- `backend/earnings_deep_dive/generator.py`
- `backend/earnings_deep_dive/errors.py`
- `backend/earnings_deep_dive/validators.py`

Responsabilité :

- Renommer l'alias `kimi_chat` si le provider réel est Codex.
- Ou revenir à `backend.kimi_provider.kimi_chat` si c'est la décision produit.
- Mettre `provider` dans le meta JSON à la valeur réelle.

Risque :

- Changement fonctionnel possible si le provider change réellement.
- À faire après les tests structurels, pas en premier.

## 3. Ordre de modification

### Phase 1 : Tests RED sur la structure attendue

Fichiers :

- Créer `tests/test_earnings_pdf_template.py`
- Créer `tests/test_earnings_pdf_renderer.py`

Tests RED :

1. `test_template_contains_all_model_sections_in_order`
   - vérifie les 10 sections du modèle dans l'ordre exact.
2. `test_mapper_replaces_examples_with_requested_ticker`
   - fixture ticker `MSFT`, company `Microsoft Corporation` ;
   - le modèle de rendu ne doit contenir ni `GEV`, ni `GE Vernova`, ni les valeurs exemples `$17.44`, `$111.18B`, `SanDisk`.
3. `test_mapper_uses_donnee_non_disponible_for_missing_metrics`
   - metrics vides ;
   - tables remplies avec `DONNÉE NON DISPONIBLE`, jamais cellules vides.
4. `test_pdf_renderer_generates_extractable_text_and_tables`
   - génère un PDF temporaire ;
   - extrait texte avec PyMuPDF si disponible ;
   - vérifie `EPS & Revenue`, `Highlights`, `Operating Metrics`, `Cash Flow`, `Guidance`, `Verdict`.
5. `test_pdf_renderer_uses_letter_page_size`
   - vérifie page `612 x 792 pt`.

Commande ciblée :

```powershell
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && .venv/bin/python -m pytest tests/test_earnings_pdf_template.py tests/test_earnings_pdf_renderer.py -v"
```

Résultat attendu RED :

- échec par modules/fonctions inexistants.

### Phase 2 : Implémenter template + DTO + mapper

Fichiers :

- Créer `backend/earnings_deep_dive/template.py`
- Créer `backend/earnings_deep_dive/report_model.py`
- Créer `backend/earnings_deep_dive/mapper.py`
- Modifier `backend/earnings_deep_dive/__init__.py`

Objectif :

- Faire passer les tests de structure/mapping.
- Ne pas toucher encore au pipeline global.

### Phase 3 : Implémenter renderer PDF dédié

Fichiers :

- Créer `backend/earnings_deep_dive/pdf_renderer.py`
- Modifier tests renderer.

Objectif :

- Générer un PDF réel extractible.
- Page size Letter.
- Tables visibles/extractibles.
- Style proche modèle page 1.

### Phase 4 : Brancher le renderer dans le pipeline

Fichiers :

- Modifier `backend/pipeline.py::_add_earnings_deep_dive_if_transcript(...)`
- Modifier `backend/earnings_deep_dive/generator.py` si nécessaire pour exposer le report model.

Objectif :

- `earnings_deep_dive.pdf` ne passe plus par `md_to_pdf`.
- `report.pdf` standard reste inchangé.

### Phase 5 : Génération de validation locale

Créer un script si nécessaire :

- Créer `scripts/generate_sample_earnings_pdf.py`

Objectif :

- Générer un PDF déterministe sans endpoint externe, à partir d'une fixture locale.
- Sortie :
  - `reports/generated/final-report.pdf`
  - `reports/pdf-visual-diff/final-page-*.png`
  - comparaison contre `modele.pdf`.

### Phase 6 : Rapport final

Fichier :

- Créer `docs/pdf-generation-final-report.md`

Contenu :

- état initial ;
- état final ;
- fichiers modifiés ;
- tests ;
- commandes ;
- niveau de conformité ;
- limites restantes.

## 4. Tests à ajouter ou renforcer

| Test | Type | Objectif |
|---|---|---|
| `test_template_contains_all_model_sections_in_order` | Unit | Verrouiller la structure officielle |
| `test_template_tables_match_model_expectations` | Unit | Verrouiller colonnes/lignes attendues |
| `test_mapper_replaces_examples_with_requested_ticker` | Unit | Empêcher fuite des exemples modèle |
| `test_mapper_uses_donnee_non_disponible_for_missing_metrics` | Unit | Empêcher cellules vides/invention |
| `test_mapper_computes_variance_only_when_inputs_available` | Unit | Calculs auditables |
| `test_pdf_renderer_generates_extractable_text_and_tables` | Integration | PDF réel, texte exploitable |
| `test_pdf_renderer_uses_letter_page_size` | Integration | Pagination/format modèle |
| `test_pipeline_uses_deep_dive_pdf_renderer` | Integration | Ne plus passer par `md_to_pdf` pour deep-dive |
| `test_visual_audit_script_outputs_pngs` | Script/integration léger | Validation assistée |

## 5. Critères d'acceptation

### Contenu

- Le PDF final contient les 10 sections du modèle dans le bon ordre.
- Les exemples du modèle sont remplacés par le ticker réel.
- Les tables critiques existent :
  - EPS & Revenue ;
  - Highlights/Lowlights ;
  - Operating Metrics ;
  - Cash Flow ;
  - Capital Efficiency ;
  - Segments ;
  - Forward P/E ;
  - Backlog ;
  - Guidance ;
  - Verdict.
- Aucune cellule critique n'est vide.
- Les données absentes sont explicitement `DONNÉE NON DISPONIBLE`.

### Visuel

- Format page Letter `612 x 792 pt`.
- Rendu en police proche Arial ; JP lisible si police disponible.
- Questions EN/JP avec style proche du modèle.
- Tables alignées, lisibles, sans suppression des lignes.
- Couleurs principales proches :
  - rouge foncé pour questions ;
  - vert pour valeurs positives ;
  - noir pour corps ;
  - gris discret pour notes.
- Pagination significativement plus proche du modèle que l'ancien `genere.pdf`.

### Technique

- `report.pdf` standard n'est pas cassé.
- `earnings_deep_dive.pdf` est généré par le renderer dédié.
- Tests ciblés passent.
- Suite pytest pertinente passe.
- Script d'audit visuel régénère les PNG.

## 6. Risques

| Risque | Impact | Mitigation |
|---|---|---|
| Police Arial/MS-PGothic indisponible en production | Différences visuelles | Fallback documenté, ne pas bloquer la génération |
| Données estimates/guidance/backlog absentes | Tables incomplètes | `DONNÉE NON DISPONIBLE`, sources explicites |
| Segments non normalisés selon provider | Tables produit/région pauvres | Normaliseur défensif, tests fixtures |
| ReportLab gère mal certains emojis | Caractères parasites | Utiliser libellés texte + symboles compatibles, ou fallback sans casser |
| Trop de dépendance au LLM | Non-déterminisme | Tables et structure déterministes, LLM seulement pour commentaires |
| Le modèle est un document d'exemples, pas un template strict | Ambiguïtés | Conserver structure, remplacer valeurs exemples, documenter limites |
| Workspace déjà sale | Risque d'écraser travail existant | Changements ciblés, pas de revert, git status avant/après |

## 7. Stratégie de validation

Commandes prévues :

```powershell
# Tests ciblés deep-dive PDF
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && .venv/bin/python -m pytest tests/test_earnings_pdf_template.py tests/test_earnings_pdf_renderer.py tests/test_earnings_deep_dive.py tests/test_earnings_deep_dive_integration.py -v"

# Génération fixture déterministe
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && .venv/bin/python scripts/generate_sample_earnings_pdf.py"

# Audit visuel
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && .venv/bin/python scripts/pdf_audit_extract.py"
```

Puis vérifier :

- `reports/generated/final-report.pdf` existe et taille > 10 Ko.
- Texte extractible contient les sections clés.
- `reports/pdf-visual-diff/` contient les PNG de comparaison.
- `docs/pdf-generation-final-report.md` liste les écarts restants.

## 8. Hors périmètre sans confirmation

- Télécharger des polices, logos ou assets externes.
- Appeler Seeking Alpha, Finnhub, yfinance ou autre endpoint externe pour générer une fixture.
- Transformer le PDF final en image.
- Réécrire tout le pipeline standard `report.pdf`.
- Supprimer les fichiers existants ou nettoyer le workspace sale.

## 9. Prochaine action d'implémentation

Commencer par les tests RED :

1. `tests/test_earnings_pdf_template.py`
2. `tests/test_earnings_pdf_renderer.py`

Puis implémenter :

1. `backend/earnings_deep_dive/template.py`
2. `backend/earnings_deep_dive/report_model.py`
3. `backend/earnings_deep_dive/mapper.py`
4. `backend/earnings_deep_dive/pdf_renderer.py`

Ensuite seulement brancher `backend/pipeline.py`.
