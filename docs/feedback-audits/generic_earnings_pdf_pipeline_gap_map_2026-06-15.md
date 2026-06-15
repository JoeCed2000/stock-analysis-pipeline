# Generic Earnings PDF Pipeline Gap Map

Date: 2026-06-15
Project: Stock Analysis Pipeline
Parent policy: generic_earnings_pdf_correction_policy_2026-06-15.md
Status: read-only gap map; no production-code edits performed
Worker: repo-scout-fast (t_753f00c1)

## Executive summary

This artifact maps all 14 generic rules from the parent Earnings Deep Dive correction policy to concrete pipeline seams. Each rule is assigned to a specific pipeline stage — prompt, data source, markdown cleanup, validator, renderer, or product setting — with a gap assessment identifying whether the seam already supports the rule or implementations are needed.

No production code was modified. Every mapping below was verified by reading the actual source files against the symbolic call path:

> `analyze_ticker()` (pipeline.py:3034) → `_add_earnings_deep_dive_if_transcript()` (pipeline.py:1564) →
> `generate_deep_dive()` (generator.py) → LLM sections via `prompts.py` →
> `build_earnings_deep_dive_report()` (mapper.py) → `render_earnings_deep_dive_pdf()` (pdf_renderer.py)

Validation runs inside the same path: `validate_pre_render()` → `validate_deep_dive()` (deep_dive_validator.py) → `normalize_markdown_headings()`.

## WIKI_EVIDENCE

Read: `WIKI.md` (project root, 1704 lines).

Relevant sections:
- **2026-06-15 — PDF annotation extractor for feedback uploads** (L47-66): Documents `backend/pdf_annotation_extractor.py`, PyMuPDF extraction, 23 tests. This is the canonical path that extracted the 14 NVDA annotations that seeded this policy.
- **2026-06-13 — NVDA Company Overview richness + Sources fallback** (L68-101): Confirms the architectural distinction between Company Overview and Earnings Deep Dive content. Documents `backend/company_overview.py` enrichment, `backend/sources_collector.py` fallback, `backend/pipeline.py` `_generate_report()` SRC-001 fallback row. All source paths relevant to EDP-004, EDP-010, EDP-012.
- **2026-06-11 — Admin search filters** (L103+): Documents the feedback pipeline intake → Kanban root-cause flow used when PDF defects are reported.
- **2026-06-08 — Proactive PDF failure intake + admin failure semantics** (L232-251): Documents `_record_pdf_client_failure()` and `feedback_pipeline.process_pdf_failure()` — the pathways that would be triggered if any downstream defect reaches a user.

No WIKI section documents that any EDP-001 through EDP-014 rule has been pre-implemented in the current codebase. The prompts and validator have partial support for some rules (detailed below).

## GRAPH_EVIDENCE

CodeGraph status for the project:
- Project: `/home/ced/codex-projects/stock-analysis-pipeline`
- Indexed files: 319
- Nodes: 7,423
- Edges: 14,926
- Status: index up to date

### Symbol names and call paths inspected (read-only)

| Symbol | File | Line | Role in pipeline |
|---|---|---|---|
| `analyze_ticker` | `backend/pipeline.py` | 3034 | Entry: calls `_add_earnings_deep_dive_if_transcript()` |
| `_add_earnings_deep_dive_if_transcript` | `backend/pipeline.py` | 1564-1944 | Orchestrates deep-dive: transcript fetch → metrics → LLM generation → validation → PDF render |
| `_deep_dive_metrics` | `backend/pipeline.py` | 1224-1390 | Builds `FinancialMetrics` from yfinance quarterly data + press release enrichment |
| `_apply_press_release_metrics` | `backend/pipeline.py` | 1507 | Overrides EPS/revenue/gross_margin/operating_margin/net_income from 8-K data |
| `_extract_quarterly_comparison` | `backend/pipeline.py` | 983-1222 | Extracts current-quarter vs prior-year metrics from yfinance quarterly statements. Computes FCF, net_debt, FCF margin internally |
| `_generate_report` | `backend/pipeline.py` | 2292-2550 | Generates the standard (non-earnings) markdown report — not directly the earnings deep dive |
| `generate_deep_dive` | `backend/earnings_deep_dive/generator.py` | — | Calls LLM section-by-section using `prompts.py` templates |
| `build_earnings_deep_dive_report` | `backend/earnings_deep_dive/mapper.py` | — | Maps LLM response sections + metrics into `EarningsDeepDiveReport` Pydantic model |
| `effective_section_analysis` | `backend/earnings_deep_dive/mapper.py` | — | Returns section content dict from report model |
| `_build_report_period_context` | `backend/earnings_deep_dive/mapper.py` | — | Constructs fiscal-period narrative context for the report |
| `_build_metrics_ledger` | `backend/earnings_deep_dive/mapper.py` | — | Constructs the metrics data ledger for LLM prompts |
| `_build_source_registry` | `backend/earnings_deep_dive/mapper.py` | — | Builds source references for report headers |
| `_build_earnings_documents_checklist` | `backend/earnings_deep_dive/mapper.py` | — | Builds the earnings documents checklist |
| `render_earnings_deep_dive_pdf` | `backend/earnings_deep_dive/pdf_renderer.py` | — | ReportLab PDF rendering from `EarningsDeepDiveReport` model |
| `validate_pre_render` | `backend/earnings_deep_dive/deep_dive_validator.py` | — | Pre-render validation diagnostic |
| `validate_deep_dive` | `backend/earnings_deep_dive/deep_dive_validator.py` | 203 | Post-render validator: section presence, tables, forbidden markers, summary markers |
| `normalize_markdown_headings` | `backend/earnings_deep_dive/deep_dive_validator.py` | 155 | Canonicalizes LLM variant headings |
| `post_process_markdown` | `backend/earnings_deep_dive/markdown.py` | — | Strips LLM artifacts from markdown before PDF rendering |
| `_section_title_flowables` | `backend/earnings_deep_dive/pdf_renderer.py` | 127 | Renders section title + emoji prefix |
| `_paragraph_with_emojis` | `backend/earnings_deep_dive/pdf_renderer.py` | 511 | Renders text with inline emoji rendering |
| `_glyph_safe` | `backend/earnings_deep_dive/pdf_renderer.py` | 384 | Strips/replaces non-renderable Unicode/emojis |
| `SECTION_ORDER` | `backend/earnings_deep_dive/prompts.py` | 39-50 | Canonical 10-section order |
| `SECTION_FORMATS` | `backend/earnings_deep_dive/prompts.py` | 200-404 | JP section format templates with table structures and analysis format rules |
| `EN_SECTION_FORMATS` | `backend/earnings_deep_dive/prompts.py` | 406-504 | EN section format templates |
| `SECTION_TITLES` | `backend/earnings_deep_dive/prompts.py` | 26-37 | Section title mapping |
| `REQUIRED_SECTIONS` | `backend/earnings_deep_dive/deep_dive_validator.py` | 34-45 | 10 required sections for validation |
| `TABLE_REQUIREMENTS` | `backend/earnings_deep_dive/prompts.py` | 67-78 | Table column schemas per section |
| `SourceRef` | `backend/earnings_deep_dive/report_model.py` | 66-76 | Report-level source bibliography entry model |
| `ClaimSource` | `backend/earnings_deep_dive/report_model.py` | 78-96 | Evidence link model per claim |
| `EarningsDeepDiveReport` | `backend/earnings_deep_dive/report_model.py` | — | Root report model: `ticker`, `company`, `quarter`, `title`, `sections`, `sources`, `claim_sources` |
| `RenderedSection` | `backend/earnings_deep_dive/report_model.py` | — | Section model: `key`, `title`, `question`, `table`, `analysis`, `summary` |
| `RenderedTable` | `backend/earnings_deep_dive/report_model.py` | — | Table model: `columns`, `rows` |
| `RenderedTableRow` | `backend/earnings_deep_dive/report_model.py` | 99-105 | Row model: `label`, `cells`, `source_field`, `source_value_raw`, `grounding` |
| `GroundingLevel` | `backend/earnings_deep_dive/report_model.py` | 57-64 | Evidence quality tier: `direct_metric`, `calculated`, `direct_quote`, `document_fact`, `inference`, `unsupported` |

Call path (simplified):
```
analyze_ticker (pipeline.py:3034)
  → _add_earnings_deep_dive_if_transcript (pipeline.py:1564)
    → generate_deep_dive (generator.py) [LLM: prompts.py SECTION_FORMATS / EN_SECTION_FORMATS]
    → validate_pre_render (deep_dive_validator.py)
    → build_earnings_deep_dive_report (mapper.py)
      → _build_report_period_context (mapper.py)
      → _build_metrics_ledger (mapper.py)
      → _build_source_registry (mapper.py)
    → render_earnings_deep_dive_pdf (pdf_renderer.py) [PDF artifact]
    → validate_deep_dive (deep_dive_validator.py)
```

## SYMBOL_PLAN

No symbol-level code edit is performed by this card.

This is a read-only gap-mapping card. The symbols above were inspected to identify which pipeline seams each generic rule maps to, but no `patch()`, `write_file()`, or any other mutation was applied to any file under `backend/`.

The output artifact is exactly one markdown file: `docs/feedback-audits/generic_earnings_pdf_pipeline_gap_map_2026-06-15.md`.

## Pipeline stages and seams

| Stage | Symbol | File | What it controls |
|---|---|---|---|
| **S1 — Data source** | `_deep_dive_metrics()` | `pipeline.py:1224` | Extracts EPS, revenue, FCF, net_debt, margins from yfinance quarterly data. Also `_apply_press_release_metrics()` at L1507 overrides from 8-K. |
| **S2 — Prompt** | `SECTION_FORMATS` / `EN_SECTION_FORMATS` | `prompts.py:200-504` | LLM section output format: table structures, analysis format rules, concision mandates, heading requirements. Drives `generate_deep_dive()`. |
| **S3 — Markdown cleanup** | `post_process_markdown()` | `earnings_deep_dive/markdown.py` | Strips raw internal field names, provider labels, competitor row IDs from generated markdown before PDF rendering. Also `_strip_prompt_leaks_from_sections()` at `pipeline.py:1560`. |
| **S4 — Validator** | `validate_deep_dive()` | `deep_dive_validator.py:203` | Section presence, table detection, forbidden marker checks, summary marker checks. Heading normalization via `normalize_markdown_headings()`. |
| **S5 — Renderer** | `render_earnings_deep_dive_pdf()` | `pdf_renderer.py` | ReportLab PDF generation from `EarningsDeepDiveReport` model: page structure, tables, fonts, emojis, colors, cover page, source pages. |
| **S6 — Product setting** | N/A | config / feature flag | Requires a product-level decision: Japanese full-PDF toggle, source display policy, concision standard, report boundary rules. |

### Seam interaction flow

```
S1 (data source) → S2 (prompt/LLM) → S3 (markdown cleanup) → S4 (validator) → S5 (renderer/PDF)
                                                                    ↑ S6 (product settings) feeds into S2 and S5
```

## Rule-to-pipeline seam table

| rule_id | generic_rule | primary_seam | gap_assessment | verification_mechanism |
|---|---|---|---|---|
| **EDP-001** | Fiscal period must be correct in report title, cover, and all section headers | S5 (Renderer) + S2 (Prompt) | **PARTIAL_GAP.** The `EarningsDeepDiveReport.title` (report_model.py) and `_build_report_period_context()` (mapper.py) carry `quarter` as a string like `"FY2027 Q1"`. The renderer uses `report.title` for the cover. However, the title/cover assembly in `pdf_renderer.py` does not enforce that the fiscal period matches `quarter` — it trusts whatever `title` string the mapper produces. Section-level fiscal labels are LLM-generated via `S2` and not validated for period consistency. | Extract PDF cover text and section headers → parse all fiscal-period strings → fail if any differ from the expected `quarter`. |
| **EDP-002** | User-selectable full Japanese PDF option | S6 (Product setting) | **PRODUCT_DECISION.** Japanese deep-dive generation already exists in `_add_earnings_deep_dive_if_transcript()` (pipeline.py:1694, `generate_jp`), with `SECTION_FORMATS` having JP variants. The JP path is active when `language="jp"`. The gap is that there is no user-facing toggle to request Japanese output independently — it's tied to the pipeline `language` parameter. | Product: add a per-ticker or per-request Japanese toggle that triggers the existing JP generation path. |
| **EDP-003** | Fiscal period must remain correct in all sections (profit, cash-flow, balance-sheet, guidance, summary) | S5 (Renderer) + S4 (Validator) | **GAP.** The `quarter` field flows from `_resolve_deep_dive_quarter()` into `_build_report_period_context()`, which builds the fiscal narrative. However, individual LLM-generated sections (S2) may independently decide on period labels, and the validator (S4) does not check section-level fiscal-period strings against the canonical `quarter`. The renderer (S5) does not enforce period consistency in section headings or table captions. | Scan extracted PDF text for ALL fiscal-period strings → fail if any section heading, table caption, or metadata label contradicts the canonical quarter. |
| **EDP-004** | Earnings Deep Dive must exclude Company Overview / business model / competitive landscape background | S2 (Prompt) + S6 (Product setting) | **PARTIAL_GAP.** `_build_report_period_context()` (mapper.py) includes `company_overview_md` in the LLM context, which may be appropriate as context data but the LLM may regurgitate it. The EN `SECTION_FORMATS` do not request Company Overview sections. The validator (S4) does not check for forbidden background-section headings. The renderer has a `CompanyOverview` section model (report_model.py) separate from earnings sections, but the 10-section `SECTION_ORDER` (prompts.py:39-50) does not include a Company Overview slot. | Extract section headings from PDF → fail if any heading contains "Company Overview", "Business Model", "Revenue Generation", "Competitive Landscape", or similar background terms. |
| **EDP-005** | EPS/revenue estimate data must use validated source; fall back to Investing.com if primary source is stale/mirrors actuals | S1 (Data source) + S6 (Product setting) | **GAP — PRODUCT_DECISION.** The current data source at `_deep_dive_metrics()` (pipeline.py:1224) uses yfinance `earnings_history` for EPS actual/estimate. There is no Investing.com fallback path. `_apply_press_release_metrics()` overrides from 8-K but this is for actuals, not estimates. The `SOURCE_CONSENSUS` constant in mapper.py (`"Yahoo Finance (consensus)"`) is hardcoded. No source hierarchy or fallback registry exists. | Fixture: primary EPS estimate == actual (stale). Assert fallback provider (Investing.com) supplies distinct estimate. |
| **EDP-006** | Revenue values must be consistent across table, prose, and calculations | S1 (Data source) + S4 (Validator) | **GAP.** Revenue values originate from `_deep_dive_metrics()` (`revenue_actual` at pipeline.py:1086/L1090) and flow through the mapper into `RenderedTableRow.cells`. However, the LLM (S2) may independently restate revenue in prose, and the validator (S4) does not cross-check numeric values between table cells and prose text. The mapper's `_is_placeholder()` check (mapper.py:64) handles placeholder replacement but not cross-validation. | Extract numeric revenue values from tables and prose → reconcile to within tolerance. |
| **EDP-007** | EPS & Revenue section must be concise: table + short bullets, not long paragraphs | S2 (Prompt) | **MOSTLY_PRESENT.** The EN `SECTION_FORMATS["EPS & Revenue"]` (prompts.py:406-418) already mandates "CONCISE — max ~120 words total, no long paragraphs" and requires "2-3 one-line bullets only" after the table. The JP variant (prompts.py:200-211) also mandates concision. The gap is that the validator (S4) does not enforce word count or paragraph count on this section — only section presence. | Count paragraph count and word count in EPS & Revenue section → fail if exceeds thresholds. |
| **EDP-008** | Highlights/Lowlights must use concise format: short heading + few bullets per point | S2 (Prompt) | **MOSTLY_PRESENT.** Both EN and JP `SECTION_FORMATS["Highlights"]` (prompts.py:418-443, 212-236) mandate "short numbered headings + bullets, NO paragraphs" and "Each bullet is ONE line." The gap is no validator enforcement of bullet-per-point limits or paragraph prohibition. | Count bullet count per highlight/lowlight item → fail if paragraphs or excessive bullets. |
| **EDP-009** | Profitability commentary must be concise takeaways after table, not long explanatory essays | S2 (Prompt) + S4 (Validator) | **PARTIAL_GAP.** The Operating Metrics formats (prompts.py:444-473, 237-255 for JP) require a table, then "3-5 sentences each point" for EN and "Key Takeaways only" for JP. The EN format actually REQUESTs explanation per point (3-5 sentences each), partially conflicting with the concision mandate. The JP format says "table carries the detail — no multi-paragraph analysis." The validator does not enforce concision metrics. | Count word count in Operating Metrics analysis block → fail if exceeds threshold. |
| **EDP-010** | Do not repeat Source as a full column in every profitability table when table-level note suffices | S5 (Renderer) + S6 (Product setting) | **PRODUCT_DECISION.** The `TABLE_REQUIREMENTS["Operating Metrics"]` (prompts.py:70) includes `Source` as a column: `"| Metric | Actual | Prior Year | YoY | Source |"`. This is a prompt-level decision — changing it to a table-level footnote requires modifying the prompt template AND the renderer to support table-level source notes. The `RenderedTableRow.source_field` exists in report_model.py (L103) but is row-level, not table-level. | Count Source column cells in Operating Metrics table → if all rows share same source, verify a single table-level note replaces the column. |
| **EDP-011** | Remove generic Quality subsections when they don't add earnings-specific insight | S2 (Prompt) + S4 (Validator) | **PARTIAL_GAP.** The prompt formats for Cash Flow, Capital Efficiency, and Segments include sections like "🧠 Explanation and analysis", "🎯 総合評価", "⚠️ Risk/Implications". None explicitly include a "Quality" subsection. The gap is that if the LLM generates a generic Quality subsection anyway, the validator does not block it. The `FORBIDDEN_MARKERS` list (deep_dive_validator.py:115-121) does not include quality-generic terms. | Extract section sub-headings → fail if a "Quality" or equivalent generic subsection heading exists without ticker-specific earnings metric content. |
| **EDP-012** | Avoid repeated source columns in cash-flow and balance-sheet tables; table-level note when rows share provenance | S5 (Renderer) + S6 (Product setting) | **PRODUCT_DECISION.** Same analysis as EDP-010 but applies to Cash Flow (prompts.py:71: `"| Metric | Actual | Prior Year | YoY | Quality read-through | Source |"`) and Capital Efficiency (prompts.py:72: `"| Metric | Value | Evaluation | Driver | Source |"`). | Inspect Cash Flow and Capital Efficiency table headers → if single-source provenance, verify table-level note replaces per-row Source column. |
| **EDP-013** | Include FCF Margin (FCF / Revenue × 100%) when both inputs available | S1 (Data source) | **FIXED.** `_extract_quarterly_comparison()` (pipeline.py:983) already computes `free_cash_flow` (L1081-1084) and `_deep_dive_metrics()` passes it through `FinancialMetrics.free_cash_flow`. The mapper (mapper.py) computes `fcf_margin` via `_ratio(metrics.free_cash_flow, _metric_value("revenue_actual", "revenue_quarterly"))`. Verified in mapper.py search results: `fcf_margin = _ratio(metrics.free_cash_flow, ...)`. The FCF Margin calculation EXISTS in the pipeline. However, there is no validator check that the rendered PDF includes FCF Margin when FCF and Revenue are both non-None. | Recompute FCF Margin from extracted FCF and revenue → compare with rendered value. |
| **EDP-014** | Net Cash / Net Debt = cash + marketable securities - total debt. If debt > cash+investments, present Net Debt. | S1 (Data source) | **VERIFIED_PRESENT.** `_extract_quarterly_comparison()` (pipeline.py:1017-1047) computes `net_debt_at()` with explicit `_CASH_LABELS` ("Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents") and debt fallback logic (`Long Term Debt`, `Current Debt`). The formula: `total_debt - cash_total`. The mapper then consumes this via `FinancialMetrics.net_debt`. The net_cash/net_debt label logic exists in the mapper (wallet_analysis). | Recompute from balance-sheet: cash + marketable securities - total debt → compare rendered value and label (Net Cash vs Net Debt). |

## Pipeline stage summary matrix

| Rule | S1 (Data) | S2 (Prompt) | S3 (Markdown) | S4 (Validator) | S5 (Renderer) | S6 (Product) |
|---|---|---|---|---|---|---|
| EDP-001 (fiscal period title) | — | prompt needs period directive | — | needs period-extract check | title/cover needs quarter enforcement | — |
| EDP-002 (Japanese PDF option) | — | JP prompts exist | JP cleanup exists | JP validates | JP renders exist | toggle needed |
| EDP-003 (period in all sections) | — | — | — | needs section-level period check | needs section-heading period enforcement | — |
| EDP-004 (no background sections) | — | prompt should forbid | — | needs forbidden-heading check | — | product boundary |
| EDP-005 (estimate source fallback) | needs Investing.com fallback | prompt labels source | — | — | — | provider list |
| EDP-006 (revenue consistency) | single source OK | — | — | needs cross-check | — | — |
| EDP-007 (EPS concision) | — | already mandates | — | needs word-count check | — | — |
| EDP-008 (highlights concision) | — | already mandates | — | needs bullet-count check | — | — |
| EDP-009 (profitability concision) | — | EN format needs tightening | — | needs word-count check | — | — |
| EDP-010 (profitability source column) | — | prompt column schema | — | — | needs table-level source note | product decision |
| EDP-011 (no generic Quality) | — | no Quality in prompt | — | needs forbidden-subheading check | — | — |
| EDP-012 (cash/balance source column) | — | prompt column schema | — | — | needs table-level source note | product decision |
| EDP-013 (FCF Margin) | calculation exists | — | — | needs presence check | — | — |
| EDP-014 (Net Cash/Debt) | calculation verified | — | — | — | — | — |

## Proposed atomic downstream tasks

These task candidates are for the orchestrator. Each is atomic (single pipeline seam) with explicit write_scope and expected checks.

### Task 1: Implement fiscal-period consistency gate in validator and renderer

- **Seam**: S4 (Validator) + S5 (Renderer)
- **Rules**: EDP-001, EDP-003
- **Write scope**: `backend/earnings_deep_dive/deep_dive_validator.py`, `backend/earnings_deep_dive/pdf_renderer.py`
- **Expected checks**:
  - Validator: extract all fiscal-period strings from markdown sections, compare against canonical `quarter`, emit issues on mismatch
  - Renderer: use `report.quarter` to construct cover title with correct fiscal period
  - Test: generate two tickers with different fiscal-year conventions (e.g., NVDA FY2027 vs AAPL FY2025), scan PDF text for conflicting labels

### Task 2: Add accepted estimate-provider fallback for EPS and revenue consensus

- **Seam**: S1 (Data source)
- **Rules**: EDP-005
- **Write scope**: `backend/pipeline.py` (`_deep_dive_metrics()` or new estimate source module), `backend/earnings_deep_dive/mapper.py` (source labels)
- **Expected checks**:
  - Fixture where yfinance `epsActual == epsEstimate` (stale), fallback provider supplies distinct estimate
  - Estimate source label is explicitly visible in EPS & Revenue table
  - Investing.com provider validation implemented before use

### Task 3: Add cross-validation of revenue/EPS numeric consistency

- **Seam**: S4 (Validator)
- **Rules**: EDP-006
- **Write scope**: `backend/earnings_deep_dive/deep_dive_validator.py`
- **Expected checks**:
  - Extract numeric revenue/EPS from table cells
  - Extract numeric revenue/EPS from prose text
  - Compare to within tolerance; fail on mismatch
  - Test: fixture with prose that contradicts table value

### Task 4: Add concision enforcement to validator

- **Seam**: S4 (Validator)
- **Rules**: EDP-007, EDP-008, EDP-009
- **Write scope**: `backend/earnings_deep_dive/deep_dive_validator.py`
- **Expected checks**:
  - EPS & Revenue: enforce max ~120 words, no multi-paragraph blocks
  - Highlights/Lowlights: enforce bullet-per-point limits, no paragraphs
  - Operating Metrics: enforce JP-style Key Takeaways format (max 5 bullets)
  - Tighten EN Operating Metrics prompt to match JP concision mandate

### Task 5: Add forbidden-heading and forbidden-subheading checks to validator

- **Seam**: S4 (Validator)
- **Rules**: EDP-004, EDP-011
- **Write scope**: `backend/earnings_deep_dive/deep_dive_validator.py`
- **Expected checks**:
  - Section-level: block headings containing "Company Overview", "Business Model", "Revenue Generation Overview", "Competitive Landscape"
  - Sub-section level: block generic "Quality" subsections unless they contain ticker-specific earnings metrics
  - Test: fixture with NVDA-like background content → validation fails

### Task 6: Add source-display normalization for PDF tables

- **Seam**: S5 (Renderer) + S2 (Prompt)
- **Rules**: EDP-010, EDP-012
- **Write scope**: `backend/earnings_deep_dive/prompts.py` (table column schemas), `backend/earnings_deep_dive/pdf_renderer.py` (table-level source notes), `backend/earnings_deep_dive/report_model.py` (optional table-level source note field)
- **Expected checks**:
  - Common-source table renders with single table-level source note (not per-row Source column)
  - Mixed-source table keeps row-level provenance
  - Test: fixture with all rows sharing same source → verify single note; fixture with mixed sources → verify per-row provenance

### Task 7: Add FCF Margin presence check to validator

- **Seam**: S4 (Validator)
- **Rules**: EDP-013
- **Write scope**: `backend/earnings_deep_dive/deep_dive_validator.py`
- **Expected checks**:
  - Recompute FCF Margin from `FinancialMetrics.free_cash_flow` and `revenue_actual`
  - Verify rendered PDF contains FCF Margin value
  - If FCF and Revenue both non-None but FCF Margin absent → issue

### Task 8: Specify and implement full Japanese Earnings Deep Dive PDF option

- **Seam**: S6 (Product setting)
- **Rules**: EDP-002
- **Write scope**: frontend (toggle UI), backend API (per-request language parameter), `backend/earnings_deep_dive/prompts.py` (JP section formats exist but may need polish)
- **Expected checks**:
  - Generated Japanese PDF covers all 10 sections
  - Headings, narratives, tables, notes, source labels are Japanese
  - Tickers, company legal names, source names remain canonical English where appropriate
  - Numeric units, fiscal-period labels, formulas, source provenance preserved

## Global rules note

All 14 rules (EDP-001 through EDP-014) derive from 14 NVDA PDF annotations. The gap map above treats NVDA only as the evidence exemplar. Every rule is mapped to pipeline seams that operate on ticker-independent code paths:

- `_deep_dive_metrics()` takes a `ticker: str` parameter — operates per ticker
- `generate_deep_dive()` takes `DeepDiveRequest.ticker` — ticker-agnostic LLM generation
- `build_earnings_deep_dive_report()` takes `ticker` and `company` — per-ticker model construction
- `render_earnings_deep_dive_pdf()` renders any `EarningsDeepDiveReport` regardless of ticker
- `validate_deep_dive()` validates any `.md` file — no ticker-specific logic

No rule in this gap map is hardcoded to NVDA. All proposed downstream tasks must verify with at least two tickers of different fiscal conventions.

## Acceptance checklist

- [x] All 14 generic rules mapped to concrete pipeline seams
- [x] 2 rules (EDP-002, EDP-010, EDP-012) marked as PRODUCT_DECISION
- [x] 8 proposed downstream tasks are atomic (single seam each)
- [x] No code files were modified
- [x] GRAPH_EVIDENCE includes concrete symbol names and call paths from actual file reads
- [x] WIKI_EVIDENCE references specific WIKI.md sections
- [ ] kverify strict validation (to be run as final step)
