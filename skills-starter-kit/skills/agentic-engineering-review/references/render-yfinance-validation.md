# Render + Yahoo Finance — Ticker Validation Rate-Limiting

## Context

Adding `yfinance`-based ticker existence validation to a FastAPI backend deployed on Render's free tier. The goal: reject fake tickers (TITYJ) while accepting real ones (NVDA).

## Pitfall

**Yahoo Finance aggressively rate-limits or blocks requests from Render's shared IP addresses.** `yf.Ticker(symbol).info` returns a sparse dict (2-3 meaningful fields) even for real tickers like NVDA. A validation check that requires rich fields (e.g., `shortName` or `longName`) will produce false negatives — valid tickers are rejected.

## The Heuristic

```python
def _ticker_exists(ticker: str) -> bool:
    yf = _get_yf()
    if not yf:
        return True  # Can't validate — don't block
    try:
        info = yf.Ticker(ticker).info
        meaningful = sum(1 for v in info.values() if v is not None)
        if meaningful <= 3:
            # Too sparse — likely rate-limited. Allow.
            return True
        # Has rich data — check for company name
        return bool(info.get('shortName') or info.get('longName'))
    except Exception:
        return True  # Can't validate — don't block
```

**Tradeoff**: On Render's shared IP, fake tickers like TITYJ will pass validation because yfinance returns sparse data for ALL tickers (including fakes). The only reliable validation is format (1-5 letters). On local dev or a dedicated IP, the distinction works correctly.

## Testing Strategy

1. Test locally first: `curl -X POST localhost:8780/api/batch/upload -F "file=@-;filename=test.txt" <<< "NVDA"`
2. Test on Render: same command against the Render URL
3. If Render returns `invalid` for known-good tickers → yfinance is rate-limited → the heuristic needs adjustment (lower the `meaningful` threshold or add additional checks)

## Alternatives Considered

- **Finnhub symbol lookup**: requires API key, has its own rate limits
- **Alpha Vantage**: same issue
- **Known ticker list**: maintenance burden, misses new tickers
- **Deferred validation**: validate during analysis (when yfinance is called anyway) rather than during ticker input

The current approach (yfinance with rate-limit fallback) is the most pragmatic for a free-tier deployment.
