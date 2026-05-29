"""Valuation layer — V2.3 market data + valuation multiples.

Fetches data from the existing stock data cache (get_stock_data),
enriches with yfinance for exchange/enterprise_value/shares/debt/cash.
EUR conversion is disabled in V2.3 (fx_status='unavailable').
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.http_client import http
from backend.sources_collector import get_stock_data, _yf_ticker_safe
from backend.models import ValuationV2Response

logger = logging.getLogger(__name__)


def _safe_float_loose(val) -> Optional[float]:
    """Safe float parsing for provider strings (commas, %, N/A tokens)."""
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip()
        if not s or s.lower() in {"none", "n/a", "na", "null", "-"}:
            return None
        s = s.replace(",", "")
        if s.endswith("%"):
            s = s[:-1]
        return _safe_float(s)
    return _safe_float(val)


def _normalize_growth_decimal(val) -> Optional[float]:
    """Normalize growth values to decimal form (0.12 = 12%)."""
    f = _safe_float_loose(val)
    if f is None:
        return None
    # Providers may return 12.3 instead of 0.123.
    if abs(f) > 1:
        return f / 100.0
    return f


def _alpha_vantage_request(function: str, ticker: str) -> Optional[Dict[str, Any]]:
    """Best-effort Alpha Vantage request (returns None on quota/errors)."""
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        resp = http.get(
            "https://www.alphavantage.co/query",
            params={"function": function, "symbol": ticker, "apikey": api_key},
            timeout=12,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not isinstance(data, dict):
            return None
        if data.get("Note") or data.get("Information") or data.get("Error Message"):
            return None
        return data
    except Exception as exc:
        logger.debug("Alpha Vantage %s failed for %s — %s", function, ticker, exc)
        return None


def _backfill_from_alpha_vantage(
    ticker: str,
    pe_current: Optional[float],
    pe_forward: Optional[float],
    peg_ratio: Optional[float],
    eps_growth: Optional[float],
    revenue_growth: Optional[float],
    total_debt: Optional[float],
) -> Dict[str, Optional[float]]:
    """Fill missing valuation fields from Alpha Vantage when available."""
    result = {
        "pe_current": pe_current,
        "pe_forward": pe_forward,
        "peg_ratio": peg_ratio,
        "eps_growth": eps_growth,
        "revenue_growth": revenue_growth,
        "total_debt": total_debt,
    }

    if all(value is not None for value in result.values()):
        return result

    overview = _alpha_vantage_request("OVERVIEW", ticker)
    if overview:
        if result["pe_current"] is None:
            result["pe_current"] = _safe_float_loose(overview.get("PERatio"))
        if result["pe_forward"] is None:
            result["pe_forward"] = _safe_float_loose(overview.get("ForwardPE"))
        if result["peg_ratio"] is None:
            result["peg_ratio"] = _safe_float_loose(overview.get("PEGRatio"))
        if result["eps_growth"] is None:
            # Prefer quarterly earnings growth YOY, fallback earnings growth YOY.
            result["eps_growth"] = _normalize_growth_decimal(
                overview.get("QuarterlyEarningsGrowthYOY")
                or overview.get("EPSGrowthYOY")
            )
        if result["revenue_growth"] is None:
            result["revenue_growth"] = _normalize_growth_decimal(
                overview.get("QuarterlyRevenueGrowthYOY")
            )

    if result["total_debt"] is None:
        bs = _alpha_vantage_request("BALANCE_SHEET", ticker)
        if bs:
            reports = bs.get("quarterlyReports") or bs.get("annualReports") or []
            if isinstance(reports, list) and reports:
                latest = reports[0] if isinstance(reports[0], dict) else {}
                total_debt_candidate = (
                    latest.get("shortLongTermDebtTotal")
                    or latest.get("longTermDebtNoncurrent")
                    or latest.get("longTermDebt")
                    or latest.get("shortTermDebt")
                )
                result["total_debt"] = _safe_float_loose(total_debt_candidate)

    return result


def get_valuation(ticker: str) -> ValuationV2Response:
    """Fetch valuation data for a ticker following V2.3 contract.

    Data sources (in order):
      1. Stock data cache (Finnhub -> Twelve Data -> yfinance chain)
      2. yfinance .info enrichment (exchange, enterprise_value,
         shares_outstanding, total_cash, total_debt)

    EUR conversion is disabled in V2.3 — fx_status='unavailable',
    all EUR fields are null. This avoids the stale static-rate problem.

    Returns a ValuationV2Response — fields will be None where
    data is unavailable (status reflects data freshness).
    """
    now = datetime.now(timezone.utc).isoformat()
    ticker = ticker.upper().strip()

    # -- 1. Base data from existing pipeline --------------------------
    try:
        stock_data = get_stock_data(ticker)
    except Exception:
        logger.exception("get_stock_data failed for %s", ticker)
        return ValuationV2Response(
            ticker=ticker,
            status="unavailable",
            quote_timestamp=now,
        )

    if not stock_data:
        return ValuationV2Response(
            ticker=ticker,
            status="unavailable",
            quote_timestamp=now,
        )

    price = _safe_float(stock_data.get("price"))
    market_cap = _safe_float(stock_data.get("market_cap"))
    currency = stock_data.get("currency", "USD")
    raw_source = stock_data.get("_source", "unknown")

    financials = stock_data.get("financials") if isinstance(stock_data.get("financials"), dict) else {}

    pe_current = _safe_float(stock_data.get("pe_current"))
    pe_forward = _safe_float(stock_data.get("pe_forward"))
    peg_ratio = _safe_float(stock_data.get("peg_ratio"))

    # Keep both explicit EPS growth and legacy expected_growth compatibility.
    eps_growth = _safe_float(stock_data.get("eps_growth"))
    if eps_growth is None:
        eps_growth = _safe_float(stock_data.get("expected_growth"))
    if eps_growth is None:
        eps_growth = _safe_float(financials.get("eps_yoy"))

    revenue_growth = _safe_float(stock_data.get("revenue_growth"))
    if revenue_growth is None:
        revenue_growth = _safe_float(financials.get("revenue_yoy_growth"))
    if revenue_growth is None:
        revenue_growth = _safe_float(financials.get("revenue_annual_growth"))

    # Separate provider (source) from delivery method (served_from)
    KNOWN_PROVIDERS = {"finnhub", "yfinance", "twelvedata", "eodhd", "alpha_vantage"}
    if raw_source in KNOWN_PROVIDERS:
        source = raw_source          # actual financial data provider
        served_from = "live"         # live fetch, not cached
    elif raw_source == "cache":
        source = "unknown"           # original provider lost in cache
        served_from = "cache"        # served from file cache
    else:
        source = "unknown"
        served_from = raw_source if raw_source else "unknown"

    # -- 2. yfinance enrichment (best-effort, non-blocking) -----------
    exchange = None
    reported_ev = None
    shares = None
    cash = None
    total_debt = None

    try:
        yt = _yf_ticker_safe(ticker, timeout=20)
        info = yt.info or {}
        exchange = info.get("exchange") or info.get("exchangeName")
        reported_ev = _safe_float(info.get("enterpriseValue"))
        shares = _safe_float(info.get("sharesOutstanding"))
        cash = _safe_float(
            info.get("totalCash")
            or info.get("cash")
        )
        total_debt = _safe_float(info.get("totalDebt"))

        # Fill missing valuation/growth fields from raw yfinance info.
        if pe_current is None:
            pe_current = _safe_float(info.get("trailingPE"))
        if pe_forward is None:
            pe_forward = _safe_float(info.get("forwardPE"))
        if peg_ratio is None:
            peg_ratio = _safe_float(info.get("pegRatio"))
        if eps_growth is None:
            eps_growth = _safe_float(info.get("earningsGrowth"))
        if revenue_growth is None:
            revenue_growth = _safe_float(info.get("revenueGrowth"))
    except Exception:
        logger.debug("yfinance enrichment skipped for %s", ticker)

    # -- 2.5 Alternative provider backfill (best-effort) ----------------
    before_backfill = {
        "pe_current": pe_current,
        "pe_forward": pe_forward,
        "peg_ratio": peg_ratio,
        "eps_growth": eps_growth,
        "revenue_growth": revenue_growth,
        "total_debt": total_debt,
    }
    backfill = _backfill_from_alpha_vantage(
        ticker=ticker,
        pe_current=pe_current,
        pe_forward=pe_forward,
        peg_ratio=peg_ratio,
        eps_growth=eps_growth,
        revenue_growth=revenue_growth,
        total_debt=total_debt,
    )
    pe_current = backfill["pe_current"]
    pe_forward = backfill["pe_forward"]
    peg_ratio = backfill["peg_ratio"]
    eps_growth = backfill["eps_growth"]
    revenue_growth = backfill["revenue_growth"]
    total_debt = backfill["total_debt"]

    if source == "unknown" and any(
        before_backfill[key] is None and backfill[key] is not None
        for key in backfill
    ):
        source = "alpha_vantage"
        served_from = "fallback"

    # -- 3. Enterprise value (reported or computed) -------------------
    computed_ev = _compute_ev(market_cap, total_debt, cash)

    if reported_ev is not None:
        enterprise_value = reported_ev
        ev_source = "reported"
    elif computed_ev is not None:
        enterprise_value = computed_ev
        ev_source = "computed"
    else:
        enterprise_value = None
        ev_source = "unavailable"

    # -- 4. Status determination --------------------------------------
    # Use the cache state from market_data layer when possible
    cache_state = stock_data.get("cache_state")
    if price is None and market_cap is None:
        status = "unavailable"
    elif cache_state in ("fresh", "cached", "stale"):
        status = cache_state
    elif source in ("finnhub", "yfinance", "twelvedata", "eodhd", "alpha_vantage"):
        status = "fresh"  # live fetch succeeded
    elif served_from == "cache":
        status = "cached"
    else:
        status = "unavailable"

    # -- 5. Build response (EUR disabled) -----------------------------
    return ValuationV2Response(
        ticker=ticker,
        exchange=exchange,
        quote_currency=currency,
        display_currency="EUR",
        price=price,
        price_eur=None,           # EUR disabled in V2.3
        market_cap=market_cap,
        market_cap_eur=None,      # EUR disabled in V2.3
        enterprise_value=enterprise_value,
        enterprise_value_eur=None,  # EUR disabled in V2.3
        ev_source=ev_source,
        shares_outstanding=shares,
        cash_and_equivalents=cash,
        total_debt=total_debt,
        pe_current=pe_current,
        pe_forward=pe_forward,
        peg_ratio=peg_ratio,
        eps_growth=eps_growth,
        revenue_growth=revenue_growth,
        quote_timestamp=now,
        fundamentals_timestamp=now,
        fx_rate_eur=None,         # EUR disabled in V2.3
        fx_timestamp=None,
        fx_status="unavailable",  # V2.3: no live FX source yet
        source=source,
        served_from=served_from,
        status=status,
    )


def _safe_float(val) -> Optional[float]:
    """Convert to float, returning None for NaN, inf, or None."""
    if val is None:
        return None
    import math
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _compute_ev(
    market_cap: Optional[float],
    total_debt: Optional[float],
    cash: Optional[float],
) -> Optional[float]:
    """Compute Enterprise Value = market_cap + total_debt - cash."""
    if market_cap is None:
        return None
    debt = total_debt if total_debt is not None else 0.0
    cash_val = cash if cash is not None else 0.0
    return market_cap + debt - cash_val


# ═════════════════════════════════════════════════════════════
#  V2.3 Pure Calculation Functions
#  (zero side effects, no network, never invents data)
# ═════════════════════════════════════════════════════════════


def _safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    """Return numerator/denominator, or None on missing/invalid input."""
    if numerator is None or denominator is None:
        return None
    if denominator <= 0:
        return None
    return numerator / denominator


# -- Price-Based Ratios --


def calculate_pe_ttm(price: Optional[float], eps_ttm: Optional[float]) -> Optional[float]:
    """Price to trailing-twelve-months earnings."""
    return _safe_div(price, eps_ttm)


def calculate_ps_ttm(price: Optional[float], revenue_per_share: Optional[float]) -> Optional[float]:
    """Price to trailing-twelve-months sales (revenue per share)."""
    return _safe_div(price, revenue_per_share)


def calculate_price_to_fcf(price: Optional[float], fcf_per_share: Optional[float]) -> Optional[float]:
    """Price to free-cash-flow per share."""
    return _safe_div(price, fcf_per_share)


def calculate_fcf_yield(fcf_per_share: Optional[float], price: Optional[float]) -> Optional[float]:
    """Free-cash-flow yield (FCF / price). Returns decimal (0.05 = 5%)."""
    return _safe_div(fcf_per_share, price)


# -- Enterprise-Value-Based Ratios --


def calculate_enterprise_value(
    market_cap: Optional[float],
    total_debt: Optional[float] = None,
    cash: Optional[float] = None,
) -> Optional[float]:
    """Enterprise Value = market_cap + total_debt - cash.

    Debt and cash default to zero when missing (best-effort).
    Returns None only when market_cap is None.
    """
    if market_cap is None:
        return None
    debt = total_debt if total_debt is not None else 0.0
    cash_val = cash if cash is not None else 0.0
    return market_cap + debt - cash_val


def calculate_ev_sales(enterprise_value: Optional[float], revenue: Optional[float]) -> Optional[float]:
    """Enterprise Value / annual (or TTM) revenue."""
    return _safe_div(enterprise_value, revenue)


def calculate_ev_ebitda(enterprise_value: Optional[float], ebitda: Optional[float]) -> Optional[float]:
    """Enterprise Value / EBITDA."""
    return _safe_div(enterprise_value, ebitda)


# -- Batch Convenience --


def calculate_all_ratios(
    price: Optional[float],
    eps_ttm: Optional[float] = None,
    revenue_per_share: Optional[float] = None,
    fcf_per_share: Optional[float] = None,
    market_cap: Optional[float] = None,
    total_debt: Optional[float] = None,
    cash: Optional[float] = None,
    revenue: Optional[float] = None,
    ebitda: Optional[float] = None,
) -> dict:
    """Calculate all valuation ratios in one call.

    Returns a dict with keys matching the individual function names.
    Missing/invalid inputs → None for the corresponding ratio.
    """
    ev = calculate_enterprise_value(market_cap, total_debt, cash)
    return {
        "pe_ttm": calculate_pe_ttm(price, eps_ttm),
        "ps_ttm": calculate_ps_ttm(price, revenue_per_share),
        "price_to_fcf": calculate_price_to_fcf(price, fcf_per_share),
        "fcf_yield": calculate_fcf_yield(fcf_per_share, price),
        "enterprise_value": ev,
        "ev_sales": calculate_ev_sales(ev, revenue),
        "ev_ebitda": calculate_ev_ebitda(ev, ebitda),
    }
