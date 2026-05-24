# Stock Analysis Pipeline — Performance Baseline v3

**Date:** 2026-05-24
**Branch:** `kanban/spec-fonctionnelle-sa`
**Commit baseline:** `ee38ffd` (last: docs(verdict): add scoring methodology note)
**Profile:** reviewer-qa (Kanban worker run #245)

---

## Environment

| Metric | Value |
|---|---|
| Hostname | LAPCED |
| OS | Linux 6.6.87.2-microsoft-standard-WSL2 |
| CPU | 8 cores |
| Python | 3.12.3 (GCC 13.3.0) |
| Virtual env | `/home/ced/codex-projects/stock-analysis-pipeline/.venv` |
| Project root | `/home/ced/codex-projects/stock-analysis-pipeline` |
| FastAPI | 0.136.1 |
| yfinance | 1.3.0 |
| Finnhub | 2.4.28 |
| ReportLab | 4.5.0 |
| PyMuPDF | 1.27.2.3 |

## API Provider Status

| Provider | Status | Notes |
|---|---|---|
| Yahoo Finance (yfinance) | ✅ Active | In-memory caching, cold ~10-20s, warm <1s |
| Finnhub | ✅ Active | Used for company profile, estimates |
| EDGAR (edgartools) | ⚠️ Partially broken | Proxy URL error: `Unknown scheme for proxy URL URL('')` |
| Seeking Alpha (RapidAPI) | 🔴 Blocked | HTTP 403: "You are not subscribed to this API." |
| Alpha Vantage | 🔴 Missing | `ALPHA_VANTAGE_API_KEY` not set in `.env` |
| Codex CLI | 🔴 Missing | Not found at `~/.hermes/profiles/reviewer-qa/home/.hermes/node/bin/codex` |

## LLM Provider Status

| Provider | Status | Notes |
|---|---|---|
| DeepSeek | ✅ Active | Primary LLM in `_llm_chat()` |
| Gemini | ✅ Active | Fallback LLM |
| Codex (GPT-5.5) | 🔴 Unavailable | CLI path missing in reviewer-qa profile |

---

## Scenario 1 — Full Ticker Analysis (`analyze_ticker_fast`)

Command:
```bash
cd /home/ced/codex-projects/stock-analysis-pipeline
.venv/bin/python3 benchmarks/bench_baseline_v3.py
```

### S1a: NVDA (NVIDIA Corp)

| Run | Wall (s) | CPU Δ (pct) | Peak RSS (MB) | Output (KB) | Files | Score | Notes |
|---|---|---|---|---|---|---|---|
| 1 (cold) | 20.57 | +7.8 | 225 | 2,465 | 23 | 33/40 BUY | Cold start, yfinance fetch + scoring |
| 2 (warm) | 7.81 | +0.5 | 233 | 2,465 | 23 | 34/40 BUY | yfinance in-memory cache active |
| 3 (warm) | 7.64 | +0.5 | 235 | 2,465 | 23 | 34/40 BUY | Stable warm performance |
| **Avg** | **12.01** | — | 231 | 2,465 | 23 | — | Cold→Warm: **2.7× speedup** |

### S1b: AAPL (Apple Inc)

| Run | Wall (s) | CPU Δ (pct) | Peak RSS (MB) | Output (KB) | Files | Score | Notes |
|---|---|---|---|---|---|---|---|
| 1 (cold) | 9.12 | +0.5 | 235 | 1,590 | 22 | 28/40 BUY | Cold start |
| 2 (warm) | 7.06 | +0.4 | 235 | 1,590 | 22 | 28/40 BUY | yfinance cache active |
| 3 (warm) | 8.21 | +0.4 | 235 | 1,590 | 22 | 28/40 BUY | Slight variance |
| **Avg** | **8.13** | — | 235 | 1,590 | 22 | — | Cold→Warm: **1.3× speedup** |

### S1 Observations

- **yfinance in-memory caching confirmed:** First run (cold) fetches live data; subsequent runs use TTL cache (1h). NVDA shows 2.7× speedup, AAPL 1.3×.
- **EDGAR broken:** `edgartools failed: Unknown scheme for proxy URL URL('')` — 10-K/10-Q extraction fails for all runs.
- **Codex CLI missing** in reviewer-qa profile. Falls back to DeepSeek for management analysis.
- **Seeking Alpha blocked** (403) for transcript sourcing. Pipeline falls back to free sources.
- **Deep-dive skipped internally:** `output_dir` validation rejects `/tmp/` paths; only `analyses/` subdirectories accepted.
- **Peak RSS stable at ~235MB** across all runs. Memory is dominated by FastAPI + yfinance in-memory structures.
- **Output consistent:** 22-23 files, 1.5-2.5MB per analysis (JSON, markdown, XLSX, PDF).

---

## Scenario 2 — Earnings Deep-Dive Generation (NVDA)

Command:
```bash
cd /home/ced/codex-projects/stock-analysis-pipeline
.venv/bin/python3 benchmarks/_rerun_s2.py
```

**Note:** S2 uses `analyses/` subdirectory for `output_dir` (required by `DeepDiveRequest` validator).

| Run | Wall (s) | Sections | PDF (KB) | Notes |
|---|---|---|---|---|
| 1 | 68.23 | 10 | 345 | LLM generation + PDF render |
| 2 | 55.13 | 10 | 335 | Slight variance in LLM response time |
| 3 | 60.51 | 10 | 347 | Consistent section count |
| **Avg** | **61.29** | 10.0 | 342 | — |

### S2 Observations

- **Fully LLM-bound:** 99% of time spent in `generate_deep_dive()` LLM calls (DeepSeek primary).
- **Stable output:** 10 sections consistently, PDF size 335-347KB.
- **Transcript sourced successfully** from free provider (StockAnalysis.com, added via commit `1aeeae0`).
- **QA Warning present:** "Missing mandatory sections: Geographic Segments" — segments data unavailable from yfinance for NVDA.
- **URL validation runs:** 3/6 URLs marked dead (investor.nvidia.com 403, yahoo finance 503, seekingalpha 403) — adds ~500ms overhead.
- **Peak RSS:** ~250MB during full deep-dive pipeline.

### First-run S2 attempt (failed — output_dir validation)

| Run | Wall (s) | Status | Notes |
|---|---|---|---|
| 1 | 2.12 | ❌ FAILED | `output_dir` must be under `analyses/`, got `/tmp/` |
| 2 | 1.18 | ❌ FAILED | Same validation error |
| 3 | 2.36 | ❌ FAILED | Same validation error |

**Finding:** `DeepDiveRequest.output_dir` is validated by Pydantic to require an `analyses/` subpath. This is a design constraint, not a bug. Benchmarks must use `analyses/bench_*` paths.

---

## Scenario 3 — PDF Report Generation

Command:
```bash
cd /home/ced/codex-projects/stock-analysis-pipeline
.venv/bin/python3 benchmarks/bench_baseline_v3.py
```

| Run | Wall (s) | PDF (KB) | Notes |
|---|---|---|---|
| 1 | <0.01 | 2.3 | 986-char markdown → ReportLab PDF |
| 2 | <0.01 | 2.3 | Identical output |
| 3 | <0.01 | 2.3 | Identical output |
| **Avg** | **<0.01** | 2.3 | — |

### S3 Observations

- **Negligible overhead:** PDF rendering from markdown is <10ms for ~1KB markdown input.
- **ReportLab dominates:** `md_to_pdf()` uses ReportLab internally. Not a bottleneck.
- **Larger reports (deep-dive):** 335-347KB PDF rendered as part of S2 above — included in S2 timing.

---

## API Call Summary

| Scenario | yfinance | Finnhub | EDGAR | Seeking Alpha | LLM (DeepSeek) | LLM (Gemini) | URL Validator |
|---|---|---|---|---|---|---|---|
| S1 NVDA cold | 1 | 1 | 1 (fail) | 1 (403) | 1-2 | 0 | 1 |
| S1 NVDA warm | 0 (cache) | 0 (cache) | 1 (fail) | 1 (403) | 1-2 | 0 | 1 |
| S1 AAPL cold | 1 | 1 | 1 (fail) | 1 (403) | 1-2 | 0 | 1 |
| S2 deep-dive | 1 | 0 | 0 | 1 (403) | 5-8 | 0 | 1 |
| S3 PDF render | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

**Key patterns:**
- **yfinance** is the primary bottleneck cold (10-20s), nearly free warm (<0.5s via in-memory cache).
- **EDGAR** consistently fails (proxy URL error) — 10-K/10-Q sections unavailable.
- **Seeking Alpha** consistently blocked (403) — transcript fallback to free sources.
- **DeepSeek** is the sole active LLM provider (Codex CLI missing, Gemini unused as fallback for S1).
- **URL validator** adds ~500ms per run (checks 6 URLs, 3 dead).

---

## End-to-End Timing Estimates

| Path | Cold (s) | Warm (s) | Dominant Phase |
|---|---|---|---|
| Full analysis (NVDA) | 20.6 | 7.7 | yfinance fetch (cold) / scoring (warm) |
| Full analysis (AAPL) | 9.1 | 7.6 | yfinance fetch (cold) |
| Deep-dive (NVDA, with transcript) | 61.3 | 61.3 | LLM generation (99%) |
| PDF render (markdown→PDF) | <0.01 | <0.01 | Negligible |
| **Full pipeline (NVDA, end-to-end)** | **~82s** | **~69s** | S1 analysis + S2 deep-dive |
| **Full pipeline (AAPL, no deep-dive)** | **~9s** | **~8s** | S1 analysis only |

---

## Performance Bottlenecks (Ranked)

| Rank | Bottleneck | Impact | Mitigation |
|---|---|---|---|
| 1 | **Deep-dive LLM calls** (DeepSeek) | 61s (75% of cold e2e) | Parallel section generation already active; consider batch prompts |
| 2 | **yfinance cold fetch** | 10-20s first run | In-memory cache active (1h TTL); pre-warm via cron |
| 3 | **EDGAR proxy error** | 0.5-1s + missing 10-K data | Fix proxy config in edgartools |
| 4 | **Seeking Alpha 403** | 0.5s per attempt (wasted) | Remove from provider list or add API subscription |
| 5 | **URL validator dead links** | ~0.5s per run | Cache dead link status per ticker |

---

## Raw Data Files

- `benchmarks/baseline_v3_20260524_140632.json` — S1 + S3 raw results
- `benchmarks/baseline_s2_20260524_141152.json` — S2 re-run raw results
- `benchmarks/bench_baseline_v3.py` — Reproducible benchmark script
- `benchmarks/_rerun_s2.py` — S2 re-run helper script

---

## Measurement Methodology

1. **S1:** `analyze_ticker_fast(ticker, output_base=<tmp>, language="en", force_refresh=<cold-only>)` — wrapped with `time.perf_counter()`. Captures the full pipeline: yfinance → Finnhub → EDGAR → transcript finder → scoring → report generation. Temporary directories cleaned after each run. `__pycache__` cleared before cold runs.
2. **S2:** Isolated deep-dive pipeline: `get_stock_data()` → `find_transcripts()` → `generate_deep_dive()` → `build_earnings_deep_dive_report()` → `render_earnings_deep_dive_pdf()`. Uses `analyses/` subdirectory for `output_dir` validation. Transcripts sourced from free provider (StockAnalysis.com).
3. **S3:** `md_to_pdf()` with 986-character markdown input → ReportLab PDF. Measures local rendering overhead only.

**NO OPTIMIZATION CHANGES.** This is a measurement of the current `kanban/spec-fonctionnelle-sa` branch as-is.

---

*Generated by Kanban worker `reviewer-qa` (run #245) — Task `t_2b5e0b63`*
