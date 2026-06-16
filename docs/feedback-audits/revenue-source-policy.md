# NVDA revenue estimate source policy

Task: `t_77a5af44`  
Project: Stock Analysis Pipeline  
Decision type: spec / source policy  
Date: 2026-06-16  
Status: DECIDED — no implementation in this card

## 1. Decision

Investing.com `79.19B` is allowed for the NVDA FY2027 Q1 revenue estimate, but only as an explicitly cited analyst-consensus estimate override.

It is not allowed as:

- company-reported actual revenue;
- SEC / 10-Q line-item data;
- management guidance;
- an uncited silent replacement for Yahoo Finance/yfinance.

For this feedback slice, the approved value is:

| Metric | Actual | Estimate | Surprise | Approved source |
|---|---:|---:|---:|---|
| EPS | `$1.87` | `$1.77` | `+5.65%` | Investing.com analyst consensus |
| Revenue | `$81.6B` | `$79.19B` | `+3.04%` | Investing.com analyst consensus |

## 2. Evidence used

WIKI_EVIDENCE:

- Project wiki: `/home/ced/codex-projects/docs/llm-wiki/projects/stock-analysis-pipeline.md` lines 103-157 documents the mandatory Wiki + CodeGraph gate, stack, validation rules, and the anti-invention rule: every financial datum must be sourced; missing data must remain unavailable rather than invented.
- Project root `WIKI.md` documents the current NVDA feedback repair context and recurring PDF validation/source-display fixes.

PLAN_EVIDENCE:

- Source plan: `/mnt/c/Users/cedon/Desktop/SA/PLAN_conseil_kanban_NVDA_feedback_2026-06-16.md` lines 23-28 states the Investing.com reference table: EPS actual `$1.87`, estimate `$1.77`, surprise `+5.65%`; revenue actual `$81.6B`, estimate `$79.19B`, surprise `+3.04%`.
- The same plan lines 59-63 identify SA-FB-02: current report says revenue estimate is `Not disclosed`; expected output is estimated revenue `$79.19B`, `vs Estimate +3.04%`, with a council decision on adopting Investing.com vs Yahoo Finance.

SOURCE_PROOF:

- Screenshot path exists: `/mnt/c/Users/cedon/Desktop/SA/2026-06-11_061719_Screenshot_2026-06-10_at_10.48.22_PM.png`.
- Gap review path exists: `/mnt/c/Users/cedon/Desktop/SA/REVUE_ecarts_NVDA_deepdive_2026-06-16.md`; lines 5, 14, and 31 repeat the same Investing.com evidence and mark the revenue estimate gap.
- OCR/vision verification was degraded in this run because the configured vision model is unavailable under the current Codex account. The decision therefore relies on the already-produced plan/gap-review transcription plus the screenshot file existence, not fresh OCR.

GRAPH_EVIDENCE:

- `codegraph status` on `/home/ced/codex-projects/stock-analysis-pipeline` returned an up-to-date index: 336 files, 7,761 nodes, 15,151 edges.
- `codegraph query '_extract_quarterly_comparison revenue_estimate eps_estimate revenue_vs_estimate FinancialMetrics'` identified:
  - `backend/pipeline.py:1009` — `_extract_quarterly_comparison()` obtains yfinance EPS actual/estimate and yfinance `info.revenueEstimate` when available.
  - `backend/pipeline.py:1250` — `_deep_dive_metrics()` maps quarterly comparison + overrides into `FinancialMetrics`.
  - `backend/earnings_deep_dive/schemas.py:11` — `FinancialMetrics` carries `eps_estimate`, `revenue_estimate`, `consensus_provider`.
  - `backend/tests/test_revenue_estimate.py` and `tests/test_quarterly_comparison.py` cover the prior no-fabrication behavior.
- `codegraph callers _extract_quarterly_comparison` identified one direct caller: `_deep_dive_metrics` in `backend/pipeline.py:1250`.

SYMBOL_PLAN:

Serena tool access is degraded in this worker context, so the symbol plan is derived from CodeGraph + direct source inspection:

- Source ingestion / default estimates: `backend/pipeline.py::_extract_quarterly_comparison`.
- Final metrics precedence: `backend/pipeline.py::_deep_dive_metrics`, where consensus overrides must have final priority over yfinance for estimate fields only.
- Override registry: `backend/consensus_overrides.py` + `backend/config/consensus_overrides.json`.
- Rendering/prompt consumers: `backend/earnings_deep_dive/prompts.py` consumes `consensus_provider`, `eps_estimate`, `revenue_estimate`; PDF renderer displays final model/source fields.

## 3. Fallback order

### 3.1 Company-reported actuals

Actuals must remain sourced from primary/company/filing data:

1. Company-reported earnings / SEC / IR / transcript-derived actuals.
2. yfinance statement rows only when they reflect company-reported values.
3. If no reviewed actual source exists: do not substitute analyst consensus; mark the actual as unavailable.

### 3.2 Analyst consensus estimates

Estimates use a separate precedence chain:

1. Explicit audited override registry for a ticker + fiscal period when backed by a client-approved reference artifact, e.g. Investing.com screenshot for NVDA FY2027 Q1.
2. yfinance `earnings_history` / `info.revenueEstimate` if present and period-compatible.
3. Manual one-run override only if it is documented with source artifact, as-of date, and provider label.
4. Otherwise: keep estimate unavailable.

Hard prohibition: never derive a revenue estimate by projecting prior-year revenue, using actual revenue, or back-solving from reported surprise unless the source artifact itself provides the estimate/surprise and the derivation is documented.

## 4. Audit citation wording

Client-facing wording should be explicit but not noisy:

- Table/source note: `Source: Investing.com analyst consensus, as of 2026-05-20.`
- Audit/internal trace: `NVDA FY2027 Q1 consensus estimate override — source artifact: Investing.com screenshot 2026-06-10; EPS est. $1.77; revenue est. $79.19B; revenue surprise +3.04%.`
- If the source is unavailable or not verified: `Revenue consensus estimate unavailable from reviewed sources.`

Do not write:

- `Source: SEC` for consensus estimates.
- `Source: yfinance` when an Investing.com override is displayed.
- `Guidance` for analyst consensus.
- `DATA NOT AVAILABLE` in client output; use client-safe unavailable wording.

## 5. Implementation boundary

This card is spec-only. It does not implement, modify, regenerate, or deploy any report.

If implementation is requested in a child card, it should be scoped separately and should verify:

1. the final metrics model contains `revenue_estimate = 79_190_000_000` and `consensus_provider = Investing.com (analyst consensus)` for NVDA FY2027 Q1;
2. EPS remains `$1.77` estimate and is not regressed;
3. generated PDF EPS & Revenue section displays revenue estimate `$79.19B` and `+3.04%` vs estimate;
4. source/audit citation uses the approved Investing.com consensus wording;
5. no fallback fabricates estimates when the override/source is absent.

## 6. Decision summary

Verdict: adopt Investing.com for this NVDA revenue estimate when represented as an audited, period-specific analyst-consensus override.

Ced consent is not needed for the policy decision because the plan explicitly asks the council to decide the Investing.com adoption question and provides the source artifact. Consent would be needed only before broadening this beyond NVDA/FY2027 Q1 into a live scraper or default provider integration.
