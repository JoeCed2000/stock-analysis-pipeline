# Input Validation — Live Check Pattern

## Problem
Format validation (regex) gives false confidence. A ticker like "TITYJ" passes `^[A-Z]{1,5}$`
but doesn't exist on any exchange. The green checkmark ✓ appears, user clicks "Analyze",
and only then discovers the ticker is invalid — wasted time.

## Solution: Format + Live Check
1. Format validation first (instant, no I/O)
2. If format OK → live existence check via market data API
3. If live check fails → mark as `invalid` with error message

## Implementation (Python + yfinance)
```python
import yfinance as yf

def _ticker_exists(ticker: str) -> bool:
    """Check if ticker exists on Yahoo Finance."""
    try:
        info = yf.Ticker(ticker).info
        return bool(info.get('symbol') and (info.get('shortName') or info.get('longName')))
    except Exception:
        return False

def _parse_tickers_from_text(text: str) -> List[dict]:
    for token in tokens:
        if TICKER_RE.match(token):
            exists = _ticker_exists(token)
            items.append({
                "value": token, "type": "TICKER",
                "normalized": token,
                "status": "valid" if exists else "invalid",
                "error": None if exists else "Ticker not found on any exchange — verify the symbol",
            })
```

## Providers
| Provider | Endpoint | Latency |
|----------|----------|---------|
| Yahoo Finance (yfinance) | `Ticker.info` | ~1-2s |
| Stooq | `https://stooq.com/q/l/?s={symbol}.us&f=sd2t2ohlcvn&e=csv` | ~0.5s |

## Pitfalls
- **Lazy import**: don't import yfinance at module level on slow filesystems (NTFS)
- **Fallback**: if yfinance unavailable (ImportError), don't block — return True
- **Rate limiting**: yfinance has no official rate limit but can be throttled
- **European tickers**: yfinance works for .PA, .DE, .AS suffixes; Stooq for .fr, .de, .uk

## Concrete case (stock-analysis-pipeline, 2026-05-04)
- User typed "TITYJ" → regex passed → green checkmark ✓ appeared
- Analysis ran → yfinance returned empty dict → error surfaced only at analysis time
- Fix: added `_ticker_exists()` call in `_parse_tickers_from_text()`
- Result: TITYJ → ✕ invalid immediately, NVDA → ✓ valid as expected
