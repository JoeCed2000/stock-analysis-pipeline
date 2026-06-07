# SA PDF Structural Quality v1 — Architecture Spec

Date: 2026-06-07  
Scope: Stock Analysis Pipeline — Company Overview PDF + Earnings Deep-Dive PDF  
Branch: `kanban/spec-fonctionnelle-sa`  
Mode: manual sequential execution only; no Kanban task creation/spawn/dispatch.

## 1. Objective

Make future investor PDFs structurally correct regardless of ticker, sector, currency, country, fiscal year, or data provider while preserving the current PDF structure as much as possible.

This is not a ticker-specific cleanup. The target is a pipeline-level contract that prevents incorrect numbers, ambiguous periods, unsupported source attributions, stale guidance, broken glyphs, and overconfident verdicts from reaching client-facing PDFs.

## 2. User-visible acceptance criteria

A generated PDF is acceptable only if:

- every displayed financial number is backed by one canonical metric entry;
- every metric has a resolved period label: `Quarterly`, `Annual`, `TTM`, `Market Snapshot`, `Guidance`, `Consensus`, or `Calculated`;
- historical actuals, market data, consensus estimates, management guidance, and internal calculations are not conflated;
- no source is cited for a metric unless the source capability registry says it can provide that metric family;
- all derived calculations shown in the PDF match their formula and inputs within explicit tolerances;
- guidance includes target period, publication date, and `current`/`prior` freshness status;
- Data Quality never marks an unavailable/not-used source as evidence;
- low confidence or low/mid completeness never produces a strong BUY/SELL-style conclusion;
- no unresolved internal enums or raw provider keys are visible (`annual_or_ttm`, `market_data`, `source: yfinance`, `S1`, etc.);
- no broken glyphs are visible (`■`, `□`, `�`), and no long raw URL overflows table cells;
- final export is blocked when any hard gate fails.

## 3. Current-state evidence

### 3.1 Existing project documentation

Relevant docs already establish parts of the contract:

- `docs/specs/pdf-parity-gap-analysis.md`
  - identifies P0 contradictions between deterministic tables and LLM prose;
  - identifies truncated sections accepted as OK;
  - identifies incorrect source normalization and URL/table rendering defects.
- `docs/pdf-audits/2026-06-02-pdf-quality-gates-map.md`
  - defines two layers: `pre_render_validator.py` before PDF, `pdf_quality_gate.py` after PDF;
  - documents PDFQA-001..013, including artifact validity, page counts, language, placeholders, internal labels, sources, rendered-page smoke, and key financial mismatch.
- `docs/pdf-audits/2026-06-02-company-overview-key-financials-contract.md`
  - defines upstream canonical sourcing and provenance for Company Overview `key_financials`;
  - forbids hidden PDF-renderer fallback selection;
  - blocks fields when valid sources diverge beyond tolerance.

### 3.2 Existing code hooks

`backend/earnings_deep_dive/report_model.py` already contains partial data structures:

- `SourceRegistryEntry`
- `SourceRegistry`
- `MetricsLedgerEntry`
- `MetricsLedger`
- `ReportPeriodContext`

`backend/pipeline.py` already builds and passes these structures into `build_earnings_deep_dive_report()` in the Deep-Dive path.

Important gap: CodeGraph currently returns zero definitions/references for `MetricsLedger` and `SourceRegistry`; Serena/file inspection sees them. For this project, CodeGraph evidence must therefore be paired with Serena and targeted repository search until the graph index is refreshed.

## 4. Target architecture

The architecture is a five-layer quality pipeline:

1. **Canonical data layer**
   - source capability registry;
   - metric truth table;
   - report period context;
   - guidance freshness model.

2. **Reconciliation layer**
   - validates source support;
   - validates period/basis separation;
   - validates repeated metrics across sections;
   - validates derived formulas.

3. **Policy layer**
   - confidence/completeness-aware verdict policy;
   - source/data quality display policy;
   - public label policy for sources and URLs.

4. **Renderer contract layer**
   - Deep-Dive and Company Overview consume canonical payloads;
   - renderers may format values but must not select or invent numeric values;
   - long URLs are rendered as short labels with hyperlinks.

5. **Post-render PDFQA layer**
   - extracts final PDF text;
   - optionally renders pages to PNG;
   - blocks glyph, overflow, placeholder, URL, source-label, and artifact defects.

## 5. Canonical Metric Truth Table

### 5.1 Required model

The existing `MetricsLedgerEntry` should be evolved into a canonical metric truth row with these required fields:

- `metric_id`: stable unique ID.
- `canonical_metric_name`: normalized metric key.
- `display_name`: client-safe label.
- `value`: normalized numeric value or null.
- `display_value`: rendered value text.
- `unit`: e.g. `USD`, `%`, `ratio`, `shares`.
- `scale`: e.g. `units`, `thousands`, `millions`, `billions`.
- `period_type`: strict enum, not free text.
- `fiscal_period`: fiscal label when applicable.
- `calendar_period`: date or date range when applicable.
- `basis`: strict enum: `GAAP`, `non_GAAP`, `adjusted`, `consensus`, `market`, `guidance`, `calculated`, `provider_supplied`.
- `source_id`: source registry key for sourced values.
- `source_type`: source class.
- `source_status`: resolved source usage state.
- `formula`: required for calculated rows.
- `inputs`: metric IDs or source paths used for calculated rows.
- `validation_status`: `verified`, `warning`, `blocked`, or `unavailable`.
- `confidence`: `high`, `medium`, `low`.
- `allowed_sections`: explicit list of renderer sections that may display the row.
- `quality_notes`: public-safe explanation for blocked/unavailable rows.

### 5.2 Period enum

Internal/provider labels must never reach the PDF. Map all period contexts to:

- `Quarterly`
- `Annual`
- `TTM`
- `Market Snapshot`
- `Consensus`
- `Guidance`
- `Calculated`

Examples:

- provider/internal `annual_or_ttm` → blocked until resolved;
- provider/internal `market_data` → `Market Snapshot`;
- `FY2026 Q1` actuals → `Quarterly` + fiscal period;
- forward P/E from provider → `Market Snapshot` with `provider_supplied` basis unless recomputed.

## 6. Source Capability Registry

### 6.1 Required source capabilities

Every source entry must declare what it can and cannot support:

- `source_id`
- `public_display_label`
- `provider`
- `source_type`
- `url`
- `status`: `used`, `candidate`, `available_not_used`, `failed`, `fallback_used`, `unavailable`
- `retrieved_at`
- `period_matched`
- `capability_families`: e.g. `historical_actuals`, `market_snapshot`, `consensus`, `guidance`, `transcript_claims`, `filing_facts`
- `unsupported_metric_families`
- `fields_used`
- `confidence`
- `failure_reason_internal_only`
- `public_quality_note`

### 6.2 Hard rules

- `failed`, `unavailable`, and `available_not_used` sources cannot be cited as evidence.
- A source cannot support a metric outside its declared capabilities.
- A fallback source must be labeled as fallback in Data Quality.
- Public labels must be human-readable; raw provider keys are blocked.
- A source URL may be stored in the registry but displayed only as a short label hyperlink.

## 7. Reconciliation pass

A reconciliation pass must run after canonical data assembly and before narrative/rendering.

Inputs:

- metric truth table;
- source capability registry;
- report period context;
- guidance model;
- section drafts or structured report model;
- Company Overview `key_financials_provenance` where applicable.

Outputs:

- normalized canonical payload for renderers;
- blocking defects;
- warnings;
- public-safe data quality notes;
- trace JSON saved next to generated report artifacts.

Hard checks:

- no missing period for displayed metric;
- no missing source for sourced metric;
- no unsupported source attribution;
- no metric repeated with conflicting value/period/basis;
- no calculated metric without formula and inputs;
- no narrative claim that contradicts canonical values;
- no stale guidance presented as next-quarter/current guidance;
- no strong verdict if confidence is low.

## 8. Derived calculations validator

### 8.1 Covered metrics

The validator must cover at least:

- YoY change;
- QoQ change;
- gross margin;
- operating margin;
- net margin;
- free cash flow;
- P/E;
- PEG;
- net cash / net debt;
- dividend yield;
- ROE;
- ROIC;
- other ratios explicitly rendered in tables or verdict blocks.

### 8.2 Required validation record

Each calculated metric row must include:

- formula name;
- formula expression;
- input metric IDs or source paths;
- input periods;
- recomputed value;
- displayed value;
- tolerance;
- validation result.

If validation fails, the metric is blocked from PDF display unless explicitly downgraded to a warning by a documented false-positive rule.

## 9. Guidance freshness model

Guidance rows must carry:

- `guidance_target_period`;
- `guidance_publication_date`;
- `source_id`;
- `freshness_status`: `current`, `prior`, `stale`, or `unknown`;
- `superseded_by` when known;
- `public_quality_note`.

Rules:

- Only `current` guidance can be titled next-quarter/current guidance.
- `prior` guidance can appear only as historical context.
- `stale` or `unknown` guidance cannot support a forward-looking verdict.

## 10. Verdict policy

Verdicts must be computed from data quality, not only from prose.

Inputs:

- metric truth completeness;
- source count and source quality;
- blocked critical metrics;
- guidance freshness;
- reconciliation defects;
- confidence distribution.

Hard rules:

- `confidence=low` → no strong rating.
- critical source unavailable → `preliminary assessment` or `data-limited assessment`.
- unresolved blocking defects → no final verdict.
- high-confidence final verdict requires no blocking defects, current/valid guidance where guidance is used, and enough historical/market/consensus separation.

## 11. Renderer contracts

### 11.1 Earnings Deep-Dive

Required section contract:

1. source map;
2. quarter summary;
3. EPS/revenue;
4. operating metrics;
5. segments;
6. cash flow;
7. balance sheet;
8. guidance;
9. valuation;
10. risks;
11. verdict;
12. data quality.

Renderer rules:

- consume metric truth rows, not raw provider dicts;
- consume source registry labels, not raw keys;
- display explicit period/basis labels;
- display unavailable metrics as explained omissions, not placeholders;
- never display unresolved internal enum values.

### 11.2 Company Overview

Required section contract:

1. executive snapshot;
2. business overview;
3. revenue model;
4. segments;
5. KPIs;
6. growth drivers;
7. risks;
8. valuation;
9. sources.

Renderer rules:

- use upstream `key_financials` and provenance;
- do not select values from fallback sources inside PDF rendering when provenance exists;
- if provenance is absent in legacy cache, mark as legacy fallback and run stricter PDFQA.

## 12. PDF rendering safety

Hard blockers:

- broken glyphs: `■`, `□`, `�`;
- raw internal/provider markers;
- `DATA NOT AVAILABLE`, `NaN`, `None`, `undefined`, raw null placeholders;
- long raw URL text in tables;
- table overflow/overlap detected by visual QA;
- footer overlap;
- page count outside expected ranges.

Required behavior:

- normalize Unicode before render;
- use a Unicode-capable font for all supported languages;
- use textual labels instead of emoji-dependent bullets in client PDFs unless the font is proven to support them;
- render source URLs as short hyperlinks.

## 13. Post-render visual QA

The post-render gate should:

- render every page to PNG or at least first/middle/last pages for smoke mode;
- extract text with PyMuPDF;
- scan for forbidden glyphs and markers;
- scan for raw long URLs;
- verify tables do not overflow page width where geometry metadata is available;
- save audit JSON and sampled PNGs next to report artifacts.

Smoke mode can warn on missing PNGs during development, but client export mode must block when configured as final delivery.

## 14. Blocking gates before export

A PDF export is blocked if any of the following are true:

- unresolved internal enum;
- missing period;
- missing source for a sourced metric;
- inconsistent repeated metric;
- unsupported source attribution;
- stale guidance presented as current/next-quarter;
- broken glyph;
- raw long URL overflow;
- strong rating with LOW confidence;
- invalid/corrupt/too-small PDF artifact;
- missing required artifact without explicit skip reason.

## 15. Implementation sequence

Manual sequential slices only:

1. `SA-PDF-T1` — evolve/test metric truth schema and period enums.
2. `SA-PDF-T2` — evolve/test source capability registry validator.
3. `SA-PDF-T3` — add reconciliation pre-render pass.
4. `SA-PDF-T4` — add derived calculation validator.
5. `SA-PDF-T5` — add guidance freshness gate.
6. `SA-PDF-T6` — add confidence-aware verdict policy.
7. `SA-PDF-T7` — integrate Deep-Dive with the canonical payload.
8. `SA-PDF-T8` — integrate Company Overview with canonical provenance.
9. `SA-PDF-T9` — add Unicode/glyph blocker.
10. `SA-PDF-T10` — add short source labels and hyperlinks.
11. `SA-PDF-T11` — add post-render PNG visual QA.
12. `SA-PDF-T12` — stabilize Company Overview template.
13. `SA-PDF-T13` — stabilize Earnings Deep-Dive template.
14. `SA-PDF-T14` — multi-ticker final recette, WIKI, Kernel proof.

## 16. Test strategy

Each implementation slice must add focused tests before or with code:

- model/schema tests for canonical rows and enums;
- validator tests for each hard blocker;
- renderer tests for labels, glyphs, URLs, and no hidden fallback;
- generated artifact tests on at least two tickers before final READY;
- PyMuPDF text audit for final PDFs;
- browser/API recette for client paths.

Minimum targeted commands by phase:

```bash
backend/.venv/bin/python -m pytest tests/spec_v27_metrics_ledger.py tests/spec_v27_source_registry.py -q
backend/.venv/bin/python -m pytest tests/spec_v27_pdf_quality_gate.py tests/test_post_process_markdown.py -q
backend/.venv/bin/python -m py_compile backend/earnings_deep_dive/*.py backend/company_overview.py backend/company_overview_pdf.py backend/pipeline.py
curl -fsS http://127.0.0.1:8780/api/health
```

Final phase must include real PDF generation and extraction with PyMuPDF.

## 17. Operational gates

- WIKI-first before edits.
- CodeGraph before editing functions; if CodeGraph misses known symbols, record the miss and use Serena + targeted search fallback.
- Serena symbol-level edits where possible.
- No Kanban for this SA work until Ced explicitly re-enables it.
- No push claim without live git verification.
- Backend restart proof required after backend code changes.
- Ced Agent Kernel required after significant state/config/closeout or final code-change verification.

## 18. Definition of done for this architecture slice

This architecture slice is done when:

- this spec exists in `docs/specs/sa-pdf-structural-quality-v1.md`;
- `WIKI.md` references the spec and the no-Kanban execution mode;
- `git status` shows only expected doc changes for this slice;
- local health still responds;
- no code production file has been modified.
