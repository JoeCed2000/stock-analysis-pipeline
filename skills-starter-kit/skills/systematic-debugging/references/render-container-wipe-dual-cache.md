# Render Container Wipe — Dual Cache + Immediate Enrichment Pattern

**Context**: stock-analysis-pipeline, 2026-05-04. Render free tier, Finnhub API for ratios, yfinance blocked on shared IP, cron on home PC pushes yfinance data.

## The Problem (in sequence)

1. `GET /api/analyze` → `get_stock_data()` called → Finnhub succeeds (ratios) → `get_yahoo_data()` blocked on Render → result has `pe_current: None, revenue_annual: None` → cached in `NVDA.json`
2. Cron pushes yfinance data → `POST /api/cache/financials/NVDA` → saved to `NVDA_yf.json`
3. Render container restarts (cold start) → **both cache files wiped**
4. Next analysis → cache miss → Finnhub only → everything None again → loop forever

## The Fix (3 layers)

### Layer 1: Separate caches
- `{TICKER}_yf.json` — raw yfinance data (from cron)
- `{TICKER}.json` — Finnhub + yfinance merged (from get_stock_data)

### Layer 2: Immediate enrichment in upload endpoint
When yfinance data arrives via `/api/cache/financials/{ticker}`:
1. Write `_yf.json` (cold-start fallback)
2. If `{TICKER}.json` exists → read it → merge yfinance values where None → write back

```python
if main_path.exists():
    main_data = json.load(open(main_path))
    yf_fin = body.get("financials", {})
    main_fin = main_data.get("financials", {})
    for key in ["revenue_annual", "net_income", "free_cash_flow"]:
        if main_fin.get(key) is None and yf_fin.get(key) is not None:
            main_fin[key] = yf_fin[key]
    for key in ["pe_current", "pe_forward"]:
        if main_data.get(key) is None and body.get(key) is not None:
            main_data[key] = body[key]
    json.dump(main_data, open(main_path, "w"))
```

### Layer 3: Enrichment on cache hit
Even with existing cache, check `_yf.json` for newer data:

```python
cached = _cache_get(ticker)
if cached is not None:
    yf_cached = _cache_get_yf(ticker)
    if yf_cached:
        # merge yf_cached into cached where cached has None
        _cache_set(ticker, cached)  # persist enrichment
    return cached
```

## Why This Works

| Scenario | What happens |
|----------|-------------|
| Container fresh, yf cache exists | `get_yahoo_data()` fails → `_cache_get_yf()` fallback → data merged |
| Container fresh, no cache | Finnhub only → cron pushes yf → immediate enrichment of main cache |
| Cache hit, yf cache newer | Enrichment in cache hit path → data merged without re-fetching Finnhub |
| Container restart, both caches wiped | Analysis recreates Finnhub cache → cron repushes → immediate enrichment |

## Key Pitfalls

1. **Never defer enrichment** — if you push data to a file and wait for "the next read" to merge, the container may restart and the file is gone.
2. **Dual cache is redundant but necessary** — `_yf.json` alone isn't enough (it's yfinance-only, missing Finnhub sector/ratios). `{TICKER}.json` alone isn't enough (it's enriched once, then stale). Both together cover all states.
3. **`dict.get()` detachment** — `yf_fin_live = yf_data.get("financials", {})` creates a detached dict if the key is absent. Always reassign: `yf_data["financials"] = yf_fin_live`.
