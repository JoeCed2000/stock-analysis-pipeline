"""Market data layer — V2.3.

Primary entry points:
  get_market_snapshot(ticker) → MarketSnapshot
  normalize_market_data(raw: dict) → MarketSnapshot

Rules:
  - Cache-first: check market_cache before hitting the network
  - 429 → stale: serve cached data on provider rate limits
  - Never invent data: missing fields stay None
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend import market_cache
from backend.models import MarketSnapshot

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────


def get_market_snapshot(ticker: str) -> MarketSnapshot:
    """Return a MarketSnapshot for *ticker*, using cache when possible.

    Flow:
      1. Cache hit + fresh (age < 5 min)  → return immediately
      2. Cache hit + cached (5-30 min)     → return cached, no fetch
      3. Cache hit + stale (> 30 min)      → return cached, background-fetch
      4. Cache miss                         → fetch, cache, return

    On provider error (timeout, 429, connection):
      - Serve stale cache if available
      - Otherwise return empty snapshot with cache_state='unavailable'
    """
    ticker = ticker.upper().strip()

    cached_data, state = market_cache.get_with_state(ticker)

    # ── Fresh: return immediately ──
    if state == "fresh" and cached_data:
        logger.debug("market_data: %s — fresh cache hit", ticker)
        return _data_to_snapshot(ticker, cached_data, "fresh")

    # ── Cached: return cached, no re-fetch ──
    if state == "cached" and cached_data:
        logger.debug("market_data: %s — cached (age < 30 min)", ticker)
        return _data_to_snapshot(ticker, cached_data, "cached")

    # ── Stale or Unavailable: fetch fresh data ──
    raw = _fetch_from_yfinance(ticker)

    if raw is not None:
        # Successful fetch — cache and return
        market_cache.set(ticker, raw)
        return _data_to_snapshot(ticker, raw, "fresh")

    # Fetch failed
    if state == "stale" and cached_data:
        # 429 / network error → serve stale
        logger.warning("market_data: %s — fetch failed, serving stale cache", ticker)
        return _data_to_snapshot(ticker, cached_data, "stale")

    # No cache, no fetch → unavailable
    logger.warning("market_data: %s — no data available", ticker)
    return _empty_snapshot(ticker)


def normalize_market_data(raw: Dict[str, Any]) -> MarketSnapshot:
    """Convert a raw provider dict into a standardized MarketSnapshot.

    Accepts yfinance .info dicts and simple key-value maps.
    Unknown keys are ignored; missing keys become None.

    Args:
        raw:  dict from yfinance Ticker.info, or compatible structure.

    Returns:
        Populated MarketSnapshot (caller should set ticker + retrieved_at).
    """
    return _data_to_snapshot(
        ticker=raw.get("symbol", raw.get("ticker", "???")) or "???",
        raw=raw,
        cache_state="unavailable",  # caller overrides
    )


# ─────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────


def _fetch_from_yfinance(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch market data from Yahoo Finance via yfinance.

    Returns a plain dict on success, None on any failure.
    Catches all exceptions — the caller decides fallback strategy.
    """
    try:
        # Lazy import: module-level yfinance (pulls pandas) added ~4.7s to
        # backend.main cold start via the peer_benchmark route. Every other
        # module already defers this import to call time.
        import yfinance as yf

        yt = yf.Ticker(ticker)
        info = yt.info or {}

        # Fast price data
        try:
            fast = yt.fast_info
            price = fast.get("lastPrice") or fast.get("regularMarketPrice")
            previous_close = fast.get("previousClose") or fast.get("regularMarketPreviousClose")
        except Exception:
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            previous_close = info.get("previousClose") or info.get("regularMarketPreviousClose")

        # Day change
        day_change = None
        day_change_pct = None
        if price is not None and previous_close is not None and previous_close > 0:
            day_change = price - previous_close
            day_change_pct = day_change / previous_close

        raw: Dict[str, Any] = {
            "symbol": ticker,
            "current_price": price,
            "previous_close": previous_close,
            "day_change": round(day_change, 4) if day_change is not None else None,
            "day_change_pct": round(day_change_pct, 6) if day_change_pct is not None else None,
            "volume": info.get("volume"),
            "avg_volume": info.get("averageVolume") or info.get("averageDailyVolume10Day"),
            "market_cap": info.get("marketCap"),
            "beta": info.get("beta"),
            "high_52w": info.get("fiftyTwoWeekHigh"),
            "low_52w": info.get("fiftyTwoWeekLow"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "pe_ttm": info.get("trailingPE"),
            "ps_ttm": info.get("priceToSalesTrailing12Months"),
            "pb_ratio": info.get("priceToBook"),
            "dividend_yield": info.get("dividendYield"),
        }

        logger.info("market_data: fetched %s — price=%s", ticker, price)
        return raw

    except Exception as exc:
        logger.warning("market_data: yfinance fetch failed for %s — %s", ticker, exc)
        return None


def _data_to_snapshot(ticker: str, raw: Dict[str, Any], cache_state: str) -> MarketSnapshot:
    """Build a MarketSnapshot from a raw data dict + cache state.

    Accepts both snake_case (from _fetch_from_yfinance normalization)
    and camelCase (from yfinance .info dicts or test fixtures).
    """
    def _g(*keys: str) -> Any:
        """Get first non-None value from raw dict across multiple key names."""
        for k in keys:
            v = raw.get(k)
            if v is not None:
                return v
        return None

    return MarketSnapshot(
        ticker=ticker or _g("symbol", "ticker") or "???",
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        current_price=_float_or_none(_g("current_price", "currentPrice", "regularMarketPrice")),
        previous_close=_float_or_none(_g("previous_close", "previousClose", "regularMarketPreviousClose")),
        day_change=_float_or_none(_g("day_change")),
        day_change_pct=_float_or_none(_g("day_change_pct")),
        volume=_int_or_none(_g("volume", "regularMarketVolume")),
        avg_volume=_int_or_none(_g("avg_volume", "averageVolume", "averageDailyVolume10Day")),
        market_cap=_float_or_none(_g("market_cap", "marketCap")),
        beta=_float_or_none(_g("beta")),
        high_52w=_float_or_none(_g("high_52w", "fiftyTwoWeekHigh")),
        low_52w=_float_or_none(_g("low_52w", "fiftyTwoWeekLow")),
        shares_outstanding=_float_or_none(_g("shares_outstanding", "sharesOutstanding")),
        pe_ttm=_float_or_none(_g("pe_ttm", "trailingPE")),
        ps_ttm=_float_or_none(_g("ps_ttm", "priceToSalesTrailing12Months")),
        pb_ratio=_float_or_none(_g("pb_ratio", "priceToBook")),
        dividend_yield=_float_or_none(_g("dividend_yield", "dividendYield")),
        cache_state=cache_state,
    )


def _empty_snapshot(ticker: str) -> MarketSnapshot:
    """Return a MarketSnapshot with all data fields None."""
    return MarketSnapshot(
        ticker=ticker,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        cache_state="unavailable",
    )


def _float_or_none(value: Any) -> Optional[float]:
    """Coerce value to float, or None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> Optional[int]:
    """Coerce value to int, or None."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
