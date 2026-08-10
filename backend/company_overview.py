"""
Company Overview Service — fetches yfinance + Tavily data,
synthesizes via LLM into structured JSON, caches for 7 days.

async get_company_overview(ticker, language="en") → Dict[str, Any]

⚠️ LANGUAGE SEPARATION:
  Step 1 — English: LLM generates EN content → cache
  Step 2 — Japanese: translate EN content via separate LLM call → cache
  NEVER generate mixed-language content in a single LLM call.

Phases:
  1. yfinance Ticker.info + Tavily web search
  2. LLM synthesis to strict JSON (EN only)
  3. Optional: LLM translation to JP (separate call)
  4. 7-day file-based JSON cache (ticker + language keyed)
"""

import os
import json
import math
import re
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── Cache layer ───────────────────────────────────────────────────────────
# Cache key format: company_overview:{ticker}:en:v1 / company_overview:{ticker}:jp:v1

CACHE_DIR = Path(__file__).parent / ".cache"
OVERVIEW_CACHE_TTL = 7 * 24 * 3600  # 7 days
OVERVIEW_CACHE_VERSION = 3  # v3 adds verified leadership-transition metadata

# Official, dated succession announcements used when search providers are
# unavailable or incomplete. Entries remain safe after the transition because
# the effective-date logic below promotes the designate only on/after that date.
VERIFIED_LEADERSHIP_TRANSITIONS: Dict[str, Dict[str, str]] = {
    "AAPL": {
        "title": "Tim Cook to become Apple Executive Chairman; John Ternus to become Apple CEO",
        "url": (
            "https://www.apple.com/newsroom/2026/04/"
            "tim-cook-to-become-apple-executive-chairman-john-ternus-to-become-apple-ceo/"
        ),
        "content": (
            "John Ternus, senior vice president of Hardware Engineering, will become "
            "Apple's next chief executive officer effective on September 1, 2026."
        ),
        "date": "2026-04-20",
        "current_ceo": "Tim Cook",
    },
}


def _overview_cache_path(ticker: str, language: str) -> Path:
    """Cache file: .cache/company_overview_AAPL_en_v1.json"""
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"company_overview_{ticker.upper()}_{language}_v{OVERVIEW_CACHE_VERSION}.json"


def _overview_cache_get(ticker: str, language: str) -> Optional[Dict[str, Any]]:
    """Read cached overview if fresh and version matches."""
    path = _overview_cache_path(ticker, language)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            entry = json.load(f)
        if entry.get("version") != OVERVIEW_CACHE_VERSION:
            logger.info(f"Overview cache VERSION mismatch for {ticker}/{language}")
            return None
        age = datetime.now(timezone.utc).timestamp() - entry.get("timestamp", 0)
        if age > OVERVIEW_CACHE_TTL:
            logger.info(f"Overview cache EXPIRED for {ticker}/{language} (age: {age/86400:.1f}d)")
            return None
        data = entry["data"]
        provenance = data.get("key_financials_provenance") if isinstance(data, dict) else None
        if not isinstance(provenance, dict) or provenance.get("schema_version") != 1:
            logger.info(f"Overview cache PROVENANCE mismatch for {ticker}/{language}")
            return None
        logger.info(f"Overview cache HIT for {ticker}/{language} (age: {age/86400:.1f}d)")
        return data
    except Exception as e:
        logger.debug(f"Overview cache read error for {ticker}/{language}: {e}")
    return None


def overview_cache_info(ticker: str, language: str) -> Dict[str, Any]:
    """Return cache metadata: whether cached, age, timestamp, TTL.

    Used by the frontend to show cache freshness and allow flushing.
    """
    path = _overview_cache_path(ticker, language)
    if not path.exists():
        return {"cached": False, "ticker": ticker.upper(), "language": language,
                "ttl_days": OVERVIEW_CACHE_TTL / 86400}

    try:
        with open(path) as f:
            entry = json.load(f)
        ts = entry.get("timestamp", 0)
        age = datetime.now(timezone.utc).timestamp() - ts
        return {
            "cached": True,
            "ticker": ticker.upper(),
            "language": language,
            "cache_version": entry.get("version"),
            "cached_at": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            "age_seconds": round(age),
            "age_days": round(age / 86400, 1),
            "ttl_seconds": OVERVIEW_CACHE_TTL,
            "ttl_days": OVERVIEW_CACHE_TTL / 86400,
            "expired": age > OVERVIEW_CACHE_TTL,
        }
    except Exception as e:
        logger.warning(f"Overview cache info error for {ticker}/{language}: {e}")
        return {"cached": False, "ticker": ticker.upper(), "language": language,
                "error": str(e), "ttl_days": OVERVIEW_CACHE_TTL / 86400}


def overview_cache_flush(ticker: str, language: Optional[str] = None) -> Dict[str, Any]:
    """Delete cached overview(s). If language is None, flush all languages for this ticker.

    Returns summary of what was deleted.
    """
    deleted = []
    not_found = []

    if language:
        languages = [language]
    else:
        # Discover all language variants for this ticker
        languages = []
        raw_pattern = f"company_overview_{ticker.upper()}_"
        for p in CACHE_DIR.glob(f"{raw_pattern}*_v{OVERVIEW_CACHE_VERSION}.json"):
            # Extract language from filename: company_overview_AAPL_en_v1.json → en
            stem = p.stem  # company_overview_AAPL_en_v1
            parts = stem.split("_")
            if len(parts) >= 4:
                languages.append(parts[-2])  # "en" or "jp"

    for lang in languages:
        path = _overview_cache_path(ticker, lang)
        if path.exists():
            try:
                path.unlink()
                deleted.append(lang)
                logger.info(f"Overview cache FLUSHED for {ticker}/{lang}")
            except Exception as e:
                logger.warning(f"Overview cache flush error for {ticker}/{lang}: {e}")
        else:
            not_found.append(lang)

    return {
        "ticker": ticker.upper(),
        "deleted": deleted,
        "not_found": not_found,
        "cache_version": OVERVIEW_CACHE_VERSION,
    }


def _overview_cache_set(ticker: str, language: str, data: Dict[str, Any]) -> None:
    """Write overview to cache with version stamp."""
    try:
        entry = {
            "version": OVERVIEW_CACHE_VERSION,
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "data": data,
        }
        with open(_overview_cache_path(ticker, language), "w") as f:
            json.dump(entry, f, default=str)
        logger.info(f"Overview cache SET for {ticker}/{language}")
    except Exception as e:
        logger.warning(f"Overview cache SET failed for {ticker}/{language}: {e}")


# ── Phase 1: Data fetching ────────────────────────────────────────────────


async def _fetch_yahoo_info(ticker: str) -> Dict[str, Any]:
    """Fetch yfinance Ticker.info for a ticker.

    Wraps synchronous yfinance call in a thread to avoid blocking.
    """
    import asyncio
    import concurrent.futures

    def _sync_fetch():
        import yfinance as yf  # lazy import — slow startup
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        return _build_yahoo_info_dict(ticker, info)

    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        try:
            return await loop.run_in_executor(pool, _sync_fetch)
        except Exception as e:
            logger.warning(f"yfinance fetch failed for {ticker}: {e}")
            return {"ticker": ticker, "error": str(e)}


def _build_yahoo_info_dict(ticker: str, info: Dict[str, Any]) -> Dict[str, Any]:
    """Extract structured company data from yfinance Ticker.info."""
    return {
        "ticker": ticker,
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "website": info.get("website"),
        "employees": info.get("fullTimeEmployees"),
        "description": (info.get("longBusinessSummary") or "")[:3000] or None,
        # Financial metrics
        "market_cap": info.get("marketCap"),
        "enterprise_value": info.get("enterpriseValue"),
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "previous_close": info.get("previousClose") or info.get("regularMarketPreviousClose"),
        "pe_trailing": info.get("trailingPE"),
        "pe_forward": info.get("forwardPE"),
        "dividend_yield": info.get("dividendYield"),
        "dividend_rate": info.get("dividendRate"),
        "beta": info.get("beta"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "total_revenue": info.get("totalRevenue"),
        "net_income": info.get("netIncomeToCommon"),  # Net Income to Common Stockholders
        "currency": info.get("currency", "USD"),
        "exchange": info.get("exchange"),
        # Key financial ratios (often missing from yfinance but included when available)
        "gross_margins": info.get("grossMargins"),
        "operating_margins": info.get("operatingMargins"),
        "free_cashflow": info.get("freeCashflow"),
        "peg_ratio": info.get("pegRatio"),
        # Leadership
        "company_officers": info.get("companyOfficers", []),
        # Location
        "headquarters": _format_headquarters(info),
        "source_snapshot_metadata": {
            "provider": "yfinance",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        "_raw_info": info,
    }


def _format_headquarters(info: Dict[str, Any]) -> Optional[str]:
    """Format city, state, country into a display string."""
    parts = []
    for key in ("city", "state", "country"):
        val = info.get(key)
        if val:
            parts.append(val)
    return ", ".join(parts) if parts else None


# ── Canonical key_financials resolver ────────────────────────────────────

_PLACEHOLDER_NUMERIC_STRINGS = {"", "n/a", "na", "none", "null", "undefined", "nan", "data not available", "—", "-"}
_MONEY_SUFFIXES = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}


def _get_path(data: Any, path: str) -> Any:
    """Read dotted paths from nested dictionaries."""
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _normalize_numeric(value: Any, *, ratio: bool = False) -> tuple[Optional[float], Optional[str]]:
    """Normalize provider numbers before comparison; returns (value, reason)."""
    if value is None:
        return None, "provider_missing"
    if isinstance(value, bool):
        return None, "malformed_source_value"
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None, "malformed_source_value"
    elif isinstance(value, str):
        raw = value.strip().lower()
        if raw in _PLACEHOLDER_NUMERIC_STRINGS:
            return None, "provider_missing"
        clean = raw.replace("$", "").replace(",", "").replace("%", "").strip()
        suffix = clean[-1:] if clean else ""
        multiplier = 1.0
        if suffix in _MONEY_SUFFIXES:
            multiplier = _MONEY_SUFFIXES[suffix]
            clean = clean[:-1]
        try:
            number = float(clean) * multiplier
        except (TypeError, ValueError):
            return None, "malformed_source_value"
    else:
        return None, "malformed_source_value"
    if number != number or number in (float("inf"), float("-inf")):
        return None, "malformed_source_value"
    note = None
    if ratio and number > 1 and number <= 100:
        number = number / 100
        note = "percent_input_normalized"
    return number, note


def _display_money(value: Optional[float]) -> str:
    return _format_currency(value) if value is not None else "Not available"


def _display_ratio(value: Optional[float], *, percent: bool = False) -> str:
    if value is None:
        return "Not available"
    if percent:
        return f"{value * 100:.1f}%"
    return f"{value:.2f}"


def _candidate(source: str, path: str, data: Dict[str, Any], *, ratio: bool = False, unit: str = "") -> Dict[str, Any]:
    raw = _get_path(data, path)
    normalized, reason = _normalize_numeric(raw, ratio=ratio)
    return {
        "source": source,
        "path": path,
        "raw_value": raw,
        "normalized_value": normalized,
        "valid": normalized is not None,
        "reason_code": None if normalized is not None else reason,
        "normalization_note": reason if reason == "percent_input_normalized" else None,
        "unit": unit,
    }


def _select_candidate(
    ticker: str,
    field: str,
    candidates: list[Dict[str, Any]],
    *,
    tolerance_rel: float = 0.10,
    tolerance_abs: float = 0.0,
    unit: str = "",
    period: str = "market_data",
    display_kind: str = "number",
    primary_source: str = "ledger",
) -> tuple[Optional[float], Dict[str, Any]]:
    valid = [c for c in candidates if c.get("valid")]
    base = {
        "status": "unavailable",
        "reason_code": "both_sources_absent",
        "selected_source": None,
        "selected_path": None,
        "raw_value": None,
        "normalized_value": None,
        "display_value": "Not available",
        "unit": unit,
        "period": period,
        "comparison": None,
        "candidates": candidates,
    }
    if not valid:
        reasons = [c.get("reason_code") for c in candidates if c.get("reason_code")]
        if reasons and all(r == "malformed_source_value" for r in reasons):
            base["reason_code"] = "malformed_source_value"
        return None, base

    if len(valid) >= 2:
        first, second = valid[0], valid[1]
        a = first["normalized_value"]
        b = second["normalized_value"]
        denom = max(abs(a), abs(b), tolerance_abs or 1.0)
        rel_delta = abs(a - b) / denom
        abs_delta = abs(a - b)
        accepted = rel_delta <= tolerance_rel or abs_delta <= tolerance_abs
        comparison = {
            "tolerance_rel": tolerance_rel,
            "tolerance_abs": tolerance_abs,
            "relative_delta": rel_delta,
            "absolute_delta": abs_delta,
            "accepted": accepted,
        }
        if not accepted:
            base.update({"status": "blocked", "reason_code": "mismatch_blocked", "comparison": comparison})
            logger.warning("[%s] key_financials.%s blocked: source mismatch %.3f", ticker, field, rel_delta)
            return None, base
        selected = next((c for c in valid if c.get("source") == primary_source), valid[0])
    else:
        selected = valid[0]
        comparison = None

    normalized = selected["normalized_value"]
    if display_kind == "money":
        display_value = _display_money(normalized)
    elif display_kind == "percent":
        display_value = _display_ratio(normalized, percent=True)
    elif display_kind == "multiple":
        display_value = f"{normalized:.2f}x"
    elif display_kind == "price":
        display_value = f"${normalized:.2f}"
    else:
        display_value = _display_ratio(normalized)
    base.update({
        "status": "selected",
        "reason_code": None,
        "selected_source": selected.get("source"),
        "selected_path": selected.get("path"),
        "raw_value": selected.get("raw_value"),
        "normalized_value": normalized,
        "display_value": display_value,
        "comparison": comparison,
    })
    return normalized, base


def _resolve_key_financials(
    ticker: str,
    yahoo_snapshot: Optional[Dict[str, Any]] = None,
    ledger: Optional[Dict[str, Any]] = None,
    llm_financials: Optional[Dict[str, Any]] = None,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Select numeric Company Overview facts once and attach auditable provenance.

    LLM-provided numeric key_financials are retained only as non-authoritative candidates;
    selected values come from the internal ledger/pipeline snapshot and Yahoo snapshot.
    """
    yahoo_snapshot = yahoo_snapshot or {}
    ledger = ledger or {}
    llm_financials = llm_financials or {}
    raw_info = yahoo_snapshot.get("_raw_info", {}) if isinstance(yahoo_snapshot.get("_raw_info"), dict) else {}
    yahoo = dict(yahoo_snapshot)
    yahoo["_raw_info"] = raw_info

    fields: Dict[str, Any] = {}
    selected: Dict[str, Any] = {}

    def select(field: str, paths: list[tuple[str, str, Dict[str, Any]]], **kwargs):
        candidates = [_candidate(src, p, data, ratio=kwargs.get("ratio", False), unit=kwargs.get("unit", "")) for src, p, data in paths]
        if field in llm_financials:
            llm_value, llm_reason = _normalize_numeric(llm_financials.get(field), ratio=kwargs.get("ratio", False))
            candidates.append({
                "source": "llm_output",
                "path": f"key_financials.{field}",
                "raw_value": llm_financials.get(field),
                "normalized_value": llm_value,
                "valid": llm_value is not None,
                "reason_code": None if llm_value is not None else llm_reason,
                "non_authoritative": True,
                "unit": kwargs.get("unit", ""),
            })
        authoritative = [c for c in candidates if c.get("source") != "llm_output"]
        value, provenance = _select_candidate(ticker, field, authoritative, **{k: v for k, v in kwargs.items() if k not in {"ratio"}})
        provenance["candidates"] = candidates
        fields[field] = provenance
        selected[field] = value
        selected[f"{field}_display"] = provenance["display_value"]
        return value

    select("market_cap", [("ledger", "market_cap", ledger), ("yahoo_snapshot", "market_cap", yahoo), ("yahoo_snapshot", "_raw_info.marketCap", yahoo)], unit="USD", period="market_data", display_kind="money", tolerance_abs=1_000_000)
    # Revenue card is labeled TTM — candidates must be same-basis (TTM).
    # Mixing fiscal-year annual and single-quarter ledger figures made the
    # comparator see a 62% "mismatch" on fast growers and block the metric
    # (NVDA 2026-06-12: 'Revenue (TTM): Not available / Under review').
    select("revenue", [("yahoo_snapshot", "total_revenue", yahoo), ("yahoo_snapshot", "_raw_info.totalRevenue", yahoo)], unit="USD", period="ttm", display_kind="money", tolerance_abs=1_000_000)
    select("revenue_growth", [("ledger", "financials.revenue_yoy_growth", ledger), ("ledger", "financials.revenue_annual_growth", ledger), ("yahoo_snapshot", "revenue_growth", yahoo), ("yahoo_snapshot", "_raw_info.revenueGrowth", yahoo)], unit="ratio", period="yoy", display_kind="percent", ratio=True, tolerance_rel=0.20)
    select("gross_margin", [("ledger", "financials.gross_margin", ledger), ("yahoo_snapshot", "gross_margins", yahoo), ("yahoo_snapshot", "_raw_info.grossMargins", yahoo)], unit="ratio", period="ttm", display_kind="percent", ratio=True, tolerance_abs=0.02)
    select("operating_margin", [("ledger", "financials.operating_margin", ledger), ("yahoo_snapshot", "operating_margins", yahoo), ("yahoo_snapshot", "_raw_info.operatingMargins", yahoo)], unit="ratio", period="ttm", display_kind="percent", ratio=True, tolerance_abs=0.02)
    select("net_income", [("ledger", "financials.net_income", ledger), ("yahoo_snapshot", "net_income", yahoo), ("yahoo_snapshot", "_raw_info.netIncomeToCommon", yahoo)], unit="USD", period="annual_or_ttm", display_kind="money", tolerance_abs=1_000_000)
    fcf = select("free_cash_flow", [("ledger", "financials.free_cash_flow", ledger), ("yahoo_snapshot", "free_cashflow", yahoo), ("yahoo_snapshot", "_raw_info.freeCashflow", yahoo)], unit="USD", period="annual_or_ttm", display_kind="money", tolerance_abs=1_000_000)
    selected["free_cashflow"] = fcf
    select("pe_ratio", [("ledger", "pe_current", ledger), ("yahoo_snapshot", "pe_trailing", yahoo), ("yahoo_snapshot", "_raw_info.trailingPE", yahoo)], unit="multiple", period="market_data", display_kind="multiple")
    select("pe_forward", [("ledger", "pe_forward", ledger), ("yahoo_snapshot", "pe_forward", yahoo), ("yahoo_snapshot", "_raw_info.forwardPE", yahoo)], unit="multiple", period="market_data", display_kind="multiple")
    select("beta", [("ledger", "beta", ledger), ("yahoo_snapshot", "beta", yahoo), ("yahoo_snapshot", "_raw_info.beta", yahoo)], unit="ratio", period="market_data", display_kind="number")
    low = select("52w_low", [("ledger", "52w_low", ledger), ("yahoo_snapshot", "52w_low", yahoo), ("yahoo_snapshot", "_raw_info.fiftyTwoWeekLow", yahoo)], unit="USD/share", period="52_week", display_kind="price", primary_source="yahoo_snapshot")
    high = select("52w_high", [("ledger", "52w_high", ledger), ("yahoo_snapshot", "52w_high", yahoo), ("yahoo_snapshot", "_raw_info.fiftyTwoWeekHigh", yahoo)], unit="USD/share", period="52_week", display_kind="price", primary_source="yahoo_snapshot")
    if low is not None and high is not None and low > high:
        for field in ("52w_low", "52w_high"):
            fields[field].update({"status": "blocked", "reason_code": "malformed_source_value", "normalized_value": None, "display_value": "Not available"})
            selected[field] = None
            selected[f"{field}_display"] = "Not available"

    # Dividend yield: selected from components when available.
    div_rate, div_rate_p = _select_candidate(ticker, "dividend_rate", [_candidate("yahoo_snapshot", "dividend_rate", yahoo, unit="USD/share"), _candidate("yahoo_snapshot", "_raw_info.dividendRate", yahoo, unit="USD/share")], unit="USD/share", period="market_data")
    current_price, price_p = _select_candidate(ticker, "current_price", [_candidate("yahoo_snapshot", "current_price", yahoo, unit="USD/share"), _candidate("yahoo_snapshot", "_raw_info.currentPrice", yahoo, unit="USD/share"), _candidate("yahoo_snapshot", "_raw_info.regularMarketPrice", yahoo, unit="USD/share")], unit="USD/share", period="market_data", display_kind="price")
    if div_rate is not None and current_price is not None and current_price > 0:
        div_yield = div_rate / current_price
        selected["dividend_yield"] = div_yield
        selected["dividend_yield_display"] = _display_ratio(div_yield, percent=True)
        fields["dividend_yield"] = {
            "status": "selected", "reason_code": "computed_from_components", "selected_source": "computed", "selected_path": "dividend_rate/current_price", "raw_value": None, "normalized_value": div_yield, "display_value": selected["dividend_yield_display"], "unit": "ratio", "period": "market_data", "comparison": None, "candidates": [div_rate_p, price_p]
        }
    else:
        select("dividend_yield", [("yahoo_snapshot", "dividend_yield", yahoo), ("yahoo_snapshot", "_raw_info.dividendYield", yahoo)], unit="ratio", period="market_data", display_kind="percent", ratio=True, primary_source="yahoo_snapshot")

    pe = selected.get("pe_ratio")
    earnings_growth = _candidate("ledger", "financials.earnings_growth", ledger, ratio=True, unit="ratio")
    if not earnings_growth.get("valid"):
        earnings_growth = _candidate("yahoo_snapshot", "earnings_growth", yahoo, ratio=True, unit="ratio")
    if pe is not None and earnings_growth.get("valid") and earnings_growth["normalized_value"] > 0:
        peg = pe / (earnings_growth["normalized_value"] * 100)
        selected["peg_ratio"] = peg
        selected["peg_ratio_display"] = f"{peg:.2f}x"
        fields["peg_ratio"] = {
            "status": "selected", "reason_code": "computed_from_components", "selected_source": "computed", "selected_path": "pe_ratio/earnings_growth", "raw_value": None, "normalized_value": peg, "display_value": selected["peg_ratio_display"], "unit": "multiple", "period": "market_data", "comparison": None, "candidates": [fields.get("pe_ratio"), earnings_growth, _candidate("yahoo_snapshot", "peg_ratio", yahoo, unit="multiple"), _candidate("yahoo_snapshot", "_raw_info.pegRatio", yahoo, unit="multiple")]
        }
    else:
        select("peg_ratio", [("yahoo_snapshot", "peg_ratio", yahoo), ("yahoo_snapshot", "_raw_info.pegRatio", yahoo)], unit="multiple", period="market_data", display_kind="multiple", primary_source="yahoo_snapshot")

    provenance = {
        "schema_version": 1,
        "ticker": ticker.upper(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fields": fields,
    }
    return selected, provenance


def _ceo_from_officers(yahoo_snapshot: Dict[str, Any]) -> Optional[str]:
    """Pick the CEO name from yfinance companyOfficers, if present."""
    officers = yahoo_snapshot.get("company_officers") or []
    if not officers and isinstance(yahoo_snapshot.get("_raw_info"), dict):
        officers = yahoo_snapshot["_raw_info"].get("companyOfficers") or []
    for officer in officers:
        title = str(officer.get("title", ""))
        if ("CEO" in title.upper() or "CHIEF EXECUTIVE" in title.upper()) and officer.get("name"):
            return str(officer["name"])
    return None


def _apply_verified_leadership_transition(
    overview: Dict[str, Any],
    search_results: List[Dict[str, str]],
    *,
    ticker: str | None = None,
    as_of: date | None = None,
) -> Dict[str, Any]:
    """Overlay a CEO transition only when an official company source states it.

    Structured provider profiles often lag announced successions. We keep the
    incumbent until the effective date, surface the CEO-designate meanwhile,
    and retain the exact official announcement URL for auditability.
    """
    if not isinstance(overview, dict):
        return overview
    profile = overview.setdefault("company_profile", {})
    if not isinstance(profile, dict):
        return overview

    website_host = (urlparse(str(profile.get("website") or "")).hostname or "").lower()
    website_root = ".".join(website_host.removeprefix("www.").split(".")[-2:])
    if not website_root:
        return overview

    today = as_of or datetime.now(timezone.utc).date()
    candidates = list(search_results or [])
    verified = VERIFIED_LEADERSHIP_TRANSITIONS.get(str(ticker or "").upper())
    if verified and not any(item.get("url") == verified["url"] for item in candidates):
        candidates.append(dict(verified))

    for item in candidates:
        url = str(item.get("url") or "")
        source_host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        if not source_host or not (
            source_host == website_root or source_host.endswith(f".{website_root}")
        ):
            continue

        title = str(item.get("title") or "")
        content = str(item.get("content") or "")
        combined = f"{title}. {content}"
        date_match = re.search(
            r"\beffective(?:\s+on)?\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
            combined,
        )
        if not date_match:
            continue
        try:
            effective = datetime.strptime(date_match.group(1), "%B %d, %Y").date()
        except ValueError:
            continue

        name_match = re.search(
            r"\b([A-Z][A-Za-z.'’-]+(?:\s+[A-Z][A-Za-z.'’-]+){1,2})"
            r"(?:,\s+[^.]{1,160}?,)?\s+will become\s+[^.]{0,100}?"
            r"(?:chief executive officer|CEO)\b",
            content,
        )
        if not name_match:
            name_match = re.search(
                r"\b([A-Z][A-Za-z.'’-]+\s+[A-Z][A-Za-z.'’-]+)\s+"
                r"to become\s+[^.]{0,60}?CEO\b",
                title,
            )
        if not name_match:
            continue

        designate = " ".join(name_match.group(1).split())
        official_incumbent = str(item.get("current_ceo") or "").strip()
        incumbent = official_incumbent or str(profile.get("ceo") or "").strip()
        if official_incumbent:
            profile["ceo"] = official_incumbent
        profile["ceo_effective_date"] = effective.isoformat()
        profile["ceo_transition_source_url"] = url
        profile["ceo_transition_verified_as_of"] = today.isoformat()
        if today >= effective:
            if incumbent and incumbent.casefold() != designate.casefold():
                profile["former_ceo"] = incumbent
            profile["ceo"] = designate
            profile.pop("ceo_designate", None)
            transition_note = (
                f"{designate} became CEO on {effective.strftime('%B')} {effective.day}, "
                f"{effective.year}, following the officially announced succession. "
                f"Official company announcement: {url}"
            )
        else:
            profile["ceo_designate"] = designate
            previous_day = effective - timedelta(days=1)
            transition_note = (
                f"{incumbent} remains CEO through {previous_day.strftime('%B')} "
                f"{previous_day.day}, {previous_day.year}; {designate} is CEO-designate "
                f"and becomes CEO on {effective.strftime('%B')} {effective.day}, {effective.year}. "
                f"Official company announcement: {url}"
            )
        existing_style = str(overview.get("ceo_leadership_style") or "").strip()
        if "CEO information not available from current structured data sources" in existing_style:
            existing_style = ""
        if url not in existing_style:
            overview["ceo_leadership_style"] = " ".join(
                part for part in (transition_note, existing_style) if part
            )
        return overview

    return overview


def _needs_rich_profile_fetch(snapshot: Optional[Dict[str, Any]]) -> bool:
    """Return True when a pipeline market snapshot is too thin for Company Overview.

    Finnhub/cache snapshots are sufficient for price and financials but often lack
    yfinance identity fields (longBusinessSummary, website, HQ, employees,
    companyOfficers). Passing those sparse snapshots directly into Company
    Overview caused client PDFs to render "CEO Not identified" and generic
    "NVDA — data from Yahoo Finance" prose even though yfinance had the data.
    """
    if not isinstance(snapshot, dict):
        return True
    raw_info_obj = snapshot.get("_raw_info")
    raw_info: Dict[str, Any] = raw_info_obj if isinstance(raw_info_obj, dict) else {}
    return not any(
        snapshot.get(key) or raw_info.get(raw_key)
        for key, raw_key in (
            ("description", "longBusinessSummary"),
            ("website", "website"),
            ("employees", "fullTimeEmployees"),
            ("headquarters", "city"),
            ("company_officers", "companyOfficers"),
        )
    )


def _merge_rich_profile_snapshot(base: Optional[Dict[str, Any]], rich: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge yfinance identity/profile fields into an existing market snapshot.

    Financial and valuation fields from the pipeline ledger/Finnhub snapshot stay
    authoritative; this only fills descriptive identity fields used by Company
    Overview rendering and validation.
    """
    merged = dict(base or {})
    if not isinstance(rich, dict):
        return merged
    for key in (
        "name", "sector", "industry", "country", "website", "employees",
        "description", "exchange", "company_officers", "headquarters",
        "source_snapshot_metadata", "_raw_info",
    ):
        if rich.get(key) is not None and not merged.get(key):
            merged[key] = rich[key]
    return merged


def _backfill_company_profile(overview: Dict[str, Any], yahoo_snapshot: Dict[str, Any]) -> None:
    """Fill missing company_profile facts from the yahoo snapshot.

    LLM overviews often return a sparse profile (sector/industry only);
    the snapshot already carries the factual fields. LLM-provided values
    are never overwritten — only None/missing keys are backfilled.
    (NVDA 2026-06-12 investor PDF shipped Exchange/HQ/Country/Employees/
    Website as '—' while the snapshot had them all.)
    """
    profile = overview.setdefault("company_profile", {})
    if not isinstance(profile, dict):
        return
    raw_info_obj = yahoo_snapshot.get("_raw_info")
    raw_info: Dict[str, Any] = raw_info_obj if isinstance(raw_info_obj, dict) else {}
    headquarters_parts = [
        raw_info.get("city"),
        raw_info.get("state"),
        raw_info.get("country"),
    ]
    raw_headquarters = ", ".join(str(part) for part in headquarters_parts if part)
    backfill = {
        "name": yahoo_snapshot.get("name") or raw_info.get("longName") or raw_info.get("shortName"),
        "sector": yahoo_snapshot.get("sector") or raw_info.get("sector"),
        "industry": yahoo_snapshot.get("industry") or raw_info.get("industry"),
        "country": yahoo_snapshot.get("country") or raw_info.get("country"),
        "website": yahoo_snapshot.get("website") or raw_info.get("website"),
        "employees": yahoo_snapshot.get("employees") or raw_info.get("fullTimeEmployees"),
        "headquarters": yahoo_snapshot.get("headquarters") or raw_headquarters or None,
        "exchange": yahoo_snapshot.get("exchange") or raw_info.get("fullExchangeName") or raw_info.get("exchange"),
        "ceo": _ceo_from_officers(yahoo_snapshot),
    }
    for key, value in backfill.items():
        if value is not None and profile.get(key) is None:
            profile[key] = value


def _normalize_financial_claims(
    overview: Dict[str, Any],
    key_financials: Dict[str, Any],
) -> None:
    """Keep LLM prose numerically aligned with canonical structured metrics.

    The synthesis prompt can contain several provider snapshots with different
    periods or calculation conventions. The structured resolver already chooses
    one authoritative value for the Company Overview; mirror those values in the
    overview's English narrative instead of publishing contradictory figures on
    adjacent pages. Unrelated figures such as quarterly revenue are left alone.
    """

    def _number(key: str) -> Optional[float]:
        value = key_financials.get(key)
        if isinstance(value, bool) or value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def _percent(key: str) -> Optional[str]:
        number = _number(key)
        if number is None:
            return None
        if abs(number) <= 1.5:
            number *= 100
        return f"{number:.1f}%"

    def _ratio(key: str) -> Optional[str]:
        number = _number(key)
        if number is None:
            return None
        return f"{number:.2f}".rstrip("0").rstrip(".")

    replacements: list[tuple[re.Pattern[str], Optional[str]]] = [
        (
            re.compile(
                r"(\b(?:large\s+)?free cash flow(?:\s+generation)?"
                r"(?:\s+(?:is|was|of|around|about|at)){0,2}\s*[:=]?\s*)"
                r"\$?\d[\d,.]*\s*[TBM]\b",
                re.IGNORECASE,
            ),
            _format_currency(_number("free_cash_flow")),
        ),
        (
            re.compile(
                r"(\brevenue growth(?:\s+(?:is|was|of|around|about|at)){0,2}\s*)"
                r"[+-]?\d+(?:\.\d+)?%",
                re.IGNORECASE,
            ),
            _percent("revenue_growth"),
        ),
        (
            re.compile(
                r"(\bgross margin(?:\s+profile)?"
                r"(?:\s+(?:is|was|of|around|about|near|at)){0,2}\s*)"
                r"[+-]?\d+(?:\.\d+)?%",
                re.IGNORECASE,
            ),
            _percent("gross_margin"),
        ),
        (
            re.compile(
                r"(\boperating margin(?:\s+profile)?"
                r"(?:\s+(?:is|was|of|around|about|near|at)){0,2}\s*)"
                r"[+-]?\d+(?:\.\d+)?%",
                re.IGNORECASE,
            ),
            _percent("operating_margin"),
        ),
        (
            re.compile(
                r"(\bforward P/?E(?:\s+(?:is|was|of|around|about|at)){0,2}\s*)"
                r"\d+(?:\.\d+)?(x?)",
                re.IGNORECASE,
            ),
            _ratio("pe_forward"),
        ),
        (
            re.compile(
                r"(\bPEG(?:\s+ratio)?(?:\s+(?:is|was|of|around|about|at)){0,2}\s*)"
                r"\d+(?:\.\d+)?(x?)",
                re.IGNORECASE,
            ),
            _ratio("peg_ratio"),
        ),
    ]

    def _normalize_text(value: Any) -> Any:
        if not isinstance(value, str) or not value:
            return value
        normalized = value
        for pattern, replacement in replacements:
            if replacement is None:
                continue

            def _replace(match: re.Match[str], canonical: str = replacement) -> str:
                suffix = match.group(2) if match.lastindex and match.lastindex >= 2 else ""
                return f"{match.group(1)}{canonical}{suffix or ''}"

            normalized = pattern.sub(_replace, normalized)
        normalized = re.sub(r"\bpeer\s+peers\b", "peers", normalized, flags=re.IGNORECASE)
        return normalized

    for key in (
        "business_description",
        "revenue_model",
        "competitive_position",
        "strengths_vs_competitors",
        "weaker_areas_vs_competitors",
        "client_types",
        "management_weaknesses",
        "investor_takeaway",
        "ceo_leadership_style",
        "long_term_vision",
    ):
        overview[key] = _normalize_text(overview.get(key))

    for key in ("business_segments", "growth_drivers", "moats", "key_kpis", "business_risks"):
        values = overview.get(key)
        if isinstance(values, list):
            overview[key] = [_normalize_text(value) for value in values]

    for claim in overview.get("company_claims", []) or []:
        if isinstance(claim, dict):
            claim["text_en"] = _normalize_text(claim.get("text_en"))


def _apply_key_financials_provenance(
    overview: Dict[str, Any],
    ticker: str,
    yahoo_snapshot: Optional[Dict[str, Any]] = None,
    ledger: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Overlay canonical selected key_financials onto an overview payload."""
    if not isinstance(overview, dict):
        return overview
    _backfill_company_profile(overview, yahoo_snapshot or {})
    selected, provenance = _resolve_key_financials(
        ticker=ticker,
        yahoo_snapshot=yahoo_snapshot or {},
        ledger=ledger or {},
        llm_financials=overview.get("key_financials", {}) or {},
    )
    overview["key_financials"] = selected
    _normalize_financial_claims(overview, selected)
    overview["key_financials_provenance"] = provenance
    overview["source_snapshot_metadata"] = {
        "schema_version": 1,
        "yahoo_snapshot": (yahoo_snapshot or {}).get("source_snapshot_metadata", {}),
        "ledger_present": bool(ledger),
        "ledger_build_timestamp": datetime.now(timezone.utc).isoformat() if ledger else None,
    }
    return overview


async def _search_tavily_overview(ticker: str, yf_info: Dict[str, Any]) -> List[Dict[str, str]]:
    """Search Tavily for recent company news and developments."""
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        logger.debug(f"Tavily skipped for {ticker} overview — TAVILY_API_KEY not set")
        return []

    import asyncio
    import concurrent.futures

    def _sync_search():
        from backend.http_client import http

        company_name = yf_info.get("name", ticker)
        queries = [
            f"{company_name} latest news 2026",
            f"{company_name} recent developments products",
            f"{company_name} CEO leadership transition 2026 official",
        ]
        all_results = []

        for query in queries:
            try:
                resp = http.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": api_key,
                        "query": query,
                        "max_results": 5,
                        "search_depth": "basic",
                        "include_answer": False,
                        "include_raw_content": False,
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for r in data.get("results", [])[:5]:
                        all_results.append({
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "content": (r.get("content", "") or "")[:500],
                            "date": r.get("published_date", ""),
                        })
                else:
                    logger.warning(f"Tavily search HTTP {resp.status_code} for {ticker}")
            except Exception as e:
                logger.warning(f"Tavily search failed for {ticker}: {e}")

        seen = set()
        unique = []
        for item in all_results:
            if item["url"] not in seen:
                seen.add(item["url"])
                unique.append(item)
        return unique[:8]

    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        try:
            return await loop.run_in_executor(pool, _sync_search)
        except Exception as e:
            logger.warning(f"Tavily overview search failed for {ticker}: {e}")
            return []


# ── Phase 2: LLM synthesis (EN only) ──────────────────────────────────────


def _synthesize_overview_en(
    ticker: str,
    yf_info: Dict[str, Any],
    tavily_results: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Step 1 — English: LLM generates structured company overview in English.

    Returns a dict matching the company_overview schema with text_en fields.
    """
    from backend.codex_provider import _codex_chat

    yf_str = json.dumps(yf_info, indent=2, default=str)

    if tavily_results:
        items = []
        for r in tavily_results[:8]:
            items.append(f"- {r['title']}\n  URL: {r['url']}\n  {r['content'][:300]}")
        tavily_str = "\n".join(items)
    else:
        tavily_str = "(No recent news results available)"

    prompt = f"""Synthesize a professional company overview for {yf_info.get('name', ticker)} ({ticker}) in English.

Data from Yahoo Finance:
```json
{yf_str}
```

Recent web search results:
{tavily_str}

Return ONLY a valid JSON object (no markdown, no explanation) with EXACTLY this structure:

{{
  "company_profile": {{
    "name": "full company name",
    "ticker": "{ticker}",
    "sector": "sector name",
    "industry": "industry name",
    "country": "country name",
    "website": "URL",
    "employees": 12345,
    "founded": null,
    "headquarters": "City, State, Country",
    "ceo": "current CEO name",
    "ceo_designate": null,
    "ceo_effective_date": null,
    "ceo_transition_source_url": null
  }},
  "business_description": "A comprehensive 5-8 sentence paragraph (~10 lines) describing what the company does, its products, markets, and scale. Be specific and detailed.",
  "revenue_model": "A comprehensive 5-8 sentence paragraph (~10 lines) explaining how the company makes money — major revenue engines, monetization approach, key customer segments. Be specific and detailed.",
  "business_segments": ["Segment Name: Brief description of what this segment does and its key products", "Second Segment: Brief description", "Third Segment: Brief description (include geographic segments if available)"],
  "growth_drivers": ["REQUIRED: at least 3 specific, company-tailored growth drivers. Each must be a full sentence with evidence.", "REQUIRED: second driver", "REQUIRED: third driver"],
  "moats": ["REQUIRED: at least 2 specific moats. Each must name the moat and explain why it is durable.", "REQUIRED: second moat"],
  "key_kpis": ["KPI 1 with value if known", "KPI 2 with value if known"],
  "business_risks": ["risk 1", "risk 2", "risk 3"],
  "key_financials": {{
    "market_cap": 1230000000000,
    "market_cap_display": "$1.23T",
    "revenue": 383000000000,
    "revenue_display": "$383.0B",
    "revenue_growth": 0.852,
    "gross_margin": 0.75,
    "operating_margin": 0.65,
    "net_income": 58000000000,
    "free_cash_flow": 96000000000,
    "pe_ratio": 30.5,
    "pe_forward": 28.0,
    "peg_ratio": 1.05,
    "dividend_yield": 0.0052,
    "beta": 1.25,
    "52w_high": 199.62,
    "52w_low": 124.17
  }},
  "recent_developments": [
    {{
      "title": "descriptive title",
      "summary": "2-3 sentence summary in English — be informative, not telegraphic",
      "date": "YYYY-MM-DD if known, else omit",
      "sentiment": "positive|neutral|negative"
    }}
  ],
  "competitive_position": "A comprehensive 5-8 sentence paragraph (~10 lines) analyzing market position, competitive advantages, threats, and market share dynamics. Be specific and analytical.",
  "strengths_vs_competitors": "A comprehensive 5-8 sentence paragraph (~10 lines) on concrete strengths relative to direct peers — specific advantages, not generic platitudes.",
  "weaker_areas_vs_competitors": "A comprehensive 5-8 sentence paragraph (~10 lines) on concrete weaker areas vs peers — be honest and specific, not vague.",
  "client_types": "A comprehensive 5-8 sentence paragraph (~10 lines) describing main customer types, end markets, customer concentration, and go-to-market approach.",
  "management_weaknesses": "A comprehensive 5-8 sentence paragraph (~10 lines) on management team weaknesses, turnover history, governance risks, or succession concerns.",
  "investor_takeaway": "A comprehensive 5-8 sentence paragraph (~10 lines) bottom-line investment takeaway — balanced bull/bear case, key catalysts, risks, and what to watch.",
  "ceo_leadership_style": "A comprehensive 5-8 sentence paragraph (~10 lines) on leadership style, track record, public perception, and strategic decision-making pattern.",
  "long_term_vision": "A comprehensive 5-8 sentence paragraph (~10 lines) on long-term strategy, vision, expansion plans, and how the company positions for the future.",
  "competitors": [
    {{
      "competitor_name": "competitor ticker/name",
      "text_en": "short comparative note",
      "text_jp": "",
      "source_id": "S1",
      "competitive_advantage": "what this company does better"
    }}
  ],
  "company_claims": [
    {{
      "claim_id": "C1",
      "text_en": "investor-relevant claim",
      "text_jp": "",
      "source_id": "S1",
      "section": "growth_drivers",
      "confidence": "medium"
    }}
  ]
}}

RULES:
- Use actual numbers from Yahoo Finance when available. If a field is missing, use null (not "N/A" or 0) for numbers.
- PARAGRAPH DEPTH: All text fields (business_description, revenue_model, competitive_position, strengths/weaker_areas, client_types, management_weaknesses, investor_takeaway, ceo_leadership_style, long_term_vision) MUST be substantial 5-8 sentence paragraphs, not 2-3 sentence summaries. Aim for ~10 lines each. This is client-facing professional analysis.
- For list fields, always return arrays (possibly empty), never strings.
- business_segments: list 3-5 SEGMENTS with descriptions using "Name: Description" format (e.g. "Compute & Networking: Data center GPUs, networking, and AI software."). Include business AND geographic segments if available. Each entry MUST include a colon-separated description.
- The CEO MUST be identified by name (e.g. "CEO Sundar Pichai"). If unknown, use null for the name field but state uncertainty in ceo_leadership_style.
- Announced CEO successions MUST preserve both the current CEO and CEO-designate until the effective date, with the exact official company announcement URL. Never promote a designate early.
- competitors: list at least 5-6 named competitors with ticker symbols. More is better — aim for a comprehensive competitive landscape.
- strengths_vs_competitors and weaker_areas_vs_competitors must be balanced competitive analysis, not valuation comments or volatility observations.
- NEVER use internal pipeline language: no "LLM synthesis was unavailable", no "could not be reliably synthesized", no "transcript-level validation", no "requires transcript-level", no "fallback dataset". This is client-facing content.
- growth_drivers, moats, key_kpis, and business_risks should be grounded in available data/news.
- recent_developments: pick 2-5 meaningful items from Tavily; write original summaries.
- ceo_leadership_style and long_term_vision: if evidence is weak, state uncertainty explicitly but never cite "lack of LLM" or "transcript unavailable" as the reason.

Return ONLY the JSON object. No markdown fences, no explanations."""

    system = "You are a senior equity research analyst synthesizing company overviews. You write in English. You return ONLY valid JSON with no markdown fences."

    # ── CedLab 2026-06-06: Company Overview must use Codex Spark quality path ──
    # SA_SKIP_CODEX still protects the broader Deep Dive flow, but Company Overview
    # is a client-facing downloadable investor profile and should use Ced's Plus
    # subscription by default. Override only with SA_COMPANY_OVERVIEW_SKIP_CODEX=true.
    co_skip_codex = os.getenv("SA_COMPANY_OVERVIEW_SKIP_CODEX", "false").strip().lower() in ("1", "true", "yes")
    co_codex_model = os.getenv("SA_COMPANY_OVERVIEW_CODEX_MODEL", os.getenv("SA_CODEX_MODEL", "gpt-5.3-codex-spark")).strip() or "gpt-5.3-codex-spark"
    co_reasoning_effort = os.getenv("SA_COMPANY_OVERVIEW_CODEX_REASONING_EFFORT", os.getenv("SA_CODEX_SYNTHESIS_EFFORT", "medium")).strip().lower() or "medium"
    if not co_skip_codex:
        response = _codex_chat(
            prompt,
            system=system,
            max_tokens=6000,
            model=co_codex_model,
            reasoning_effort=co_reasoning_effort,
        )
        if response:
            parsed = _parse_llm_response(response, ticker, yf_info)
            if parsed is not None:
                parsed.setdefault("generation_provider", "codex_cli")
                parsed.setdefault("generation_model", co_codex_model)
                parsed.setdefault("generation_reasoning_effort", co_reasoning_effort)
                logger.info(f"[{ticker}] Company Overview synthesis succeeded via {co_codex_model}/{co_reasoning_effort}")
                return parsed
            logger.warning(f"[{ticker}] {co_codex_model} response failed to parse, falling back to DeepSeek...")
        else:
            logger.warning(f"[{ticker}] {co_codex_model} unavailable, falling back to DeepSeek...")
    else:
        logger.info(f"[{ticker}] Company Overview Codex skipped (SA_COMPANY_OVERVIEW_SKIP_CODEX) — using DeepSeek fallback")

    # ── Optional fallback: DeepSeek V4 Pro ──────────
    enable_deepseek = os.getenv("SA_ENABLE_DEEPSEEK_FALLBACK", "false").strip().lower() in ("1", "true", "yes")
    if enable_deepseek:
        try:
            from backend.kimi_provider import _deepseek_chat
            ds_response = _deepseek_chat(prompt, system=system, max_tokens=6000, temperature=0.0)
            if ds_response:
                parsed = _parse_llm_response(ds_response, ticker, yf_info)
                if parsed is not None:
                    parsed.setdefault("generation_provider", "deepseek")
                    parsed.setdefault("generation_model", "deepseek-v4-pro")
                    logger.info(f"[{ticker}] DeepSeek synthesis succeeded")
                    return parsed
        except Exception as ds_e:
            logger.warning(f"[{ticker}] DeepSeek fallback failed: {ds_e}", exc_info=True)
    else:
        logger.info(f"[{ticker}] DeepSeek fallback disabled (SA_ENABLE_DEEPSEEK_FALLBACK=false)")

    # ── Fallback 2: Deterministic (yfinance + regex) ─────────
    return _fallback_overview(ticker, yf_info)


def _translate_overview_to_jp(en_overview: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    """Step 2 — Japanese: translate EN overview text fields to JP via separate LLM call.

    NEVER generate mixed-language content. This is a standalone translation call.
    Only text fields are translated; numeric data and structure are preserved.
    """
    from backend.codex_provider import _codex_chat

    # Build a compact representation of text fields that need translation
    text_fields: Dict[str, Any] = {
        "business_description": en_overview.get("business_description", ""),
        "revenue_model": en_overview.get("revenue_model", ""),
        "competitive_position": en_overview.get("competitive_position", ""),
        "strengths_vs_competitors": en_overview.get("strengths_vs_competitors", ""),
        "weaker_areas_vs_competitors": en_overview.get("weaker_areas_vs_competitors", ""),
        "ceo_leadership_style": en_overview.get("ceo_leadership_style", ""),
        "long_term_vision": en_overview.get("long_term_vision", ""),
    }

    list_fields = [
        "business_segments",
        "growth_drivers",
        "moats",
        "key_kpis",
        "business_risks",
    ]
    for field in list_fields:
        values = en_overview.get(field, []) or []
        if isinstance(values, list):
            for i, item in enumerate(values[:12]):
                text_fields[f"{field}_{i}"] = str(item)

    # Translate recent_developments summaries
    devs = en_overview.get("recent_developments", [])
    for i, dev in enumerate(devs[:8]):
        text_fields[f"dev_{i}_title"] = dev.get("title", "")
        text_fields[f"dev_{i}_summary"] = dev.get("summary", "")

    # Translate competitors free text fields
    competitors = en_overview.get("competitors", []) or []
    for i, comp in enumerate(competitors[:8]):
        text_fields[f"comp_{i}_text_en"] = comp.get("text_en", "")
        text_fields[f"comp_{i}_adv"] = comp.get("competitive_advantage", "")

    # Translate company claims
    claims = en_overview.get("company_claims", []) or []
    for i, claim in enumerate(claims[:16]):
        text_fields[f"claim_{i}_text_en"] = claim.get("text_en", "")

    prompt = f"""Translate the following English company overview text fields into professional Japanese (日本語).

Translation rules:
- Use natural, financial-analyst-level Japanese. No machine-translation feel.
- Preserve all factual information and numerical precision.
- Company names and tickers remain in English.
- For recent_developments sentiment, keep as "positive", "neutral", or "negative" in English.
- Return ONLY a valid JSON object with the translated fields. No markdown, no explanations.

Fields to translate:
```json
{json.dumps(text_fields, indent=2, ensure_ascii=False)}
```

Return a JSON object with the SAME keys but Japanese values.
Return ONLY the JSON object."""

    system = "You are a professional financial translator specializing in English→Japanese. You return ONLY valid JSON with translated fields. Natural Japanese, no machine-translation feel."

    jp_codex_model = os.getenv("SA_COMPANY_OVERVIEW_CODEX_MODEL", os.getenv("SA_CODEX_MODEL", "gpt-5.3-codex-spark")).strip() or "gpt-5.3-codex-spark"
    jp_reasoning_effort = os.getenv("SA_COMPANY_OVERVIEW_CODEX_REASONING_EFFORT", os.getenv("SA_CODEX_SYNTHESIS_EFFORT", "medium")).strip().lower() or "medium"
    response = _codex_chat(
        prompt,
        system=system,
        max_tokens=2400,
        model=jp_codex_model,
        reasoning_effort=jp_reasoning_effort,
    )

    if not response:
        logger.warning(f"JP translation LLM unavailable for {ticker} — returning EN content")
        return _wrap_jp_fallback(en_overview)

    translated = _parse_llm_response(response, ticker, {})
    if translated is None:
        return _wrap_jp_fallback(en_overview)

    # Build JP overview: copy structure, replace text fields with translations
    jp = json.loads(json.dumps(en_overview, default=str))  # deep copy

    for key in (
        "business_description",
        "revenue_model",
        "competitive_position",
        "strengths_vs_competitors",
        "weaker_areas_vs_competitors",
        "ceo_leadership_style",
        "long_term_vision",
    ):
        jp[key] = translated.get(key, en_overview.get(key, ""))

    # Replace list fields
    for field in list_fields:
        current = jp.get(field, []) or []
        if not isinstance(current, list):
            current = []
        rebuilt = []
        for i, item in enumerate(current[:12]):
            rebuilt.append(translated.get(f"{field}_{i}", item))
        jp[field] = rebuilt

    # Replace development titles and summaries
    for i, dev in enumerate(jp.get("recent_developments", [])[:8]):
        dev["title"] = translated.get(f"dev_{i}_title", dev.get("title", ""))
        dev["summary"] = translated.get(f"dev_{i}_summary", dev.get("summary", ""))

    # Replace competitor text fields
    for i, comp in enumerate(jp.get("competitors", [])[:8]):
        comp["text_jp"] = translated.get(f"comp_{i}_text_en", comp.get("text_jp") or comp.get("text_en", ""))
        if comp.get("competitive_advantage"):
            comp["competitive_advantage"] = translated.get(f"comp_{i}_adv", comp.get("competitive_advantage"))

    # Replace claim bilingual text
    for i, claim in enumerate(jp.get("company_claims", [])[:16]):
        claim["text_jp"] = translated.get(f"claim_{i}_text_en", claim.get("text_jp") or claim.get("text_en", ""))

    return jp


def _wrap_jp_fallback(en_overview: Dict[str, Any]) -> Dict[str, Any]:
    """When JP translation fails, return EN content with a marker."""
    result = json.loads(json.dumps(en_overview, default=str))
    result["_translation_note"] = "JP translation unavailable — showing EN content"
    return result


# ── Parsing and fallback ──────────────────────────────────────────────────


def _parse_llm_response(response: str, ticker: str, yf_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse LLM JSON response, stripping markdown fences and trailing chatter.

    Returns None if parsing fails (caller should use fallback). Spark sometimes
    returns a valid JSON object followed by a second object or commentary; decode
    the first valid object instead of rejecting the whole response as Extra data.
    """
    text = response.strip()
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence):].strip()
        if text.endswith("```"):
            text = text[:-3].strip()

    # Start at the first JSON object. Do NOT trim to the last brace first: when
    # Codex emits two JSON objects, json.loads(first...last) fails with Extra data.
    start = text.find("{")
    if start >= 0:
        text = text[start:]

    def _ensure_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                if item is None:
                    continue
                s = str(item).strip()
                if s:
                    out.append(s)
            return out
        if isinstance(value, str):
            # tolerate newline/comma-separated output
            parts = [p.strip(" -•\t") for p in value.replace("\r", "\n").split("\n")]
            items = [p for p in parts if p]
            if len(items) <= 1 and "," in value:
                items = [p.strip() for p in value.split(",") if p.strip()]
            return items
        return [str(value)]

    try:
        decoder = json.JSONDecoder()
        data, _ = decoder.raw_decode(text)
        if not isinstance(data, dict):
            raise ValueError("LLM JSON root is not an object")
        data.setdefault("company_profile", {})
        data.setdefault("business_description", "")
        data.setdefault("revenue_model", "")
        data.setdefault("business_segments", [])
        data.setdefault("growth_drivers", [])
        data.setdefault("moats", [])
        data.setdefault("key_kpis", [])
        data.setdefault("business_risks", [])
        data.setdefault("key_financials", {})
        data.setdefault("recent_developments", [])
        data.setdefault("competitive_position", "")
        data.setdefault("strengths_vs_competitors", "")
        data.setdefault("weaker_areas_vs_competitors", "")
        data.setdefault("ceo_leadership_style", "")
        data.setdefault("long_term_vision", "")
        data.setdefault("competitors", [])
        data.setdefault("company_claims", [])

        for list_key in ("business_segments", "growth_drivers", "moats", "key_kpis", "business_risks"):
            data[list_key] = _ensure_str_list(data.get(list_key))

        if yf_info:
            _apply_key_financials_provenance(data, ticker, yf_info)
        return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"LLM JSON parse failed for {ticker}: {e} | raw: {response[:200]}")
        return None


def _build_fallback_competitors(ticker: str, yf_info: Dict[str, Any]) -> list[Dict[str, str]]:
    """Build a basic competitor list from yfinance sector/industry data when LLM is unavailable."""
    competitors: list[Dict[str, str]] = []
    sector = yf_info.get("sector", "")
    industry = yf_info.get("industry", "")

    # Try Finnhub peer API first (real ticker-level peers)
    peer_tickers: list[str] = []
    try:
        from backend.peer_universe import _get_finnhub_peers
        peer_tickers = _get_finnhub_peers(ticker)
    except Exception:
        pass

    # Use sector peers from yfinance if available
    sector_peers = []
    if isinstance(yf_info.get("sectorKey"), str):
        sector_peers.append(yf_info["sectorKey"])
    if isinstance(yf_info.get("industryKey"), str):
        sector_peers.append(yf_info["industryKey"])

    if sector and industry:
        peer_names_str = ", ".join(peer_tickers[:8]) if peer_tickers else ""
        peer_note = f" Direct peers include: {peer_names_str}." if peer_names_str else ""
        competitors.append({
            "competitor_name": f"Peers in {sector} — {industry}",
            "text_en": (
                f"Key publicly traded competitors operate in the {sector} sector, "
                f"specifically within {industry}.{peer_note} Refer to the company's 10-K "
                f"(Item 1 — Business, Competition section) for named competitors "
                f"and its proxy statement for the peer group used in executive compensation benchmarking."
            ),
            "text_jp": "",
            "source_id": "FALLBACK",
            "competitive_advantage": (
                f"{ticker}'s competitive position within {industry} should be evaluated "
                "against peers on revenue scale, margin profile, growth rate, and market share trends."
            ),
        })
    elif sector:
        competitors.append({
            "competitor_name": f"Peers in {sector}",
            "text_en": (
                f"Competitors operate in the {sector} sector. "
                "Refer to the company's 10-K for a full competitive landscape."
            ),
            "text_jp": "",
            "source_id": "FALLBACK",
            "competitive_advantage": f"{ticker}'s position should be assessed relative to {sector} peers.",
        })

    return competitors


def _fallback_overview(ticker: str, yf_info: Dict[str, Any]) -> Dict[str, Any]:
    """Build a deterministic investor-oriented overview when LLM is unavailable."""
    # yf_info is raw Yahoo Ticker.info — camelCase keys
    mc = yf_info.get("marketCap")
    rev = yf_info.get("totalRevenue")
    desc = (yf_info.get("longBusinessSummary") or yf_info.get("description") or "").strip()
    beta = yf_info.get("beta")

    def _first_sentences(text: str, max_sentences: int = 2) -> str:
        if not text:
            return ""
        parts = [p.strip() for p in text.replace("\n", " ").split(".") if p.strip()]
        return ". ".join(parts[:max_sentences]) + ("." if parts else "")

    business_description = desc[:3000] if desc else f"{ticker} — data from Yahoo Finance."
    revenue_model = _first_sentences(desc, max_sentences=3) or (
        f"Revenue model estimated from available data for {ticker}. "
        "Refer to the company's investor relations for detailed revenue breakdowns."
    )

    sector = yf_info.get("sector")
    industry = yf_info.get("industry")
    business_segments: list[str] = []

    # Try extracting explicit segment names from longBusinessSummary text
    lower_desc = desc.lower()
    # Pattern: "operates through X segments" or "operates in X segments"
    # Try to extract named segments after the count
    seg_match = re.search(r'operates\s+(?:through|in)\s+(?:\w+\s+)?segments?[,:]\s*(.+?)(?:\.\s|$)', desc)
    if seg_match:
        seg_text = seg_match.group(1)
        # Split on common delimiters
        raw_parts = re.split(r'\s+(?:and|,)\s+|\s*;\s*', seg_text)
        for part in raw_parts[:6]:
            part = part.strip(' .')
            if part and len(part) > 2:
                business_segments.append(part)

    # Fallback: try "operates through X" pattern where X is a number
    if not business_segments:
        marker = "operates through "
        if marker in lower_desc and " segment" in lower_desc:
            start = lower_desc.find(marker) + len(marker)
            end = lower_desc.find(" segment", start)
            if end > start:
                segment_blob = desc[start:end]
                # Skip if it's just a number like "two"
                blob_clean = segment_blob.strip(' .')
                if not blob_clean.isalpha() or len(blob_clean) <= 3:
                    # Try to find actual segment names after "segments." or "segments,"
                    after_seg = re.search(r'segments?[,:]\s*(.+?)(?:\.\s|$)', desc[end:])
                    if after_seg:
                        seg_text = after_seg.group(1)
                        raw_parts = re.split(r'\s+(?:and|,)\s+|\s*;\s*', seg_text)
                        for part in raw_parts[:6]:
                            part = part.strip(' .')
                            if part and len(part) > 2:
                                business_segments.append(part)
                else:
                    # It's a word like "three" — try simple split
                    raw_parts = segment_blob.replace(" and ", ",").split(",")
                    for seg in raw_parts[:6]:
                        seg = seg.strip(' .')
                        if seg and len(seg) > 2:
                            business_segments.append(seg)

    if sector:
        business_segments.append(f"Primary sector exposure: {sector}.")
    if industry:
        business_segments.append(f"Core industry: {industry}.")

    # De-duplicate while preserving order
    dedup_segments: list[str] = []
    for seg in business_segments:
        if seg not in dedup_segments:
            dedup_segments.append(seg)
    business_segments = dedup_segments

    if not business_segments:
        business_segments.append("Business segment breakdown not available from current structured sources.")

    growth_drivers: list[str] = []
    rev_growth = yf_info.get("revenue_growth")
    earn_growth = yf_info.get("earnings_growth")
    if isinstance(rev_growth, (int, float)):
        direction = "strong" if rev_growth > 0.1 else "modest" if rev_growth > 0 else "negative"
        growth_drivers.append(
            f"Revenue expansion: {direction} top-line trajectory ({rev_growth * 100:+.1f}% YoY) "
            f"indicates the company is actively scaling its core business and capturing market demand"
        )
    if isinstance(earn_growth, (int, float)):
        direction = "robust" if earn_growth > 0.1 else "stable" if earn_growth > 0 else "declining"
        growth_drivers.append(
            f"Earnings momentum: {direction} bottom-line growth ({earn_growth * 100:+.1f}% YoY) "
            f"suggests operating leverage and cost discipline are converting revenue into profit"
        )
    if yf_info.get("enterprise_value") and mc:
        growth_drivers.append(
            "Scale economics: large enterprise footprint provides capital for R&D reinvestment, "
            "strategic acquisitions, and market expansion that smaller competitors cannot match"
        )
    # Add sector/industry based driver for more depth
    if industry and sector:
        growth_drivers.append(
            f"Industry tailwinds: {industry} sector within {sector} benefits from secular trends "
            f"in digital transformation, creating a multi-year demand runway for established players"
        )
    if not growth_drivers:
        growth_drivers.append(
            "Detailed growth drivers are not available from current structured data sources. "
            "Refer to the company's investor relations materials for strategic growth initiatives."
        )

    moats: list[str] = []
    if "cloud" in lower_desc:
        moats.append("Cloud platform scale and enterprise integration can create switching-cost advantages.")
    if "search" in lower_desc or "ads" in lower_desc or "advertis" in lower_desc:
        moats.append("Large user and advertiser ecosystems can reinforce network effects.")
    if "ai" in lower_desc:
        moats.append("AI infrastructure and model deployment capabilities may strengthen product differentiation.")
    if industry and not moats:
        moats.append(f"Industry positioning in {industry} may support durable competitive advantages.")
    if yf_info.get("website"):
        moats.append("Brand and distribution reach inferred from global platform presence.")
    if not moats:
        moats.append("Competitive moat assessment requires additional qualitative evidence.")

    key_kpis: list[str] = []
    if mc is not None:
        key_kpis.append(f"Market Cap: {_format_currency(mc)}")
    if rev is not None:
        key_kpis.append(f"Revenue: {_format_currency(rev)}")
    if yf_info.get("pe_trailing") is not None:
        key_kpis.append(f"Trailing P/E: {float(yf_info['pe_trailing']):.1f}x")
    if yf_info.get("pe_forward") is not None:
        key_kpis.append(f"Forward P/E: {float(yf_info['pe_forward']):.1f}x")
    if yf_info.get("52w_high") is not None and yf_info.get("52w_low") is not None:
        key_kpis.append(f"52W range: ${float(yf_info['52w_low']):.2f}–${float(yf_info['52w_high']):.2f}")
    if not key_kpis:
        key_kpis.append("KPI extraction unavailable from current market snapshot.")

    business_risks: list[str] = []
    beta = yf_info.get("beta")
    if isinstance(beta, (int, float)) and beta > 1.2:
        business_risks.append(
            f"Elevated market sensitivity: with a beta of {beta:.2f}, the stock tends to amplify "
            f"broader market movements — historically moving {beta:.1f}x the index — which can "
            f"magnify drawdowns during market corrections and test investor conviction"
        )
    if isinstance(rev_growth, (int, float)) and rev_growth < 0:
        business_risks.append(
            "Revenue contraction risk: declining top-line growth may pressure valuation multiples, "
            "reduce operating leverage, and signal weakening competitive position or end-market demand"
        )
    # Always add at least 2 substantive operational risks
    if industry and sector:
        business_risks.append(
            f"Competitive disruption: the {industry} landscape within {sector} faces rapid "
            f"technological change and new-entrant pressure — incumbents must continuously "
            f"innovate to maintain market share and pricing power"
        )
    # Add market structure risk
    business_risks.append(
        "Execution and governance: strategic missteps, leadership transitions, regulatory changes, "
        "or supply chain disruptions can materially impact financial performance — monitoring "
        "management commentary and proxy filings provides early warning signals"
    )

    strengths_parts: list[str] = []
    if mc and mc >= 1e12:
        strengths_parts.append("Very large scale provides capital and distribution advantages")
    if rev and rev >= 1e11:
        strengths_parts.append("high absolute revenue base supports sustained reinvestment")
    if isinstance(rev_growth, (int, float)) and rev_growth > 0:
        strengths_parts.append(f"positive revenue momentum ({rev_growth * 100:+.1f}% YoY)")
    strengths_vs = "; ".join(strengths_parts) if strengths_parts else (
        "Financial scale and market presence appear to be the main relative strengths in available data"
    )

    weaker_parts: list[str] = []
    pe_trailing = yf_info.get("pe_trailing")
    # Use sector/industry context where available, not just valuation
    if sector:
        weaker_parts.append(f"competitive dynamics within the {sector} sector may pressure market share or pricing")
    if industry:
        weaker_parts.append(f"industry-specific disruption risks in {industry} could challenge current positioning")
    if isinstance(pe_trailing, (int, float)) and pe_trailing > 30:
        weaker_parts.append("elevated valuation multiples leave less room for execution missteps")
    if isinstance(beta, (int, float)) and beta > 1.2:
        weaker_parts.append("above-average share-price volatility may deter some institutional investors")
    if "other bets" in lower_desc:
        weaker_parts.append("non-core initiatives may dilute near-term margin focus")
    weaker_vs = "; ".join(weaker_parts) if weaker_parts else (
        "No clear structural weakness identified from available data."
    )

    # Try to extract CEO name from yfinance officers data
    ceo_name = ""
    raw_info_obj = yf_info.get("_raw_info")
    raw_info = raw_info_obj if isinstance(raw_info_obj, dict) else {}
    officers = yf_info.get("company_officers", []) or raw_info.get("companyOfficers", []) or []
    for officer in officers:
        if isinstance(officer, dict):
            title = (officer.get("title") or "").lower()
            if "chief executive" in title or "ceo" in title:
                ceo_name = officer.get("name", "")
                break

    if ceo_name:
        ceo_style = (
            f"CEO {ceo_name} leads the company. "
            "Leadership approach assessed from public filings and market data. "
            "A full qualitative assessment requires direct management commentary."
        )
    else:
        ceo_style = (
            "CEO information not available from current structured data sources. "
            "Investors should consult proxy statements and investor presentations for management assessment."
        )

    long_term_vision = (
        f"Based on available data, {ticker}'s long-term strategy centers on scaling core business lines "
        "and investing in growth adjacencies. "
        "For a complete strategic assessment, refer to the company's annual report and investor day materials."
    )

    client_types = (
        f"Based on available structured data, {ticker}'s customers span multiple end markets. "
        "Refer to the company's annual report (10-K) for detailed customer and geographic revenue breakdowns."
    )

    management_weaknesses = (
        f"Management governance risks for {ticker} could not be assessed from structured data alone. "
        "Investors should review proxy statements (DEF 14A) and governance ratings for a full evaluation."
    )

    investor_takeaway = (
        f"A balanced investment assessment for {ticker} requires weighing revenue growth momentum, "
        "valuation multiples, competitive positioning, and the durability of its business model. "
        "This deterministic overview provides baseline data; qualitative analysis requires additional research."
    )

    return {
        "company_profile": {
            "name": yf_info.get("name", ticker),
            "ticker": ticker,
            "sector": sector,
            "industry": industry,
            "country": yf_info.get("country"),
            "website": yf_info.get("website"),
            "employees": yf_info.get("employees"),
            "founded": None,
            "headquarters": yf_info.get("headquarters"),
        },
        "business_description": business_description,
        "revenue_model": revenue_model,
        "business_segments": business_segments,
        "growth_drivers": growth_drivers,
        "moats": moats,
        "key_kpis": key_kpis,
        "business_risks": business_risks,
        "key_financials": {
            "market_cap": mc,
            "market_cap_display": _format_currency(mc),
            "revenue": rev,
            "revenue_display": _format_currency(rev),
            "pe_ratio": yf_info.get("trailingPE"),
            "pe_forward": yf_info.get("forwardPE"),
            "dividend_yield": yf_info.get("dividendYield"),
            "beta": beta,
            "52w_high": yf_info.get("fiftyTwoWeekHigh"),
            "52w_low": yf_info.get("fiftyTwoWeekLow"),
        },
        "recent_developments": [],
        "competitive_position": f"Market position for {ticker} estimated from available sector ({sector or 'N/A'}) and industry ({industry or 'N/A'}) data. Refer to the company's 10-K for detailed competitive analysis.",
        "strengths_vs_competitors": strengths_vs,
        "weaker_areas_vs_competitors": weaker_vs,
        "client_types": client_types,
        "management_weaknesses": management_weaknesses,
        "investor_takeaway": investor_takeaway,
        "ceo_leadership_style": ceo_style,
        "long_term_vision": long_term_vision,
        "competitors": _build_fallback_competitors(ticker, yf_info),
        "company_claims": [],
    }


def _format_currency(value) -> Optional[str]:
    """Format a number into human-readable currency string."""
    if value is None:
        return None
    if abs(value) >= 1e12:
        return f"${value/1e12:.2f}T"
    if abs(value) >= 1e9:
        return f"${value/1e9:.1f}B"
    if abs(value) >= 1e6:
        return f"${value/1e6:.0f}M"
    return f"${value:,.0f}"


# ── Main public API ───────────────────────────────────────────────────────


async def get_company_overview(
    ticker: str,
    language: str = "en",
    ledger: Optional[Dict[str, Any]] = None,
    yahoo_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Get structured company overview — cached for 7 days.

    ⚠️ LANGUAGE SEPARATION:
      EN: LLM generates English content directly.
      JP: First fetches/caches EN overview, then translates via separate LLM call.
      NEVER generates mixed-language content in a single LLM call.

    Args:
        ticker: Stock symbol (e.g. "AAPL", "NVDA")
        language: "en" (English) or "jp" (Japanese)

    Returns:
        Dict with keys: company_profile, business_description,
        key_financials, recent_developments, competitive_position
    """
    ticker = ticker.upper()
    lang = language.lower()
    if lang not in ("en", "jp"):
        logger.warning(f"Unsupported language '{language}', defaulting to 'en'")
        lang = "en"

    use_cache = not ledger and not yahoo_snapshot
    # ── Check cache ─────────────────────────────────────────────────
    if use_cache:
        cached = _overview_cache_get(ticker, lang)
        if cached is not None:
            return cached

    logger.info(f"Fetching company overview for {ticker}/{lang}...")

    # ── Phase 1: Fetch raw data ─────────────────────────────────────
    yf_info = yahoo_snapshot or await _fetch_yahoo_info(ticker)
    if _needs_rich_profile_fetch(yf_info):
        try:
            rich_profile = await _fetch_yahoo_info(ticker)
            yf_info = _merge_rich_profile_snapshot(yf_info, rich_profile)
            logger.info(f"[{ticker}] Company Overview profile enriched from yfinance identity fields")
        except Exception as e:
            logger.warning(f"[{ticker}] Company Overview rich profile fetch failed: {e}")
    tavily_results = await _search_tavily_overview(ticker, yf_info)

    if lang == "en":
        # ── Phase 2a: LLM synthesis (EN) ────────────────────────────
        overview = _synthesize_overview_en(ticker, yf_info, tavily_results)
        _apply_key_financials_provenance(overview, ticker, yf_info, ledger)
    else:
        # ── Phase 2b: EN → JP translation (two-step) ─────────────────
        # Step 1: Get English overview (from cache or generate)
        en_cached = _overview_cache_get(ticker, "en")
        if en_cached is None:
            en_cached = _synthesize_overview_en(ticker, yf_info, tavily_results)
            _apply_key_financials_provenance(en_cached, ticker, yf_info, ledger)
            if use_cache:
                _overview_cache_set(ticker, "en", en_cached)

        # Step 2: Translate EN → JP via separate LLM call
        logger.info(f"Translating overview EN→JP for {ticker}...")
        overview = _translate_overview_to_jp(en_cached, ticker)
        _apply_key_financials_provenance(overview, ticker, yf_info, ledger)

    _apply_verified_leadership_transition(overview, tavily_results, ticker=ticker)

    # ── Cache and return ────────────────────────────────────────────
    if use_cache:
        _overview_cache_set(ticker, lang, overview)
    return overview
