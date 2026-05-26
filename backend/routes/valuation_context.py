"""V2.4 Valuation Context API route.

GET /api/valuation-context/{ticker}

Fetches valuation multiples + growth rates from yfinance, computes
valuation context signals using the T2 pure-function engine, and returns
a structured response. USD-only. No scoring/recommendations.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from backend.models import (
    HistoricalContextInfo,
    ValuationContextResponse,
    ValuationInputData,
)
from backend.services.valuation_context import (
    calculate_peg_ttm,
    calculate_sales_multiple_vs_growth,
    calculate_ev_ebitda_vs_ebitda_growth,
    calculate_price_to_fcf_vs_fcf_growth,
    calculate_fcf_yield_context,
    calculate_valuation_support,
    calculate_valuation_context_summary,
)
from backend.sources_collector import _yf_ticker_safe

logger = logging.getLogger(__name__)

router = APIRouter(tags=["valuation-context"])


@router.get(
    "/api/valuation-context/{ticker}",
    response_model=ValuationContextResponse,
)
async def get_valuation_context(ticker: str):
    """Return valuation context for a ticker — raw multiples + computed signals.

    Data source: yfinance.info (real-time snapshot).
    Context engine: pure functions from backend/services/valuation_context.py.

    Returns 404 if the ticker cannot be found (no price, no market cap).
    Historical context is always unavailable in V2.4 Phase 1.
    """
    now = datetime.now(timezone.utc).isoformat()
    ticker = ticker.upper().strip()

    # ── Fetch yfinance info ──────────────────────────────────────────
    try:
        yf_ticker = _yf_ticker_safe(ticker)
        info = yf_ticker.info if yf_ticker else {}
    except Exception:
        logger.exception("yfinance fetch failed for %s", ticker)
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found or unavailable")

    if not info or not isinstance(info, dict):
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found or unavailable")

    # ── Extract raw data ─────────────────────────────────────────────
    # Valuation multiples
    pe_ttm = _safe_float(info.get("trailingPE"))
    ps_ttm = _safe_float(info.get("priceToSalesTrailing12Months"))
    ev_ebitda = _safe_float(info.get("enterpriseToEbitda"))
    market_cap = _safe_float(info.get("marketCap"))
    free_cashflow = _safe_float(info.get("freeCashflow"))

    # Compute derived multiples
    p_fcf = None
    fcf_yield = None
    if free_cashflow and free_cashflow > 0 and market_cap and market_cap > 0:
        p_fcf = market_cap / free_cashflow
        fcf_yield = free_cashflow / market_cap

    # Growth rates (decimals from yfinance)
    eps_growth = _safe_float(info.get("earningsGrowth"))
    revenue_growth = _safe_float(info.get("revenueGrowth"))
    ebitda_growth = _safe_float(info.get("ebitdaGrowth") or info.get("ebitdaGrowth"))
    fcf_growth = None  # yfinance doesn't provide FCF growth directly

    # ── Determine if ticker is valid ─────────────────────────────────
    price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
    if price is None and market_cap is None:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found or unavailable")

    # ── Source ───────────────────────────────────────────────────────
    source = "yfinance"

    # ── Build valuation input ────────────────────────────────────────
    valuation_input = ValuationInputData(
        pe_ttm=pe_ttm,
        ps_ttm=ps_ttm,
        ev_ebitda=ev_ebitda,
        p_fcf=_round(p_fcf, 1),
        fcf_yield=_round(fcf_yield, 4),
        eps_growth=eps_growth,
        revenue_growth=revenue_growth,
        ebitda_growth=ebitda_growth,
        fcf_growth=fcf_growth,
    )

    # ── Compute context signals (T2 pure functions) ──────────────────
    peg_signal = calculate_peg_ttm(pe_ttm, eps_growth)
    ps_vs_growth = calculate_sales_multiple_vs_growth(ps_ttm, revenue_growth)
    ev_ebitda_vs_growth = calculate_ev_ebitda_vs_ebitda_growth(
        ev_ebitda, ebitda_growth
    )
    p_fcf_vs_growth = calculate_price_to_fcf_vs_fcf_growth(p_fcf, fcf_growth)
    fcf_yield_signal = calculate_fcf_yield_context(fcf_yield)

    valuation_support = calculate_valuation_support(
        peg_signal=peg_signal,
        ps_vs_growth=ps_vs_growth,
        ev_ebitda_vs_growth=ev_ebitda_vs_growth,
        p_fcf_vs_growth=p_fcf_vs_growth,
        fcf_yield_signal=fcf_yield_signal,
    )

    context_summary = calculate_valuation_context_summary(
        peg_signal=peg_signal,
        ps_vs_growth=ps_vs_growth,
        ev_ebitda_vs_growth=ev_ebitda_vs_growth,
        p_fcf_vs_growth=p_fcf_vs_growth,
        fcf_yield_signal=fcf_yield_signal,
    )

    # ── Build context ────────────────────────────────────────────────
    context = {
        "peg_ttm": peg_signal,
        "ps_vs_growth": ps_vs_growth,
        "ev_ebitda_vs_growth": ev_ebitda_vs_growth,
        "p_fcf_vs_growth": p_fcf_vs_growth,
        "fcf_yield_context": fcf_yield_signal,
        "valuation_support": valuation_support,
        "context_summary": context_summary,
    }

    # ── Historical context (V2.4 Phase 1: always unavailable) ────────
    historical_context = HistoricalContextInfo()

    # ── Determine status ─────────────────────────────────────────────
    status = "available" if pe_ttm or ps_ttm or ev_ebitda else "limited"

    return ValuationContextResponse(
        ticker=ticker,
        currency="USD",
        valuation=valuation_input,
        context=context,
        historical_context=historical_context,
        source=source,
        status=status,
        quote_timestamp=now,
    )


# ── Helpers ──────────────────────────────────────────────────────────

def _safe_float(value) -> float | None:
    """Convert value to float, returning None for invalid/nan/inf values."""
    if value is None:
        return None
    try:
        f = float(value)
        if f != f or f == float("inf") or f == float("-inf"):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _round(value: float | None, ndigits: int) -> float | None:
    """Round a float, preserving None."""
    if value is None:
        return None
    return round(value, ndigits)
