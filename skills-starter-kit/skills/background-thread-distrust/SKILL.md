---
name: background-thread-distrust
description: "On Render, Vercel, and serverless platforms, never rely on background daemon threads for essential work. All critical file generation must be synchronous. Background threads are cache/optimization only."
version: 1.0.0
metadata:
  hermes:
    tags: [render, serverless, background, threading, reliability]
    priority: critical
---

# Background Thread Distrust

## The Rule

**On serverless/ephemeral platforms (Render free tier, Vercel, Lambda), daemon threads are UNRELIABLE. Never depend on them for essential work.**

## Why

1. **Render kills daemon threads when the server idles** — if no request comes in, the thread dies
2. **No log visibility** — thread crashes are silent, no stdout/stderr captured
3. **API rate-limits from shared IPs** — Finnhub 429, SEC EDGAR blocked entirely from Render's IP range
4. **Thread completes AFTER the API response** — the user sees "done" but files aren't written yet
5. **`daemon=True`** — killed without warning when the main process exits

## Pattern: Synchronous Generation

```python
# ❌ WRONG — essential work in background thread
def analyze_ticker_fast(ticker):
    result = do_analysis(ticker)
    thread = Thread(target=generate_files, args=(result,))
    thread.start()  # May never complete on Render
    return result   # User sees "done" but files aren't written

# ✅ CORRECT — all essential work is synchronous
def analyze_ticker_fast(ticker):
    result = do_analysis(ticker)
    generate_report(result)       # Synchronous
    generate_excel(result)        # Synchronous
    generate_company_profile(result)  # Synchronous
    # Optional: spawn thread for nice-to-have files ONLY
    Thread(target=download_10k, args=(ticker,)).start()
    return result  # All critical files already on disk
```

## What CAN Be Background

- 10-K download from SEC EDGAR (lapced cron handles this)
- Cache warming
- Non-critical logging/metrics
- Image optimization

## What MUST Be Synchronous

- Report PDF/Excel generation
- Company profile
- Market context
- Any file the user needs in the ZIP download
- Any file checked by `get_dossier_status()` for `ready=true`

## Checklist

Before deploying to Render:
- [ ] All files needed for `ready=true` are written synchronously
- [ ] Background threads only handle optional/cache content
- [ ] `daemon=True` threads are acceptable to lose (they don't hold critical work)
- [ ] Alternative delivery method exists for rate-limited APIs (lapced cron)
