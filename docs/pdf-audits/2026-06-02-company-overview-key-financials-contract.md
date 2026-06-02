# Company Overview `key_financials` — canonical sourcing contract

Task: `t_e84a33e6` — Define canonical key_financials sourcing contract  
Date: 2026-06-02  
Scope: Stock Analysis Pipeline — Company Overview JSON/PDF data integrity

## 1. Purpose

This contract fixes the NVDA-class mismatch where rendered Company Overview PDFs can display financial values that diverge from the canonical market/source snapshot.

The required behavior is simple:

- numeric Company Overview facts must be selected once upstream;
- every selected field must carry provenance;
- PDF renderers must consume the canonical selected payload;
- PDF renderers must not perform hidden fallback selection at display time;
- when two valid sources disagree beyond tolerance, the field is blocked instead of fabricated or silently chosen.

## 2. Triad evidence

### WIKI_EVIDENCE

Relevant project WIKI entries establish this as a known client-facing PDF quality issue:

- `2026-06-01 — Kanban t_cfa7ab17`: NVDA mismatch was reproduced end-to-end; local and production JSON/PDF were byte-identical, proving this is not local/prod drift.
- Baseline mismatch class: rendered Company Overview values used market cap / forward P-E / beta / revenue / FCF / 52W values that diverged from the Yahoo/source-ledger trace.
- `2026-06-01 — Kanban t_d4c1bc6e`: metric source selection is spread across `company_overview.py`, `pipeline.py`, `company_overview_pdf.py`, `company_profile.py`, and deep-dive model/rendering code.
- WIKI notes require financial data to remain sourced/auditable through generated source manifests and forbid hidden/fabricated fallback values.

### GRAPH_EVIDENCE

GBrain CodeGraph returned zero hits for the relevant symbols, so the documented fallback was used: Serena symbol map + `tb rg` targeted search.

Confirmed symbols and current behavior:

- `backend/company_overview.py::_build_yahoo_info_dict`
  - adapts raw yfinance camelCase info to snake_case keys;
  - exposes `market_cap`, `total_revenue`, `gross_margins`, `operating_margins`, `free_cashflow`, `peg_ratio`, `pe_forward`, `beta`, `52w_high`, `52w_low`, etc.;
  - does not currently attach per-field provenance.

- `backend/company_overview.py::_parse_llm_response`
  - accepts/normalizes LLM JSON;
  - preserves `key_financials` from LLM output;
  - currently only special-cases dividend yield normalization;
  - therefore LLM output can still become numeric source-of-truth unless later overlaid.

- `backend/company_overview.py::_fallback_overview`
  - builds deterministic fallback values directly from raw Yahoo camelCase keys;
  - currently produces `key_financials` without provenance;
  - currently contains independent numeric formatting/selection branches.

- `backend/company_overview.py::get_company_overview`
  - fetches Yahoo info and Tavily context;
  - generates EN overview or JP translation;
  - caches the complete overview for seven days;
  - currently does not accept a pipeline ledger/source context and does not recompute provenance before cache write.

- `backend/company_overview_pdf.py::_render_kpis`
  - uses `fin = overview.get('key_financials', {})`;
  - then performs multiple PDF-time fallbacks to `yf_data`, e.g. `fin.get('market_cap') or yf_data.get('marketCap')`, `fin.get('revenue') or yf_data.get('totalRevenue')`, etc.;
  - uses inconsistent key conventions (`free_cash_flow` vs `free_cashflow`, camelCase Yahoo keys vs normalized snake_case keys);
  - computes PEG/dividend at render time;
  - therefore the PDF layer can silently override upstream semantics.

### SYMBOL_PLAN

Implementation must introduce one upstream resolver and then simplify renderers.

Primary insertion point:

- `backend/company_overview.py`: add a canonical resolver used by `_parse_llm_response`, `_fallback_overview`, and `get_company_overview` before cache write.

Pipeline integration point:

- `backend/pipeline.py::analyze_ticker_fast`: build/pass the canonical ledger and Yahoo snapshot into `get_company_overview`, and persist the provenance next to `company_overview_{ticker}.json`.

Renderer integration point:

- `backend/company_overview_pdf.py::_render_kpis`: stop selecting values from `yf_data` except as explicit backward-compatible legacy fallback when provenance is absent. Once provenance exists, render only selected fields or explicit `Not available` with reason.

## 3. Definitions

### 3.1 Source candidates

- `ledger`: typed values already computed by the pipeline after yfinance/SEC/EDGAR enrichment. Preferred for values that are derived from canonical internal models.
- `yahoo_snapshot`: raw/sanitized output from Yahoo/yfinance, including both snake_case adapter fields and `_raw_info` camelCase passthrough where available.
- `llm_output`: narrative-only. It can provide prose, but it must not be authoritative for numeric `key_financials`.

### 3.2 Canonical selected field

A selected field is the value that downstream JSON, Markdown, and PDF must render.

Each selected field must have:

- `status`: `selected`, `unavailable`, or `blocked`;
- `reason_code`: null for selected fields, coded reason for unavailable/blocked fields;
- `selected_source`: e.g. `ledger`, `yahoo_snapshot`, `computed`, or null;
- `selected_path`: exact path used, e.g. `AnalysisResult.market_cap`, `yahoo_snapshot.market_cap`, `_raw_info.forwardPE`;
- `raw_value`;
- `normalized_value`;
- `display_value`;
- `unit`;
- `period`;
- `candidates` list.

## 4. Required output schema

`company_overview` must remain backward-compatible:

```json
{
  "key_financials": {
    "market_cap": 5220000000000,
    "market_cap_display": "$5.22T",
    "revenue": null,
    "revenue_display": "Not available",
    "pe_forward": 35.0,
    "beta": 1.70,
    "52w_low": 124.17,
    "52w_high": 199.62
  },
  "key_financials_provenance": {
    "schema_version": 1,
    "ticker": "NVDA",
    "generated_at": "2026-06-02T00:00:00Z",
    "fields": {
      "market_cap": {
        "status": "selected",
        "reason_code": null,
        "selected_source": "ledger",
        "selected_path": "AnalysisResult.market_cap",
        "raw_value": 5220000000000,
        "normalized_value": 5220000000000.0,
        "display_value": "$5.22T",
        "unit": "USD",
        "period": "market_data",
        "comparison": {
          "tolerance_rel": 0.10,
          "tolerance_abs": 1000000,
          "relative_delta": 0.003,
          "accepted": true
        },
        "candidates": [
          {
            "source": "ledger",
            "path": "AnalysisResult.market_cap",
            "raw_value": 5220000000000,
            "normalized_value": 5220000000000.0,
            "valid": true,
            "reason_code": null
          },
          {
            "source": "yahoo_snapshot",
            "path": "market_cap",
            "raw_value": 5235000000000,
            "normalized_value": 5235000000000.0,
            "valid": true,
            "reason_code": null
          }
        ]
      }
    }
  }
}
```

## 5. Per-field source priority

### 5.1 Market cap

- Field: `market_cap`
- Display: `market_cap_display`
- Preferred source: `ledger.AnalysisResult.market_cap`
- Secondary source: `yahoo_snapshot.market_cap` or `_raw_info.marketCap`
- Unit: USD market value
- Period: market data timestamp
- Tolerance: max(10% relative, $1M absolute)
- Mismatch behavior: if both sources are valid and disagree by more than 10%, block with `mismatch_blocked`.

### 5.2 Revenue

- Field: `revenue`
- Display: `revenue_display`
- Preferred source: ledger revenue if available from `FinancialData` / income statement pipeline output.
- Secondary source: `yahoo_snapshot.total_revenue` or `_raw_info.totalRevenue`.
- Unit: USD annual/TTM value.
- Period: annual or TTM; must be explicit.
- Tolerance: max(10% relative, $1M absolute) when both sources represent the same period class.
- If periods differ (annual vs TTM) and cannot be reconciled, prefer ledger only if ledger period is explicit; otherwise block with `period_mismatch_blocked`.

### 5.3 Gross margin

- Field: `gross_margin`
- Display: percentage.
- Preferred source: ledger margin from financial model if available.
- Secondary source: `yahoo_snapshot.gross_margins` or `_raw_info.grossMargins`.
- Unit: ratio normalized to decimal internally (`0.741`) and percent for display (`74.1%`).
- Tolerance: 2 percentage points absolute.
- Values > 1 and <= 100 are treated as percent input and normalized by `/100` with reason note `percent_input_normalized`.

### 5.4 Operating margin

- Field: `operating_margin`
- Same rules as gross margin.
- Secondary source: `yahoo_snapshot.operating_margins` or `_raw_info.operatingMargins`.

### 5.5 Free cash flow

- Field: `free_cash_flow`
- Alias accepted for input only: `free_cashflow`.
- Output must standardize on `free_cash_flow` and may include `free_cashflow` as backward-compatible alias during migration.
- Preferred source: ledger/cash-flow model.
- Secondary source: `yahoo_snapshot.free_cashflow` or `_raw_info.freeCashflow`.
- Unit: USD annual/TTM.
- Tolerance: max(10% relative, $1M absolute) when periods match.
- Sign must be preserved; do not `abs()` cash flow values.

### 5.6 Forward P/E

- Field: `pe_forward`
- Preferred source: ledger valuation field if present.
- Secondary source: `yahoo_snapshot.pe_forward` or `_raw_info.forwardPE`.
- Unit: multiple, e.g. `35.0x`.
- Tolerance: 10% relative.
- If provider gives non-positive value, mark malformed.

### 5.7 Trailing P/E

- Field: `pe_ratio`
- Preferred source: ledger valuation field.
- Secondary source: `yahoo_snapshot.pe_trailing` or `_raw_info.trailingPE`.
- Unit: multiple.
- Tolerance: 10% relative.

### 5.8 Beta

- Field: `beta`
- Preferred source: ledger only if ledger explicitly stores market beta with timestamp.
- Secondary/default source: `yahoo_snapshot.beta` or `_raw_info.beta`.
- Unit: ratio.
- Tolerance: 10% relative.
- If sources disagree beyond tolerance, block; beta must not be invented.

### 5.9 52-week range

- Fields: `52w_low`, `52w_high`
- Preferred source: Yahoo snapshot; ledger only if it stores equivalent market range with timestamp.
- Secondary source: `_raw_info.fiftyTwoWeekLow`, `_raw_info.fiftyTwoWeekHigh`.
- Unit: USD share price.
- Invariant: `52w_low <= 52w_high`.
- If only one bound exists, render that bound only and mark the other `unavailable_from_source`.
- If low > high, block both fields with `malformed_source_value`.

### 5.10 Dividend yield

- Field: `dividend_yield`
- Preferred behavior: compute from `dividend_rate / current_price` when both are valid.
- Secondary source: Yahoo dividend yield.
- Internal unit: decimal ratio; display unit: percent.
- If source value is > 0.5 and <= 100, treat as percent input and normalize by `/100`, preserving a normalization note.

### 5.11 PEG ratio

- Field: `peg_ratio`
- Preferred behavior: compute consistently from selected trailing P/E and selected earnings growth if both exist and earnings growth is positive.
- Secondary source: Yahoo `pegRatio` only when compute inputs are missing.
- Display unit: multiple.
- If compute and Yahoo disagree, keep computed value and include Yahoo as candidate; do not mix expected 5-year Yahoo PEG with trailing growth PEG without labeling.

## 6. Candidate normalization rules

Every candidate must be normalized before comparison.

### Numeric coercion

Accept:

- int/float;
- numeric strings with commas;
- strings with suffixes: K, M, B, T, thousand, million, billion, trillion;
- strings with leading `$`.

Reject as malformed:

- `None`;
- empty string;
- `N/A`, `DATA NOT AVAILABLE`, `null`, `undefined`, `NaN`;
- non-finite float;
- arbitrary prose.

### Scale rules

- money fields normalize to absolute USD numeric values;
- ratio fields normalize to decimal internally where applicable;
- display formatting happens after selection, not before comparison;
- no comparison may use display strings.

### Rounding rules

- comparisons use unrounded normalized values;
- displays may round:
  - market cap/revenue/FCF: compact `$5.22T`, `$253.5B`;
  - ratios: one or two decimals as appropriate;
  - margins/yields: one or two percent decimals.

## 7. Reason-code taxonomy

Required reason codes:

- `provider_missing`: upstream provider did not expose the field.
- `unavailable_from_source`: provider/source exists but does not report this metric.
- `malformed_source_value`: source value exists but cannot be safely normalized or violates invariants.
- `both_sources_absent`: no valid ledger or Yahoo candidate exists.
- `mismatch_blocked`: two valid candidates disagree beyond tolerance and no deterministic reconciliation rule applies.
- `period_mismatch_blocked`: candidates are valid but represent incompatible periods.
- `currency_mismatch_blocked`: candidates are valid but currency/unit metadata conflicts.
- `computed_from_components`: selected value was computed from selected components, e.g. dividend yield or PEG.
- `legacy_unprovenanced_fallback`: temporary renderer fallback path used only for old cached artifacts without provenance; must be logged and eventually removed.

## 8. Selection algorithm

For each field:

1. Build candidate list from ledger and Yahoo snapshot using the field mapping above.
2. Normalize each candidate.
3. Mark malformed candidates with `malformed_source_value`.
4. If no valid candidates exist, output:
   - `key_financials[field] = null`
   - display value = `Not available`
   - provenance status = `unavailable`
   - reason = `both_sources_absent` or the more specific missing reason.
5. If one valid candidate exists, select it.
6. If two or more valid candidates exist:
   - compare ledger vs Yahoo when periods/units match;
   - if within tolerance, prefer ledger unless field-specific rules say Yahoo is primary;
   - if beyond tolerance, output null/Not available and block with `mismatch_blocked`.
7. For computed fields, compute only from already-selected components.
8. Persist both selected value and candidates/provenance.

## 9. Exact NVDA-class mismatch behavior

If NVDA ledger says market cap `$5.22T` and Yahoo/current snapshot says `$3.10T`, relative delta is ~40.6%.

Required output:

```json
{
  "key_financials": {
    "market_cap": null,
    "market_cap_display": "Not available"
  },
  "key_financials_provenance": {
    "fields": {
      "market_cap": {
        "status": "blocked",
        "reason_code": "mismatch_blocked",
        "selected_source": null,
        "selected_path": null,
        "normalized_value": null,
        "display_value": "Not available",
        "comparison": {
          "tolerance_rel": 0.10,
          "relative_delta": 0.406,
          "accepted": false
        }
      }
    }
  }
}
```

The PDF must render `Not available` or a concise source mismatch note. It must not choose `$3.10T`, `$5.22T`, or an LLM-estimated value silently.

## 10. Renderer rules

Once `key_financials_provenance` exists:

- render `overview["key_financials"]` only;
- do not use `yf_data` to fill missing selected fields;
- do not recompute PEG/dividend inside `_render_kpis` except through precomputed canonical fields;
- display source from provenance, not a hardcoded `Yahoo Finance` label;
- if a field is blocked/unavailable, render `Not available` with reason where appropriate;
- keep legacy fallback only for cached artifacts without provenance, and mark/log `legacy_unprovenanced_fallback`.

## 11. Cache rules

- `OVERVIEW_CACHE_VERSION` must be bumped when adding provenance schema.
- Cached EN and JP overview payloads must include the same canonical numeric/provenance payload.
- JP translation may translate prose, labels, and display wording, but must not alter numeric normalized values or provenance candidates.
- Any cache hit lacking `key_financials_provenance.schema_version == 1` is legacy and should be either regenerated or rendered via explicit legacy fallback warning.

## 12. Persistence rules

When `pipeline.py` writes `company_overview_{ticker}.json`, it must include:

- `key_financials`;
- `key_financials_provenance`;
- `source_snapshot_metadata`, including Yahoo snapshot timestamp/path and ledger build timestamp;
- enough candidate data to debug mismatches without re-running the provider.

## 13. Tests required before implementation is accepted

### Unit tests — resolver

Create tests for a resolver such as `_resolve_key_financials(...)`:

- selects ledger when ledger/Yahoo agree within tolerance;
- blocks market cap when disagreement > 10%;
- handles both sources absent;
- handles malformed strings / NaN / placeholders;
- normalizes percent vs ratio for margins/dividend;
- preserves FCF sign;
- validates 52W low/high invariant;
- computes dividend yield from selected dividend rate and price;
- computes PEG from selected P/E and earnings growth when available.

### Integration tests — Company Overview

- LLM returns numeric `key_financials`; canonical resolver overrides those numbers.
- fallback overview uses the same resolver and emits provenance.
- JP overview preserves numeric/provenance payload from EN.
- cache schema version invalidates old unprovenanced payloads.

### Renderer tests — PDF/Markdown

- `_render_kpis` does not fill a blocked field from `yf_data`.
- source labels are derived from provenance.
- legacy unprovenanced fallback remains backward-compatible but is explicitly covered.

### Fixture tickers

Minimum regression set:

- NVDA: mismatch-blocking behavior.
- AAPL: normal selected-fields path.
- GOOGL: alias/large-cap normal path and 52W range.

## 14. Acceptance checklist

Implementation is accepted only when:

- [ ] `key_financials_provenance.schema_version == 1` exists in generated Company Overview JSON.
- [ ] LLM numeric output cannot become source-of-truth.
- [ ] PDF renderer no longer performs hidden `fin or yf_data` selection for provenanced fields.
- [ ] >10% mismatches are blocked, not silently resolved.
- [ ] Missing values are coded with reason codes.
- [ ] tests cover NVDA/AAPL/GOOGL.
- [ ] WIKI updated with the implemented behavior and verification commands.
- [ ] Production/browser PDF check confirms no stale legacy artifact is served as current Company Overview.

## 15. Non-goals

This contract does not require changing the user-facing visual design of the PDF.

This contract does not require replacing yfinance.

This contract does not require all fields to be available. It requires unavailable fields to be explicit, sourced, and deterministic.

## 16. Immediate next manual task

After this spec is persisted and reviewed, the next manual implementation task should be:

1. add canonical resolver in `backend/company_overview.py`;
2. wire ledger/source context from `backend/pipeline.py`;
3. simplify `_render_kpis` to consume provenance;
4. add resolver + renderer tests;
5. regenerate and inspect Company Overview PDF for NVDA/AAPL/GOOGL.
