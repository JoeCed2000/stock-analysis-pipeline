# SA-P0-UXDATA-DISCOVERY — Loading + empty sections + PDF transcript URL

Task: `t_1ccf556e`
Date: 2026-05-27 22:32 CEST
Project: `/home/ced/codex-projects/stock-analysis-pipeline`
Branch: `kanban/spec-fonctionnelle-sa`
Scope: READ-ONLY discovery. Application code was not modified.
Allowed write target: this file only.

## Executive summary

The four reported symptoms do not share one single backend outage. They are three mostly independent data/UX-contract defects plus one PDF rendering/provenance defect:

| Area | Layer attribution | Root cause summary | Evidence confidence |
|---|---|---|---|
| A — loading/state machine | Frontend state model + backend status contract | `progress.ticker` is overloaded with ticker, backend free-text progress, and dossier phase text. The UI has a disabled but still-mounted `TickerInput`; the visible loader can replace the ticker identity with `Starting analysis...` because message and active ticker are the same field. There is no real phase enum/state machine. | High |
| B — Peer Benchmark | API payload partially populated + frontend/PDF contract mismatch | The route is not empty for NVDA/AAPL/TSLA, but only a small subset of metric keys is `available`; absent/unavailable metrics are silently dropped or shown as N/A. The deep-dive/PDF mapper also discards detailed benchmark metrics and stores only labels/summary, making the section sparse/non-actionable. | High |
| C — TTM Summary + Quality/Returns | Frontend chart math/availability handling | Backend JSON is sanitized and contains no NaN/inf. NaN is created client-side: `calculateStats()` does not filter invalid values for absolute mode, TTM/quality fields are absent/null for most quarters, and the SVG area uses `points[n-1]` where `n=sorted.length`, not `points.length`, producing invalid paths and missing curves. | High |
| D — PDF transcript link mismatch | PDF renderer/link annotation | Current generated PDF has the same canonical specific transcript URL in first-page text and appendix, but only the appendix exposes proper clickable link annotations. The first-page document table renders the raw long URL as wrapped text; PDF viewers can auto-link only the first wrapped fragment, causing 404-like behavior. | High |

Recommended downstream split: 4 implementation tasks, one per area, with A and C first because they are user-visible core UX/data correctness; B can follow with contract alignment; D is a targeted renderer fix + PDF regression test.

---

## Reproduction / verification evidence

### API probes across sibling tickers

Verified tickers: `NVDA`, `AAPL`, `TSLA`.
Verified environments: local `http://127.0.0.1:8780/api` and production host variants:
- `https://sa.cedlabusa.net/api/...`
- `https://sa.cedlabusa.net/stock-analysis/api/...`

Observed results:

| Probe | NVDA | AAPL | TSLA | Notes |
|---|---:|---:|---:|---|
| `/api/peer-benchmark/{ticker}` status | 200 / `available` | 200 / `available` | 200 / `available` | Local/prod shapes matched. |
| Peer sample size | 4–5 | 4–5 | 4–5 | `peer_context.available=true`. |
| Peer benchmark keys | `pe_ttm`, `ps_ttm`, `pb_ratio`, `pe_forward`, `peg_ratio`, `total_debt` | same | same | Only subset is actionably available. |
| Available peer metrics | `ps_ttm`, `pb_ratio`, `total_debt` | same pattern | same pattern | `pe_ttm`, `pe_forward`, `peg_ratio` generally unavailable in samples. |
| `/api/metrics-history/{ticker}` status | 200 | 200 | 200 | Local/prod shapes matched. |
| Metrics quarters | 7 | 7 | 7 | No NaN/inf in API payload. |
| Derived TTM/quality density after frontend-equivalent enrichment | 2/7 non-null | 2/7 non-null | 2/7 non-null | Many missing/absent values feed frontend chart math. |

### Generated PDF evidence

Sample artifact inspected:
`analyses/2026-05-27_205546_NVDA_NVIDIA_Corp/07_final_report/earnings_deep_dive.pdf`

Facts:
- File exists: 380,124 bytes, 23 pages.
- Page 1 text includes `https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/` in the Earnings Documents table.
- Page 23 Sources appendix includes the same canonical URL.
- PyMuPDF link annotations:
  - page 1 links: `https://www.nvidia.com` only.
  - page 23 links: transcript, IR, website, press release, Yahoo, SEC, Finnhub.
- Direct URL checks:
  - `https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/` returned HTTP 200.
  - generic listing `https://stockanalysis.com/stocks/nvda/transcripts/` returned HTTP 200.
  - SeekingAlpha transcript fallback returned HTTP 403, expected for bot-protected SA pages and not the canonical PDF appendix link.

---

## A — Loading / analysis state machine

### Verified facts

Code path:
- `frontend/src/App.jsx:22-25` keeps `loading` and `progress` as separate React state, but `progress` shape is `{ current, total, ticker, companyName }`.
- `frontend/src/App.jsx:125-139` starts an async analysis, sets `loading=true`, clears results, then starts a synthetic timer that increments `progress.current` independently of real backend phase.
- `frontend/src/App.jsx:143-207` polls `/api/analyze/job/{job_id}` every 3 seconds; while processing, if `job.progress` exists, it writes `setProgress(p => ({ ...p, ticker: job.progress }))`.
- `frontend/src/App.jsx:160-180` switches into dossier polling after `job.status === 'done'` and again writes dossier message text into `progress.ticker` (`📊 Building dossier… X/7`).
- `frontend/src/App.jsx:287-289` currently renders `<TickerInput onAnalyze={handleAnalyze} loading={loading} ... />` whenever `mode === 'single'`; it is not wrapped in `!loading` anymore.
- `frontend/src/components/TickerInput.jsx:106-117` keeps the text area visible but disables it during loading.
- `frontend/src/components/TickerInput.jsx:120-184` keeps parsed ticker chips visible when `items.length > 0`; clicks are disabled during loading.
- `frontend/src/components/SmartLoader.jsx` displays the `ticker` prop, so it receives either a ticker symbol or free-text phase/status depending on current `App.jsx` writes.
- Backend async route anchors:
  - `backend/main.py:1434` defines `POST /api/analyze/async`.
  - `backend/main.py:1563` defines `GET /api/analyze/job/{job_id}`.
- `backend/job_store.py` stores job status/progress as mutable free text: default `status="pending"`, `progress="Queued N ticker(s)"`, later updated to strings such as `Starting analysis...`.

### Hypotheses rejected

- Rejected: “The ticker input component is currently unmounted during loading.” Current `App.jsx` mounts `TickerInput` whenever `mode === 'single'`; only `AboutSection` and mode tabs are explicitly hidden behind `!loading`.
- Rejected: “This is purely a backend latency issue.” The misleading UI is reproducible from state shape alone: frontend conflates active ticker identity and phase copy in `progress.ticker`.
- Rejected: “Synthetic progress alone is the root cause.” The synthetic timer is a problem, but the user-visible replacement of ticker identity happens specifically when backend/job/dossier messages are assigned to the `ticker` display field.

### Root cause

The loading UX has no typed state machine. It uses one overloaded field (`progress.ticker`) for at least three different concepts:
1. selected/current ticker (`NVDA`),
2. backend job status text (`Starting analysis...`),
3. dossier-build status text (`📊 Building dossier… X/7`).

That makes the loader look like the ticker/chip is replaced by `starting analysis` even if the input itself remains mounted. The backend only exposes `status` + free-text `progress`, not a phase enum with stable semantics. Frontend then invents additional synthetic progress and phase text.

### Impact radius

- Frontend-only UI behavior: `App.jsx`, `SmartLoader.jsx`, `TickerInput.jsx`.
- Backend contract likely needs enrichment if Ced wants a true phase-driven state machine rather than frontend inference.
- Batch/single analysis flows may diverge if only `App.jsx` is fixed.

### Proposed fix

Introduce a minimal explicit analysis state contract:

```text
analysisState = {
  phase: 'idle' | 'queued' | 'analyzing' | 'generating_pdf' | 'building_dossier' | 'finalizing' | 'done' | 'error',
  tickers: ['NVDA'],
  activeTicker: 'NVDA',
  message: 'Starting analysis…',
  current: 0,
  total: 1,
  dossierSectionsDone: 0,
  dossierSectionsTotal: 7
}
```

Frontend rules:
- Keep `TickerInput` and chips mounted while loading; disabled is fine.
- `SmartLoader` receives `activeTicker` and `message` as separate props.
- Never write backend free-text into ticker identity.
- Replace synthetic-only progress with phase-driven progress; if backend cannot provide numeric progress, display indeterminate phase copy honestly.

Backend rules:
- `/api/analyze/job/{job_id}` should return stable `phase` and optional `phase_detail`, not just free-text `progress`.
- Keep backward-compatible `progress` during migration if needed.

### Tests to add/update

- Frontend component test: submit `NVDA`, set loading/job progress to `Starting analysis...`, assert `NVDA` chip remains visible and loader message is separate from active ticker.
- State reducer/unit test: phase transitions `idle -> queued -> analyzing -> building_dossier -> done` preserve `activeTicker`.
- API contract test for job status: response includes valid phase enum and message for pending/processing/done/error jobs.

### Risk

Medium. The UI can be fixed frontend-only, but a robust state machine requires backend status-contract changes. Keep compatibility with current job payloads to avoid breaking production while deploying the frontend fix.

---

## B — Peer Benchmark unusable / empty

### Verified facts

Code path:
- Frontend route wrapper exists in `frontend/src/api.js` / direct component fetch usage.
- Main component: `frontend/src/components/PeerBenchmark/PeerBenchmarkGroup.jsx`.
- Backend route: `backend/routes/peer_benchmark.py`.
- Peer engine/data path: `backend/peer_universe.py`, `backend/peer_batch.py`, `backend/peer_benchmark.py`, `backend/valuation.py`, `backend/market_data.py`, `backend/models.py`.
- Deep-dive/PDF mapper path: `backend/earnings_deep_dive/mapper.py:2762-2834` builds `PeerBenchmarkSection`.
- PDF renderer path: `backend/earnings_deep_dive/pdf_renderer.py:1466-1530` renders only peer group, 3 relative labels, and summary.

API facts from local + prod probes for `NVDA`, `AAPL`, `TSLA`:
- `/api/peer-benchmark/{ticker}` returns HTTP 200 and `status="available"`.
- `peer_context.available=true` and sample size is generally 4–5.
- Payload benchmark object is keyed by metric name; it is not a list.
- Metric keys observed: `pe_ttm`, `ps_ttm`, `pb_ratio`, `pe_forward`, `peg_ratio`, `total_debt`.
- Available/actionable metric subset in samples is mostly `ps_ttm`, `pb_ratio`, `total_debt`.
- `pe_ttm`, `pe_forward`, `peg_ratio` are present but often `status != "available"` because either subject or peer values are missing.
- Warnings arrays were empty in sampled responses, even though key valuation metrics were unavailable.

Frontend facts:
- `PeerBenchmarkGroup.jsx` expects `benchmarks` as an object keyed by metric, which matches the current API contract.
- UI metric catalog includes keys not returned in sampled API payloads (`ev_ebitda`, `p_fcf`), so these sections silently drop rows.
- Rows only become meaningful when `benchmark.status === 'available'`; unavailable rows render as muted/N/A and can make a section look empty/non-actionable.
- Missing keys are filtered out rather than explained as “metric not supported by backend response”.

Deep-dive/PDF facts:
- `report_model.py:357-381` defines `PeerBenchmarkSection` with `valuation_metrics` and `quality_metrics` dicts.
- `mapper.py:2818-2829` computes `benchmarks` but only maps derived labels and summary to `PeerBenchmarkSection`.
- `mapper.py` does not populate `PeerBenchmarkSection.valuation_metrics` or `quality_metrics` from the detailed benchmark results.
- `pdf_renderer.py:1497-1529` only renders the 3 relative labels and summary; no metric table is rendered.

### Hypotheses rejected

- Rejected: “The peer benchmark API is down/empty for NVDA.” Repeated local/prod probes returned 200 with `status=available` and populated payloads.
- Rejected: “The frontend expects a list but backend sends an object.” Current component expects a metric-keyed object.
- Rejected: “This is only stale cache.” Local and prod/base-path variants returned consistent shapes for NVDA/AAPL/TSLA.

### Root cause

Peer Benchmark is not empty at the API layer, but the product contract is incomplete across API/frontend/PDF:

1. API returns a narrow/partial metric set for sampled tickers; many important valuation metrics are unavailable.
2. Frontend silently drops absent metrics and gives weak/no explanation for unavailable key metrics.
3. Frontend metric catalog and backend metric payload are not aligned (`ev_ebitda`/`p_fcf` in UI, absent in payload samples).
4. PDF/deep-dive mapper discards detailed benchmark metrics entirely and only keeps labels/summary, which makes the section non-actionable in the report.
5. The backend warning model does not surface enough “why unavailable” detail when the route overall status is `available`.

### Impact radius

- Live frontend PeerBenchmark component can look sparse/non-actionable even when API status is `available`.
- Deep-dive/PDF Peer Benchmark section is structurally too thin because detailed metrics are not mapped/rendered.
- Affects all tickers using the same curated peer benchmark route, not NVDA-only. Verified pattern on NVDA/AAPL/TSLA.

### Proposed fix

Contract alignment task:
- Define canonical peer metrics by category: valuation, growth, quality, balance-sheet/risk.
- Make backend response explicitly include:
  - `supported_metrics`,
  - `available_metrics`,
  - `unavailable_metrics` with reasons (`subject_missing`, `peer_sample_missing`, `not_supported`),
  - `peer_sample_size` per metric.
- Align frontend metric catalog exactly with backend-supported keys.
- Replace silent filtering with visible explanatory empty states per category.
- Populate `PeerBenchmarkSection.valuation_metrics` and `quality_metrics` (or add a structured `benchmarks` field) from the API/engine output.
- Render a compact PDF peer benchmark table with subject value, peer median, percentile/spread, and status/reason.

### Tests to add/update

- API contract tests for `/api/peer-benchmark/{ticker}` with partial data: response must expose unavailable reasons and per-metric sample sizes.
- Frontend tests: category with absent metrics displays a clear “not available because …” state, not a blank section.
- Mapper test: detailed benchmark values from `buildPeerBenchmarkSummary()` are preserved in `PeerBenchmarkSection`.
- PDF renderer test: Peer Benchmark section includes at least one metric row when detailed benchmarks exist.
- Cross-ticker smoke: NVDA/AAPL/TSLA should each render available metrics and explicit unavailable reasons.

### Risk

Medium. Need avoid over-promising availability for metrics yfinance/peer snapshots cannot reliably provide. Prefer transparent partial availability over hiding rows.

---

## C — TTM Summary + Quality/Returns NaN and missing curves

### Verified facts

Backend facts:
- `/api/metrics-history/{ticker}` is implemented at `backend/main.py:781-908`.
- It merges quarter keys from yfinance quarterly financials, cash flow, and balance sheet.
- It returns newest-first quarters (`backend/main.py:893`).
- `_safe_float()` maps pandas/NaN values to `None` (`backend/main.py:911-925`).
- `_sanitize_json()` was also observed in the backend and recursively replaces NaN/inf with `None` before JSON responses.
- Local/prod probes for `NVDA`, `AAPL`, `TSLA` returned 7 quarters and no NaN/inf values in JSON.

Frontend facts:
- `MetricsHistoryChart.jsx:31` fetches `/stock-analysis/api/metrics-history/${ticker}`.
- `MetricsHistoryChart.jsx:42-50` calls `enrichData(data)` then reverses API newest-first into oldest-first.
- `MetricsHistoryChart.jsx:62-64` uses `PERIOD_OPTIONS = [5, 8, 12]`; with only 7 quarters, effective display period becomes 5, not 7.
- `chartUtils.js:188-263` computes TTM and quality metrics only when `i >= 3`, using rolling 4-quarter windows.
- Frontend-equivalent enrichment on live NVDA/AAPL/TSLA data showed TTM/quality metrics had only 2 non-null points out of 7; 3 rows lacked the fields entirely and 2 rows had null due input gaps.
- `chartUtils.js:108-135` in `calculateStats()` filters nulls only for pct views; absolute mode uses `transformed` directly, including `undefined`/`null`.
- `MetricsHistoryChart.jsx:122-155` computes `maxVal`, `minVal`, `range`, `avgY`, and `pathD` from those stats/values; invalid entries can produce `NaN` geometry.
- `MetricsHistoryChart.jsx:141-147` builds `points` by filtering `displayVal == null`; valid point count can be much smaller than `sorted.length`.
- `MetricsHistoryChart.jsx:131` sets `n = sorted.length`, but `MetricsHistoryChart.jsx:265` uses `points[n-1]` and `points[0]` to close the area path. When `points.length < sorted.length`, this yields `undefined` coordinates in the SVG path and missing/invalid curves.

### Hypotheses rejected

- Rejected: “The backend sends literal NaN values.” API payload probes found `nan_inf_values=0` for NVDA/AAPL/TSLA, local and prod.
- Rejected: “This is a ticker-specific data issue.” Same 7-quarter/partial-derived pattern reproduced on NVDA, AAPL, and TSLA.
- Rejected: “Curves are missing because no data exists at all.” There are two valid TTM/quality points after enrichment, but frontend math/path handling cannot robustly render sparse derived series.

### Root cause

The NaN/missing-curve symptom is generated in the frontend chart layer, not the metrics-history API layer.

There are two coupled defects:

1. Invalid values are not normalized before chart statistics/geometry.
   - Absolute view keeps `undefined`/`null` values in `stats.values`.
   - `Math.max(...values)`, `Math.min(...values)`, average, and axis/point calculations can become NaN.

2. Sparse derived metrics break area path construction.
   - TTM/quality metrics are sparse by design because they need 4-quarter windows and complete inputs.
   - `points` filters invalid values, but the area path indexes it with `n=sorted.length`, not `points.length`.
   - This can emit `undefined`/NaN path coordinates and make the curve disappear.

The 7-quarter backend coverage amplifies this because the period selector falls back to 5Q, leaving only a very small valid point set for TTM/quality categories.

### Impact radius

- All TTM Summary metrics: `revenue_ttm`, `ebitda_ttm`, `net_income_ttm`, `operating_cash_flow_ttm`, `free_cash_flow_ttm`, `fcf_margin_ttm`, `eps_ttm`, `ebitda_margin_ttm`.
- All Quality/Returns metrics: `roe`, `roa`, `roic`, `fcf_conversion_ttm`, `fcf_ttm_per_share`, `revenue_ttm_per_share`, `ni_ttm_per_share`.
- Any future chart metric with sparse/null-heavy data can hit the same path/stats bug.
- Verified across NVDA/AAPL/TSLA.

### Proposed fix

Frontend chart hardening task:
- Centralize transformation in `chartUtils.transformValues()`; remove duplicated transform code in `MetricsHistoryChart.jsx`.
- Normalize chart series with a helper that keeps only finite numeric values for geometry/statistics.
- In absolute mode, filter non-finite values exactly like pct modes.
- Compute path closure using `points.length`, not `sorted.length`.
- If `points.length < 2`, render a clear empty state for that metric/category (`Not enough complete TTM/quality data: need 2 valid points after 4-quarter rolling window`) rather than an SVG with NaN coordinates.
- Period handling: when `maxAvailable=7`, either allow a `7Q` effective period or label the fallback clearly (`Showing 5 of 7 available quarters`) to avoid hiding usable history.

### Tests to add/update

- `chartUtils.calculateStats()` unit test: absolute mode with `[undefined, null, 10, 12]` returns finite stats over `[10,12]` or explicit insufficient-data state, never NaN.
- `MetricsHistoryChart` render test: sparse TTM metric with 2 valid points produces a valid SVG path without `NaN`/`undefined`.
- Render test: metric with fewer than 2 finite points shows explanatory empty state.
- API smoke remains useful but is not sufficient: assert `/api/metrics-history/{ticker}` has no NaN/inf for NVDA/AAPL/TSLA.

### Risk

Low-to-medium. Most fix is frontend hardening, but visual chart behavior needs browser/DOM verification after implementation. Do not validate this only with curl.

---

## D — PDF transcript link mismatch / first-page 404

### Verified facts

Source/model path:
- `backend/earnings_deep_dive/report_model.py:26-35` defines `SourceRef`.
- `backend/earnings_deep_dive/report_model.py:38-56` defines `ClaimSource`.
- `backend/earnings_deep_dive/report_model.py:59-70` supports table row provenance fields.
- `backend/earnings_deep_dive/mapper.py` has source helpers including `_seeking_alpha_transcripts_url`, `_source`, and claim-source builders.
- `backend/earnings_deep_dive/mapper.py:1990-2054+` builds `SourceRef` rows for transcript, IR, official website, press release, presentation, plus data sources (Yahoo, SEC, Finnhub).
- `backend/earnings_deep_dive/pdf_renderer.py:597-606` resolves source URLs/notes from `report.sources` by label matching.
- `backend/earnings_deep_dive/pdf_renderer.py:620+` builds the first-page “Earnings Documents” table.
- `backend/earnings_deep_dive/pdf_renderer.py:1855+` injects the earnings-documents story early in the PDF.
- `backend/earnings_deep_dive/pdf_renderer.py:2048-2118` renders final source sections.

Generated artifact facts:
- Sample NVDA deep-dive PDF page 1 text includes the transcript URL `https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/` in the first-page Earnings Documents table.
- The appendix page 23 includes the same transcript URL in Sources.
- PyMuPDF extracted clickable link annotations only for `https://www.nvidia.com` on page 1; it did not extract a transcript link annotation from the first-page table.
- Page 23 appendix did have a clickable transcript annotation pointing to the exact canonical URL.
- The first-page table text wraps the long URL across lines (`.../q1-2` then `027/` in extracted text), which can make PDF viewers auto-detect a truncated partial URL and navigate to a 404-like URL.
- Direct check of the canonical appendix URL returned HTTP 200.

### Hypotheses rejected

- Rejected: “The canonical transcript URL itself is currently dead.” The specific StockAnalysis transcript URL returned HTTP 200.
- Rejected: “The first page and appendix always use different source data.” In the inspected generated artifact, the text value is the same canonical specific transcript URL.
- Rejected: “This is only a mapper-source issue.” The generated PDF already contains the canonical URL in both sections; the first-page failure is in rendering/link annotation/wrapping behavior.

### Root cause

The first-page Earnings Documents table renders the raw long transcript URL as table text, not as a stable hyperlink annotation with a safe display label. Because the URL wraps across a line break, PDF viewers can auto-detect only the first line fragment and open a truncated URL, causing the reported 404. The final Sources appendix uses proper clickable links and therefore works.

This is why Ced sees “appendix link works, first-page/table link 404”: the underlying canonical URL can be identical, but the first-page rendering method makes the visible/clicked link fragile.

### Impact radius

- Transcript row in the first-page Earnings Documents table.
- Any other long raw URL in the same table can suffer from the same auto-link/wrapping issue, especially press-release URLs.
- PDF output only; API/source metadata can be correct while rendered first-page behavior is broken.

### Proposed fix

Single canonical rendering rule:
- The first-page table must reuse the exact `SourceRef.url` used by the appendix.
- Render long source URLs as explicit ReportLab links with short display labels, for example:
  - display text: `Transcript — StockAnalysis.com`
  - href: canonical `SourceRef.url`
- Do not rely on PDF viewer auto-linking of raw URL text.
- For each document row, pass both `display_text` and `href` to the table paragraph/link constructor.
- Optionally show host/domain as secondary muted text, not the full raw URL.

Regression test:
- Generate a small PDF with a transcript source URL long enough to wrap.
- Use PyMuPDF to extract link annotations from the first-page Earnings Documents area and the final Sources appendix.
- Assert both contain the same canonical transcript URI.
- Assert no annotation URI contains a truncated fragment such as `/q1-2` when canonical is `/q1-2027/`.

### Risk

Low. Targeted renderer fix. Main risk is ReportLab paragraph/table link syntax compatibility and preserving layout. Must verify by opening/extracting generated PDF, not just unit tests.

---

## Downstream implementation task recommendation

### Task 1 — SA-P0-LOADING-STATE-MACHINE

write_scope:
- `frontend/src/App.jsx`
- `frontend/src/components/SmartLoader.jsx`
- `frontend/src/components/TickerInput.jsx` if needed
- `backend/job_store.py` and `backend/main.py` only if adding backend `phase` fields
- targeted tests for state/progress contract

acceptance_criteria:
- Ticker input and selected ticker chips remain visible during analysis.
- Loader displays active ticker and phase/message separately.
- No UI field named `ticker` receives free-text phase messages.
- Job status response has typed phase or frontend has an explicit compatibility adapter.

Dependencies: none. Should run first because it fixes the core production-visible analysis UX.

### Task 2 — SA-P0-METRICS-HISTORY-CHART-HARDENING

write_scope:
- `frontend/src/components/MetricsHistoryChart.jsx`
- `frontend/src/components/chartUtils.js`
- chart utility/component tests

acceptance_criteria:
- Sparse/null-heavy metrics never generate `NaN` or `undefined` in SVG paths or labels.
- TTM Summary and Quality/Returns render either valid curves or clear insufficient-data states.
- NVDA/AAPL/TSLA tested through API + browser/DOM.

Dependencies: none. Can run in parallel with Task 1 if file overlap is avoided; otherwise run after Task 1 if both touch shared frontend tests.

### Task 3 — SA-P0-PEER-BENCHMARK-CONTRACT

write_scope:
- `backend/routes/peer_benchmark.py`
- `backend/peer_benchmark.py` / models if needed
- `frontend/src/components/PeerBenchmark/PeerBenchmarkGroup.jsx`
- `backend/earnings_deep_dive/report_model.py`
- `backend/earnings_deep_dive/mapper.py`
- `backend/earnings_deep_dive/pdf_renderer.py`
- API/frontend/mapper/PDF tests

acceptance_criteria:
- API exposes supported/available/unavailable metric reasons.
- Frontend categories align with backend-supported metrics and explain unavailable data.
- PDF preserves and renders detailed peer metrics, not only labels/summary.
- NVDA/AAPL/TSLA all show non-empty actionable content or explicit reasons.

Dependencies: can follow Task 2; touches different areas but includes frontend work.

### Task 4 — SA-P0-PDF-TRANSCRIPT-LINK-CANONICALIZATION

write_scope:
- `backend/earnings_deep_dive/pdf_renderer.py`
- maybe `backend/earnings_deep_dive/mapper.py` only if canonical source URL helper is missing
- PDF regression tests

acceptance_criteria:
- First-page Earnings Documents transcript link annotation equals appendix transcript link annotation.
- Long raw URLs are not relied on for auto-linking.
- Generated NVDA PDF link extraction confirms canonical transcript URI on first page and appendix.

Dependencies: none. Small targeted fix; can run independently.

---

## Commands / inspections run

Representative non-mutating checks used during discovery:

```bash
tb sa-check
tb rg "TickerInput|startingAnalysis|SmartLoader|loading|progress" frontend/src/App.jsx
tb rg "metrics-history|MetricsHistory|NaN|pctChange|toFixed|yoyIsAvailable" backend frontend/src tests
tb rg "transcript_url|transcript_source|StockAnalysis|stockanalysis" backend
tb rg "class PeerBenchmarkSection|relative_valuation_label|peer_benchmark" backend/earnings_deep_dive/report_model.py backend/earnings_deep_dive/pdf_renderer.py
git status --short
```

Python/execute_code inspections were used to:
- read targeted source windows without modifying code,
- probe local/prod API payloads for NVDA/AAPL/TSLA,
- count NaN/inf occurrences in API JSON,
- emulate frontend derived TTM/quality metric density,
- enumerate generated analysis artifacts,
- parse generated PDFs with PyMuPDF and compare page link annotations,
- check transcript URLs via HTTP GET with a browser-like User-Agent.

---

## Definition-of-done check for this discovery

- [x] One section per symptom A/B/C/D.
- [x] Each section has Verified facts, Hypotheses rejected, Root cause, Impact radius, Proposed fix, Tests, Risk.
- [x] NVDA + sibling tickers AAPL/TSLA considered.
- [x] Layer attribution provided.
- [x] Explicit statement: symptoms do not share one single root cause.
- [x] Downstream task split proposed with write scopes/dependencies.
- [x] No application-code edits made by this discovery task.
