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

_MISSING_REASON_PROVIDER_MISSING = "provider_missing"
_MISSING_REASON_NOT_REPORTED_YET = "not_reported_yet"
_MISSING_REASON_FALLBACK_EXHAUSTED = "fallback_exhausted"


def _ticker_variants(ticker: str) -> list[str]:
    """Return normalized ticker variants (dot/hyphen aliases) in priority order."""
    base = ticker.upper().strip()
    variants: list[str] = []
    for candidate in (base, base.replace(".", "-"), base.replace("-", ".")):
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


def _safe_datetime_key(raw_key: Any) -> Optional[datetime]:
    """Best-effort conversion of quarterly index keys to datetime."""
    if isinstance(raw_key, datetime):
        return raw_key

    if hasattr(raw_key, "to_pydatetime"):
        try:
            return raw_key.to_pydatetime()
        except Exception:
            pass

    if hasattr(raw_key, "year") and hasattr(raw_key, "month") and hasattr(raw_key, "day"):
        try:
            return datetime(int(raw_key.year), int(raw_key.month), int(raw_key.day))
        except Exception:
            pass

    raw = str(raw_key)
    if not raw:
        return None

    for candidate in (raw, raw[:10]):
        try:
            return datetime.fromisoformat(candidate)
        except Exception:
            continue

    return None


def _compute_eps_growth_from_quarterly_eps(quarterly_income_stmt: Any) -> Optional[float]:
    """Compute YoY EPS growth from quarterly diluted/basic EPS when available.

    Returns decimal form (0.12 = +12%).
    """
    if quarterly_income_stmt is None:
        return None

    try:
        index = getattr(quarterly_income_stmt, "index", None)
        if index is None:
            return None

        eps_row = None
        for candidate_row in ("Diluted EPS", "Basic EPS"):
            if candidate_row in index:
                eps_row = candidate_row
                break

        if eps_row is None:
            return None

        eps_series = quarterly_income_stmt.loc[eps_row]
        entries: list[tuple[datetime, float]] = []
        for raw_key, raw_value in eps_series.items():
            value = _safe_float(raw_value)
            dt = _safe_datetime_key(raw_key)
            if value is None or dt is None:
                continue
            entries.append((dt, value))

        if not entries:
            return None

        entries.sort(key=lambda item: item[0], reverse=True)
        latest_dt, latest_eps = entries[0]

        prev_eps = None
        for dt, eps_val in entries[1:]:
            if dt.year == latest_dt.year - 1 and dt.month == latest_dt.month:
                prev_eps = eps_val
                break

        if prev_eps is None or prev_eps == 0:
            return None

        return (latest_eps - prev_eps) / abs(prev_eps)
    except Exception:
        return None


def _fallback_provider_availability() -> Dict[str, bool]:
    """Return whether each fallback provider is configured via API key."""
    return {
        "alpha_vantage": bool(os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()),
        "fmp": bool(os.getenv("FMP_API_KEY", "").strip()),
        "eodhd": bool(os.getenv("EODHD_API_KEY", "").strip()),
    }


def _has_any_numeric(data: Dict[str, Any], keys: tuple[str, ...]) -> bool:
    """True if any key resolves to a numeric value."""
    for key in keys:
        if _safe_float_loose(data.get(key)) is not None:
            return True
    return False


def _classify_missing_field_reasons(
    field_values: Dict[str, Optional[float]],
    financials: Dict[str, Any],
    provider_availability: Dict[str, bool],
) -> Dict[str, str]:
    """Classify missing valuation fields with explicit, coded reasons.

    Codes:
      - provider_missing: no fallback providers configured
      - not_reported_yet: growth metric has no historical signal yet
      - fallback_exhausted: providers configured but none returned usable data
    """
    reasons: Dict[str, str] = {}
    fallback_enabled = any(provider_availability.values())

    eps_signals = (
        "eps_yoy",
        "eps_growth",
        "earnings_growth",
        "earningsGrowth",
    )
    revenue_signals = (
        "revenue_yoy_growth",
        "revenue_annual_growth",
        "revenue_growth",
        "revenueGrowth",
    )

    for field, value in field_values.items():
        if value is not None:
            continue

        if field == "eps_growth" and not _has_any_numeric(financials, eps_signals):
            reasons[field] = _MISSING_REASON_NOT_REPORTED_YET
            continue

        if field == "revenue_growth" and not _has_any_numeric(financials, revenue_signals):
            reasons[field] = _MISSING_REASON_NOT_REPORTED_YET
            continue

        reasons[field] = (
            _MISSING_REASON_FALLBACK_EXHAUSTED
            if fallback_enabled
            else _MISSING_REASON_PROVIDER_MISSING
        )

    return reasons


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


def _first_dict(payload: Any) -> Dict[str, Any]:
    """Return first dict from list payloads; empty dict otherwise."""
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    return {}


def _fmp_request(endpoint: str, ticker: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    """Best-effort FMP request (returns None on key/quota/errors)."""
    api_key = os.getenv("FMP_API_KEY", "").strip()
    if not api_key:
        return None

    query = dict(params or {})
    query["apikey"] = api_key
    url = f"https://financialmodelingprep.com/api/v3/{endpoint}/{ticker}"

    try:
        resp = http.get(url, params=query, timeout=12)
        if resp.status_code != 200:
            return None
        data = resp.json()

        if isinstance(data, dict):
            msg = str(
                data.get("Error Message")
                or data.get("error")
                or data.get("message")
                or ""
            ).lower()
            if msg and any(
                token in msg
                for token in ("invalid", "forbidden", "limit", "subscribe", "denied", "not available")
            ):
                return None
        elif isinstance(data, list) and data and isinstance(data[0], str):
            if "error" in data[0].lower():
                return None

        return data
    except Exception as exc:
        logger.debug("FMP %s failed for %s — %s", endpoint, ticker, exc)
        return None


def _eodhd_fundamentals_request(ticker: str) -> Optional[Dict[str, Any]]:
    """Best-effort EODHD fundamentals request (returns None on key/quota/errors)."""
    api_key = os.getenv("EODHD_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        resp = http.get(
            f"https://eodhd.com/api/fundamentals/{ticker}",
            params={"api_token": api_key, "fmt": "json"},
            timeout=12,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not isinstance(data, dict):
            return None
        if data.get("error") or data.get("message"):
            return None
        return data
    except Exception as exc:
        logger.debug("EODHD fundamentals failed for %s — %s", ticker, exc)
        return None


def _backfill_from_fmp(
    ticker: str,
    current: Dict[str, Optional[float]],
) -> Dict[str, Optional[float]]:
    """Fill remaining missing valuation fields from FMP when available."""
    result = dict(current)
    if all(value is not None for value in result.values()):
        return result

    ratios = _first_dict(_fmp_request("ratios-ttm", ticker))
    if ratios:
        if result["pe_current"] is None:
            result["pe_current"] = _safe_float_loose(
                ratios.get("peRatioTTM")
                or ratios.get("priceEarningsRatioTTM")
                or ratios.get("priceEarningsRatio")
                or ratios.get("peRatio")
            )
        if result["pe_forward"] is None:
            result["pe_forward"] = _safe_float_loose(
                ratios.get("forwardPERatio")
                or ratios.get("forwardPE")
            )
        if result["peg_ratio"] is None:
            result["peg_ratio"] = _safe_float_loose(
                ratios.get("pegRatioTTM")
                or ratios.get("pegRatio")
                or ratios.get("priceEarningsToGrowthRatio")
            )

    growth = _first_dict(_fmp_request("income-statement-growth", ticker, params={"limit": 1}))
    if growth:
        if result["eps_growth"] is None:
            result["eps_growth"] = _normalize_growth_decimal(
                growth.get("growthEPS")
                or growth.get("epsGrowth")
                or growth.get("growthEps")
            )
        if result["revenue_growth"] is None:
            result["revenue_growth"] = _normalize_growth_decimal(
                growth.get("growthRevenue")
                or growth.get("revenueGrowth")
            )

    if result["total_debt"] is None:
        balance = _first_dict(_fmp_request("balance-sheet-statement", ticker, params={"limit": 1}))
        if balance:
            result["total_debt"] = _safe_float_loose(
                balance.get("totalDebt")
                or balance.get("shortTermDebt")
                or balance.get("longTermDebt")
                or balance.get("totalLiabilities")
            )

    return result


def _backfill_from_eodhd(
    ticker: str,
    current: Dict[str, Optional[float]],
) -> Dict[str, Optional[float]]:
    """Fill remaining missing valuation fields from EODHD fundamentals when available."""
    result = dict(current)
    if all(value is not None for value in result.values()):
        return result

    payload = _eodhd_fundamentals_request(ticker)
    if not payload:
        return result

    highlights = _first_dict(payload.get("Highlights"))
    valuation = _first_dict(payload.get("Valuation"))
    financials = _first_dict(payload.get("Financials"))

    if result["pe_current"] is None:
        result["pe_current"] = _safe_float_loose(
            highlights.get("PERatio")
            or valuation.get("TrailingPE")
            or valuation.get("PriceEarningsTTM")
        )
    if result["pe_forward"] is None:
        result["pe_forward"] = _safe_float_loose(
            highlights.get("ForwardPE")
            or valuation.get("ForwardPE")
        )
    if result["peg_ratio"] is None:
        result["peg_ratio"] = _safe_float_loose(
            highlights.get("PEGRatio")
            or valuation.get("PEGRatio")
        )
    if result["eps_growth"] is None:
        result["eps_growth"] = _normalize_growth_decimal(
            highlights.get("QuarterlyEarningsGrowthYOY")
            or highlights.get("EarningsGrowthYOY")
        )
    if result["revenue_growth"] is None:
        result["revenue_growth"] = _normalize_growth_decimal(
            highlights.get("QuarterlyRevenueGrowthYOY")
            or highlights.get("RevenueGrowthYOY")
        )

    if result["total_debt"] is None:
        bs = _first_dict(financials.get("Balance_Sheet"))
        quarterly = bs.get("quarterly") if isinstance(bs, dict) else None
        annual = bs.get("yearly") if isinstance(bs, dict) else None

        latest = {}
        if isinstance(quarterly, dict) and quarterly:
            latest_key = sorted(quarterly.keys(), reverse=True)[0]
            latest = _first_dict(quarterly.get(latest_key))
        elif isinstance(annual, dict) and annual:
            latest_key = sorted(annual.keys(), reverse=True)[0]
            latest = _first_dict(annual.get(latest_key))

        if latest:
            result["total_debt"] = _safe_float_loose(
                latest.get("shortLongTermDebtTotal")
                or latest.get("LongTermDebt")
                or latest.get("ShortTermDebt")
                or latest.get("TotalDebt")
            )

    return result


def _backfill_from_external_providers(
    ticker: str,
    pe_current: Optional[float],
    pe_forward: Optional[float],
    peg_ratio: Optional[float],
    eps_growth: Optional[float],
    revenue_growth: Optional[float],
    total_debt: Optional[float],
) -> tuple[Dict[str, Optional[float]], Optional[str]]:
    """Apply fallback providers in order and return first provider that filled data.

    The function also retries provider lookups on ticker aliases (dot/hyphen)
    to avoid avoidable gaps such as BRK.B vs BRK-B.
    """
    result = {
        "pe_current": pe_current,
        "pe_forward": pe_forward,
        "peg_ratio": peg_ratio,
        "eps_growth": eps_growth,
        "revenue_growth": revenue_growth,
        "total_debt": total_debt,
    }

    fallback_chain = [
        ("alpha_vantage", _backfill_from_alpha_vantage),
        ("fmp", _backfill_from_fmp),
        ("eodhd", _backfill_from_eodhd),
    ]

    ticker_candidates = _ticker_variants(ticker)
    provider_used: Optional[str] = None

    for provider_name, provider_fn in fallback_chain:
        if all(value is not None for value in result.values()):
            break

        for candidate in ticker_candidates:
            if all(value is not None for value in result.values()):
                break

            before = dict(result)
            if provider_name == "alpha_vantage":
                result = provider_fn(
                    ticker=candidate,
                    pe_current=result["pe_current"],
                    pe_forward=result["pe_forward"],
                    peg_ratio=result["peg_ratio"],
                    eps_growth=result["eps_growth"],
                    revenue_growth=result["revenue_growth"],
                    total_debt=result["total_debt"],
                )
            else:
                result = provider_fn(ticker=candidate, current=result)

            if provider_used is None and any(before[k] is None and result[k] is not None for k in result):
                provider_used = provider_name

    return result, provider_used


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
    KNOWN_PROVIDERS = {"finnhub", "yfinance", "twelvedata", "eodhd", "alpha_vantage", "fmp"}
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

    ticker_candidates = _ticker_variants(ticker)

    for candidate in ticker_candidates:
        try:
            yt = _yf_ticker_safe(candidate, timeout=20)
            info = yt.info or {}

            if exchange is None:
                exchange = info.get("exchange") or info.get("exchangeName")
            if reported_ev is None:
                reported_ev = _safe_float(info.get("enterpriseValue"))
            if shares is None:
                shares = _safe_float(info.get("sharesOutstanding"))
            if cash is None:
                cash = _safe_float(
                    info.get("totalCash")
                    or info.get("cash")
                )
            if total_debt is None:
                total_debt = _safe_float(info.get("totalDebt"))

            trailing_eps = _safe_float(info.get("trailingEps"))

            # Fill missing valuation/growth fields from raw yfinance info.
            if pe_current is None:
                pe_current = _safe_float(info.get("trailingPE"))
            if pe_current is None and price is not None and trailing_eps not in (None, 0):
                # Best-effort PE fallback for cases where providers omit trailingPE.
                pe_current = price / trailing_eps

            if pe_forward is None:
                pe_forward = _safe_float(info.get("forwardPE"))
            if peg_ratio is None:
                peg_ratio = _safe_float(info.get("pegRatio"))

            if eps_growth is None:
                eps_growth = _safe_float(info.get("earningsGrowth"))
            if eps_growth is None:
                eps_growth = _compute_eps_growth_from_quarterly_eps(
                    getattr(yt, "quarterly_income_stmt", None)
                )

            if revenue_growth is None:
                revenue_growth = _safe_float(info.get("revenueGrowth"))
        except Exception as exc:
            logger.debug("yfinance enrichment skipped for %s (%s)", candidate, exc)
            continue

        # Stop once all critical tracked fields are populated.
        if all(
            value is not None
            for value in (
                pe_current,
                pe_forward,
                peg_ratio,
                eps_growth,
                revenue_growth,
                total_debt,
            )
        ):
            break

    # -- 2.5 Alternative provider backfill (best-effort) ----------------
    before_backfill = {
        "pe_current": pe_current,
        "pe_forward": pe_forward,
        "peg_ratio": peg_ratio,
        "eps_growth": eps_growth,
        "revenue_growth": revenue_growth,
        "total_debt": total_debt,
    }
    backfill, backfill_provider = _backfill_from_external_providers(
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

    if peg_ratio is None and pe_current is not None and eps_growth not in (None, 0):
        # Best-effort internal PEG backfill using existing PE + growth inputs.
        # eps_growth is stored as decimal (0.10 = 10%), hence *100 in denominator.
        try:
            peg_ratio = pe_current / (eps_growth * 100.0)
        except Exception:
            pass

    if source == "unknown" and backfill_provider and any(
        before_backfill[key] is None and backfill[key] is not None
        for key in backfill
    ):
        source = backfill_provider
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
    elif source in ("finnhub", "yfinance", "twelvedata", "eodhd", "alpha_vantage", "fmp"):
        status = "fresh"  # live fetch succeeded
    elif served_from == "cache":
        status = "cached"
    else:
        status = "unavailable"

    tracked_fields = {
        "pe_current": pe_current,
        "pe_forward": pe_forward,
        "peg_ratio": peg_ratio,
        "eps_growth": eps_growth,
        "revenue_growth": revenue_growth,
        "total_debt": total_debt,
    }
    missing_field_reasons = _classify_missing_field_reasons(
        field_values=tracked_fields,
        financials=financials if isinstance(financials, dict) else {},
        provider_availability=_fallback_provider_availability(),
    )

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
        missing_field_reasons=missing_field_reasons,
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
