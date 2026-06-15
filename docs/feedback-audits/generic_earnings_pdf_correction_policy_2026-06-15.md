# Generic Earnings PDF Correction Policy

Date: 2026-06-15
Project: Stock Analysis Pipeline
Scope: Earnings Deep Dive PDFs for every ticker, every supported language variant
Source exemplar: `analyses/feedback_NVDA/2026-06-11_061719_NVDA_company_earnings_results_2026-06-09_comment_by_nt.pdf`
Status: policy/spec artifact only; no production-code change in this card

## Executive summary for Ced

This policy turns the NVDA annotated PDF into global Earnings Deep Dive behavior rules. NVDA is used only as the evidence exemplar; the rules below must apply to any ticker where the corresponding data exists.

The global direction is:

- Earnings Deep Dive reports must focus on earnings results, financial performance, guidance, cash generation, margins, balance sheet strength, and investor implications.
- Repeated company-background material belongs in Company Overview, not in Earnings Deep Dive.
- Fiscal-period labels must be correct and visible throughout the report, because different companies report different fiscal years for similar calendar periods.
- Estimate data may use fast, clear external earnings-result providers such as Investing.com when the provider is validated and explicitly labeled.
- The PDF should be more concise: short headings plus a few bullets beat long explanatory paragraphs.
- Source/provenance should remain visible but not repeated in every table row when a single table-level note is sufficient.
- A full Japanese PDF option is a product requirement, separate from the current English-report defect fixes.

## Evidence source and extraction count

Extraction method:

- Used the canonical PyMuPDF extraction path documented in `backend/pdf_annotation_extractor.py` and WIKI.md.
- Command evidence: `backend/.venv/bin/python` opened the annotated PDF and returned `total_count 14 error None`.
- The 14 extracted annotations are accounted for one by one in the rules table below.

Source annotation distribution:

- Page 1: annotations 1-4
- Page 6: annotations 5-7
- Page 8: annotation 8
- Page 11: annotations 9-10
- Page 13: annotations 11-14

## WIKI_EVIDENCE

Read: `WIKI.md` in the project root.

Relevant findings:

- WIKI.md section `2026-06-15 — PDF annotation extractor for feedback uploads` documents `backend/pdf_annotation_extractor.py`, PyMuPDF extraction, annotation counts, and tests.
- WIKI.md section `2026-06-13 — NVDA Company Overview richness + Sources fallback` records recent NVDA PDF work and confirms the need to distinguish Company Overview content from Earnings Deep Dive content.
- WIKI.md documents recent NVDA fixes around FY2027 labeling, FCF Margin, Net Cash evidence, and source pages; Ced clarified that these are generic requirements, not NVDA-only patches.

## GRAPH_EVIDENCE

CodeGraph status was checked for the project:

- Project: `/home/ced/codex-projects/stock-analysis-pipeline`
- Indexed files: 319
- Nodes: 7,423
- Edges: 14,926
- Status: index up to date

Relevant graph/symbol evidence:

- The canonical extraction integration point is `backend/pdf_annotation_extractor.py::extract_annotations`.
- This card does not request production-code edits. Therefore, the graph evidence is used only to anchor the annotation extraction source and confirm that no runtime call chain should be modified by this spec card.

## SYMBOL_PLAN

No symbol-level code edit is applicable in this card.

Planned and completed file action:

- Create one markdown policy artifact only: `docs/feedback-audits/generic_earnings_pdf_correction_policy_2026-06-15.md`.
- Do not edit `backend/`, `frontend/`, generated PDFs, feedback state, or Kanban cards.

## Generic rules table

| rule_id | source_annotation_pages | generic_rule | applies_to | exception_or_product_decision | verification_method |
|---|---:|---|---|---|---|
| EDP-001 | p1 annotation 1 | The report title must use the correct fiscal period and earnings event, not a calendar-quarter guess. Example: if a company reports FY2027 Q1 results in calendar 2026, the visible heading must say FY2027 Q1. | Every Earnings Deep Dive cover/title/header and repeated period label. | Implementation defect when the fiscal period is wrong or too small to notice. | Extract PDF text and assert the dominant title/header contains the verified fiscal period and earnings date. |
| EDP-002 | p1 annotation 2 | Provide a user-selectable option to generate or translate the entire Earnings Deep Dive PDF in Japanese. | Every generated Earnings Deep Dive PDF where Japanese output is requested. | Product decision: full-PDF Japanese is a feature option, not merely a translation bug in one section. | Generate a Japanese variant and verify all visible headings, narrative sections, tables, notes, and source labels are Japanese or intentionally untranslated tickers/company names. |
| EDP-003 | p1 annotation 3 | The fiscal period must remain correct throughout all sections, especially profit, cash-flow, balance-sheet, guidance, and summary sections. | Every section carrying fiscal-period labels, table headers, captions, source notes, and metadata. | Implementation defect if only the cover is fixed while section labels remain stale. | Scan extracted PDF text for conflicting fiscal-period strings; fail if incompatible periods appear without explicit comparative context. |
| EDP-004 | p1 annotation 4 | Earnings Deep Dive must exclude stable background sections such as company overview, business model, revenue-generation overview, competitive landscape, and other non-quarter-specific background. | Earnings Deep Dive table of contents and narrative body. | Product boundary: these sections belong in Company Overview or a separate background report. | Extract section headings and assert forbidden background headings are absent from Earnings Deep Dive PDFs. |
| EDP-005 | p6 annotation 5 | EPS and revenue estimate data must be sourced from a validated earnings-result source; if the primary source mirrors actuals or looks stale, fall back to accepted providers such as Investing.com. | EPS & Revenue section, consensus tables, beat/miss calculations, and estimate citations. | Product decision: Investing.com is an accepted estimate-data provider when validated and labeled; it is not a hacky one-off fallback. | Compare actual vs estimate fields; flag impossible estimate=actual duplicates unless the source explicitly reports no consensus. Verify provider label and URL/source note. |
| EDP-006 | p6 annotation 6 | Revenue values in the EPS & Revenue table must be consistent across table values, prose, and calculations. | Revenue actual, revenue estimate, beat/miss delta, YoY, and related prose. | Implementation defect if a highlighted number is correct in one location but contradicted elsewhere. | Extract table and prose values; reconcile actual revenue and estimate-derived deltas within tolerance. |
| EDP-007 | p6 annotation 7 | The EPS & Revenue section should be concise: table plus short key positives/negatives, not a long paragraph-by-paragraph explanation. | EPS & Revenue narrative immediately below the table. | Product style rule: detailed analysis should move to highlights/lowlights or dedicated metric sections. | Count paragraph length and bullet count; require a compact summary with no long prose block after the table. |
| EDP-008 | p8 annotation 8 | Highlights and Lowlights must use a concise format: short heading for each key point plus a few bullets explaining it. | Highlights, Lowlights, quarter positives, quarter negatives. | Product style rule; ticker-specific examples may be used only as evidence, not as hardcoded copy. | Verify each item has a short heading and limited bullets; fail long multi-paragraph highlight/lowlight entries. |
| EDP-009 | p11 annotation 9 | Profitability commentary should summarize key takeaways after the table instead of long explanatory essays. | Gross margin, operating margin, net margin, OpEx, operating-income commentary. | Product style rule: sufficient detail is the table plus concise takeaways explaining why margins changed and why they matter. | Extract profitability section and enforce a compact `Key Takeaways` or equivalent bullet block after the metrics table. |
| EDP-010 | p11 annotation 10 | Do not repeat `Source` as a full column in every profitability table when the same provenance can be stated once below the table. | Tables where all or most rows share the same source family. | Product decision: row-level sources remain allowed only when rows genuinely come from different providers or need auditability. | Inspect table headers and footnotes; prefer a table-level `Source note:` when provenance is common. |
| EDP-011 | p13 annotation 11 | Remove generic `Quality` subsections when they do not add earnings-specific insight beyond the table and concise takeaways. | Cash-flow, balance-sheet, profitability, capital-efficiency sections. | Product style rule: quality judgments should appear as concise investor takeaways, not a standalone boilerplate section. | Extract headings and fail generic `Quality` headings unless they contain a ticker-specific earnings metric not covered elsewhere. |
| EDP-012 | p13 annotation 12 | Avoid repeated source columns/blocks in cash-flow and balance-sheet tables; mention shared source context once below the table when sufficient. | Cash-flow table, balance-sheet table, capital-efficiency table. | Same exception as EDP-010: row-level source is allowed when different row sources materially affect interpretation. | Inspect table headers and nearby notes; ensure source provenance is present once and not visually cluttering the table. |
| EDP-013 | p13 annotation 13 | Include FCF Margin when free cash flow and revenue are available. Formula: FCF Margin = Free Cash Flow / Revenue × 100%. | Cash-flow section, free-cash-flow table, key metrics summary. | Implementation defect if FCF and revenue are both available but FCF Margin is omitted. If either input is unavailable, show `Not available` with source reason. | Recompute FCF Margin from extracted FCF and revenue values and compare with rendered value within rounding tolerance. |
| EDP-014 | p13 annotation 14 | Net Cash / Net Debt must use cash and cash equivalents plus marketable securities minus total debt. If debt exceeds cash and investments, present Net Debt. | Balance-sheet strength, net cash/debt table, cash structure commentary. | Implementation defect if the figure uses only cash, excludes marketable securities, or ignores short-term/long-term debt. | Recompute from balance-sheet inputs: cash + marketable securities - total debt; compare rendered value and label with tolerance. |

## Explicit global product decisions

### Japanese full-PDF option

Decision: Add a product option for full Japanese Earnings Deep Dive output.

Policy:

- The option must cover the whole PDF, not only summaries.
- Tickers, company legal names, and source names may remain in their canonical English form when appropriate.
- Japanese output must preserve numeric units, fiscal-period labels, formulas, and source provenance.

### Accepted estimate-data providers

Decision: Investing.com is an accepted earnings-result estimate provider when validated.

Policy:

- Use a source hierarchy for estimates: official/company material when available, validated consensus provider, then accepted external earnings-result provider such as Investing.com.
- If a provider gives actuals quickly but estimates look duplicated, stale, or missing, mark the issue and fall back.
- Every estimate/actual table must label its provider clearly enough for audit.

### Concision standard

Decision: Earnings Deep Dive should be table-led and concise.

Policy:

- Each major section should prefer a metrics table plus 3-5 concise investor takeaways.
- Avoid long explanatory paragraphs unless they explain a genuinely complex, material quarter-specific issue.
- Highlights/lowlights should be formatted as short headings with bullets.
- Background/company-overview content should be omitted from Earnings Deep Dive unless there is a direct quarter-specific change.

### Source/provenance display

Decision: Provenance must remain auditable but not visually noisy.

Policy:

- Use row-level source labels only when row sources differ or the distinction matters.
- Use a single table-level source note when all rows come from the same source family.
- Never remove source provenance entirely.

## Product decisions vs implementation defects

Product decisions:

- Full Japanese PDF option.
- Investing.com or similar accepted estimate-data provider as a validated fallback/source.
- Concise table-led report style.
- Source provenance display standard: table-level when possible, row-level when necessary.
- Earnings Deep Dive boundary: no generic Company Overview/background sections.

Implementation defects:

- Wrong fiscal-period title or section labels.
- Estimate values that mirror actuals because of stale or incorrect source mapping.
- Revenue/EPS inconsistencies across table, prose, and calculations.
- Missing FCF Margin when inputs exist.
- Incorrect Net Cash / Net Debt formula or data source.
- Repeated source columns causing clutter where a single source note is sufficient.

## Downstream atomic task candidates

Do not create these cards from this policy card. They are candidates for the orchestrator.

1. `Implement fiscal-period consistency gate for Earnings Deep Dive PDFs`
   - Scope: period metadata, title/header renderer, PDF text validation.
   - Expected verification: generate two tickers with different fiscal-year conventions and scan for conflicting labels.

2. `Add accepted estimate-provider fallback for EPS and revenue consensus`
   - Scope: estimate-source registry and EPS/Revenue table sourcing only.
   - Expected verification: fixture where primary estimate equals actual incorrectly, fallback source supplies distinct estimate.

3. `Apply concise Earnings Deep Dive section templates`
   - Scope: prompt/template policy for EPS & Revenue, Highlights/Lowlights, Profitability, Cash Flow, Balance Sheet.
   - Expected verification: generated sections meet heading/bullet/length constraints.

4. `Add FCF Margin and Net Cash / Net Debt deterministic calculators`
   - Scope: cash-flow/balance-sheet metric builder only.
   - Expected verification: formula tests with fixture inputs, including marketable securities and short/long-term debt.

5. `Add source-display normalization for PDF tables`
   - Scope: renderer/table mapping only.
   - Expected verification: common-source table has a single source note; mixed-source table keeps row-level provenance.

6. `Specify and implement full Japanese Earnings Deep Dive PDF option`
   - Scope: product option, translation coverage, renderer labels, language QA.
   - Expected verification: generated Japanese PDF text audit confirms all report sections are covered.

## Final acceptance checklist for implementation work that uses this policy

- All 14 exemplar annotations map to a generic behavior rule.
- No rule is hardcoded to NVDA, except as an example in tests/fixtures.
- Product decisions are tracked separately from defects.
- Metric formulas are deterministic and testable.
- PDF verification uses extracted final PDF text, not only markdown or API health.
- Japanese output is validated at full-PDF level when that option is implemented.
