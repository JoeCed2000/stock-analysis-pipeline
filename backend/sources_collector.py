"""Data collection layer — yfinance, Finnhub, SEC EDGAR wrappers."""
import os
import json
import logging
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache layer — file-based JSON cache with TTL
# ---------------------------------------------------------------------------

CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_TTL_SECONDS = 3600  # 1 hour
CACHE_VERSION = 5  # bump to invalidate old cache entries (v5: quarterly normalization + period_tag + EPS consensus guard)
YF_CACHE_TTL = 600  # 10 min — yfinance data pushed by cron (refreshed every 2 min)


def _cache_path(ticker: str) -> Path:
    """Get cache file path for a ticker."""
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"{ticker.upper()}.json"


def _cache_get(ticker: str) -> Optional[Dict[str, Any]]:
    """Read from cache if still valid and version matches."""
    path = _cache_path(ticker)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            entry = json.load(f)
        # Version check — bump CACHE_VERSION to invalidate old entries
        if entry.get("version") != CACHE_VERSION:
            logger.info(f"Cache VERSION mismatch for {ticker}, ignoring")
            return None
        age = datetime.now(timezone.utc).timestamp() - entry.get("timestamp", 0)
        if age < CACHE_TTL_SECONDS:
            logger.info(f"Cache HIT for {ticker} (age: {age:.0f}s)")
            return entry["data"]
        logger.info(f"Cache EXPIRED for {ticker} (age: {age:.0f}s)")
    except Exception as e:
        logger.debug(f"Cache read error for {ticker}: {e}")
    return None


def _cache_get_stale(ticker: str) -> Optional[Dict[str, Any]]:
    """Read the cached snapshot ignoring TTL (version still enforced).

    Used by the anti-degradation guard: a stale-but-rich snapshot is a
    better reference than nothing when a fresh fetch came back degraded.
    """
    path = _cache_path(ticker)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            entry = json.load(f)
        if entry.get("version") != CACHE_VERSION:
            return None
        return entry["data"]
    except Exception:
        return None


def _financial_field_count(snapshot: Optional[Dict[str, Any]]) -> int:
    """Count non-null financial fields — the snapshot richness signal."""
    fin = (snapshot or {}).get("financials")
    if not isinstance(fin, dict):
        return 0
    return sum(1 for v in fin.values() if v is not None)


def _guard_against_degraded_snapshot(ticker: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the richer snapshot when a fresh fetch came back degraded.

    Partial yfinance failures (rate limits, transient API errors) leave the
    silent except blocks with None in most financial fields. Persisting that
    would poison the cache and feed client PDFs with missing
    fiscal_period_label / net_debt / estimates (observed on NVDA 2026-06-12:
    wrong fiscal title + inconsistent metrics in a served PDF). The cache
    timestamp is NOT refreshed when the previous snapshot is kept, so the
    next call retries a fresh fetch.
    """
    previous = _cache_get_stale(ticker)
    fresh_count = _financial_field_count(result)
    previous_count = _financial_field_count(previous)
    if previous is not None and fresh_count < previous_count * 0.7:
        logger.warning(
            "Yahoo snapshot for %s degraded (%d non-null financial fields vs %d cached) "
            "— keeping previous snapshot, not persisting the degraded fetch",
            ticker, fresh_count, previous_count,
        )
        return previous
    _cache_set(ticker, result)
    return result


def _cache_set(ticker: str, data: Dict[str, Any]) -> None:
    """Write data to cache with version stamp."""
    try:
        entry = {
            "version": CACHE_VERSION,
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "data": data,
        }
        with open(_cache_path(ticker), "w") as f:
            json.dump(entry, f, default=_json_serializable)
        logger.info(f"Cache SET for {ticker}")
    except Exception as e:
        logger.warning(f"Cache SET failed for {ticker}: {e}")


def _json_serializable(obj: Any) -> Any:
    """Convert numpy types to native Python for JSON serialization."""
    try:
        import numpy as np
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except ImportError:
        pass
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

# ---------------------------------------------------------------------------
# YFinance cache — populated by cron (fill_dossiers.py) every 2 min
# Separate from main stock cache to avoid overwriting Finnhub-merged data
# ---------------------------------------------------------------------------

def _cache_path_yf(ticker: str) -> Path:
    """Get yfinance-only cache file path for a ticker."""
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"{ticker.upper()}_yf.json"

def _cache_get_yf(ticker: str) -> Optional[Dict[str, Any]]:
    """Read yfinance-only data pushed by cron. Short TTL (10 min)."""
    path = _cache_path_yf(ticker)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            entry = json.load(f)
        age = datetime.now(timezone.utc).timestamp() - entry.get("timestamp", 0)
        if age < YF_CACHE_TTL:
            logger.info(f"YF Cache HIT for {ticker} (age: {age:.0f}s)")
            return entry.get("data") if "data" in entry else entry
        logger.info(f"YF Cache EXPIRED for {ticker} (age: {age:.0f}s)")
    except Exception as e:
        logger.warning(f"YF Cache read error for {ticker}: {e}")
    return None

# ---------------------------------------------------------------------------
# Unified stock data — Finnhub → Twelve Data → yfinance
# ---------------------------------------------------------------------------

def _pct_to_decimal(val) -> Optional[float]:
    """Finnhub returns percentages as whole numbers (12.76 = 12.76%).
    Convert to decimal (0.1276) for consistency with yfinance."""
    if val is None:
        return None
    try:
        return float(val) / 100.0
    except (TypeError, ValueError):
        return None


def get_stock_data(ticker: str, force_refresh: bool = False) -> Dict[str, Any]:
    """Fetch fundamental + price data. Multi-source chain:
    1. Finnhub (US equities, 60 calls/min, free) — price, sector, market cap
    2. Twelve Data (international, 800 calls/day, free — needs TWELVEDATA_API_KEY)
    3. EODHD (global, 20 calls/day, free — needs EODHD_API_KEY) — price + 52w, EU fallback
    4. yfinance — DEEP financials (PE, revenue, net income, FCF) merged in
    Uses file-based cache (TTL 1h) to minimize API calls.
    Set force_refresh=True to bypass cache and force re-collection."""
    # Check cache first (unless force_refresh)
    if not force_refresh:
        cached = _cache_get(ticker)
        if cached is not None:
            # Even with cache hit, enrich with any yfinance data pushed by cron
            # (e.g., PE ratio, revenue, net income that Finnhub didn't provide,
            #  and which yfinance live fetch can't get because Render IP is blocked)
            yf_cached = _cache_get_yf(ticker)
            if yf_cached:
                yf_fin = yf_cached.get("financials", {})
                fin_cached = cached.get("financials", {})
                enriched = False
                for key in ["revenue_quarterly", "revenue_annual", "net_income",
                           "free_cash_flow", "net_debt", "revenue_estimate", "eps_estimate"]:
                    if fin_cached.get(key) is None and yf_fin.get(key) is not None:
                        fin_cached[key] = yf_fin[key]
                        enriched = True
                for key in ["pe_current", "pe_forward", "peg_ratio", "beta",
                           "52w_high", "52w_low"]:
                    if cached.get(key) is None and yf_cached.get(key) is not None:
                        cached[key] = yf_cached[key]
                        enriched = True
                if enriched:
                    logger.info(f"Cache enriched from yfinance cron data for {ticker}")
                    _cache_set(ticker, cached)  # persist enrichment
            cached["_source"] = "cache"
            return cached

    result = None
    _source = None

    # Try Finnhub (US only) — best for price/sector/name
    result = _get_stock_data_finnhub(ticker)
    if result is not None:
        _source = "finnhub"
    
    if result is None:
        # Try Twelve Data (international)
        result = _get_stock_data_twelvedata(ticker)
        if result is not None:
            _source = "twelvedata"

    if result is None:
        # Try EODHD (global coverage, richer fundamentals than Twelve Data)
        result = _get_stock_data_eodhd(ticker)
        if result is not None:
            _source = "eodhd"
    
    if result is None:
        # Last resort: pure yfinance
        logger.info(f"Finnhub/Twelve Data unavailable for {ticker}, falling back to yfinance")
        try:
            result = get_yahoo_data(ticker)
            _source = "yfinance"
            result["_source"] = _source
            _cache_set(ticker, result)
            return result
        except Exception as e:
            logger.error(f"All sources failed for {ticker}: {e}")
            raise RuntimeError(
                f"No data source available for {ticker}. "
                f"US stocks: set FINNHUB_API_KEY. "
                f"International: set TWELVEDATA_API_KEY (free at twelvedata.com) "
                f"or EODHD_API_KEY (free at eodhd.com). "
                f"Or run analysis locally where yfinance works."
            )

    # Merge yfinance deep financials into Finnhub/TwelveData result
    # Finnhub free tier gives ratios (grossMarginTTM, etc.) but NOT absolute values
    # yfinance has Income Statement, Balance Sheet, Cash Flow
    # Optimization: skip live yfinance when cron cache has sufficient data,
    # and only fetch live when critical fields are truly missing.
    
    FINNHUB_MISSING_FINANCIALS = ["revenue_quarterly", "revenue_annual", "net_income", "free_cash_flow"]
    FINNHUB_MISSING_VALUATION = ["pe_current", "pe_forward", "peg_ratio"]
    
    _needs_enrichment = any(
        result["financials"].get(k) is None for k in FINNHUB_MISSING_FINANCIALS
    ) or any(result.get(k) is None for k in FINNHUB_MISSING_VALUATION)
    
    if _needs_enrichment:
        try:
            # Step 1: Try cron-pushed cache (fast, no network) 
            yf_cached = _cache_get_yf(ticker)
            if yf_cached:
                logger.info(f"Enriching from yfinance cron cache for {ticker}")
                yf_fin_cached = yf_cached.get("financials", {})
                for key in FINNHUB_MISSING_FINANCIALS + ["revenue_estimate", "eps_estimate", "net_debt"]:
                    if result["financials"].get(key) is None and yf_fin_cached.get(key) is not None:
                        result["financials"][key] = yf_fin_cached[key]
                for key in FINNHUB_MISSING_VALUATION + ["expected_growth", "beta", "52w_high", "52w_low"]:
                    if result.get(key) is None and yf_cached.get(key) is not None:
                        result[key] = yf_cached[key]
            
            # Step 2: Recheck — still missing data? Try live yfinance 
            _still_needs = any(
                result["financials"].get(k) is None for k in FINNHUB_MISSING_FINANCIALS
            )
            if _still_needs:
                logger.info(f"Cron cache insufficient for {ticker}, trying live yfinance")
                yf_data = get_yahoo_data(ticker)
                if yf_data:
                    yf_fin = yf_data.get("financials", {})
                    for key in FINNHUB_MISSING_FINANCIALS + ["revenue_estimate", "eps_estimate"]:
                        if result["financials"].get(key) is None:
                            result["financials"][key] = yf_fin.get(key)
                    for key in FINNHUB_MISSING_VALUATION:
                        if result.get(key) is None and yf_data.get(key) is not None:
                            result[key] = yf_data[key]
                    logger.info(f"YFinance live enrichment done for {ticker}")
        except Exception as e:
            logger.warning(f"YFinance merge failed for {ticker} — using available data: {e}")

    _cache_set(ticker, result)
    result["_source"] = _source or "cache"
    return result


def _get_stock_data_finnhub(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch stock data from Finnhub. Returns None if unavailable."""
    api_key = os.getenv("FINNHUB_API_KEY", "")
    if not api_key:
        return None

    from backend.http_client import http
    import time as _time_module

    def _fh(path: str, retries: int = 3) -> Optional[Dict]:
        """Fetch Finnhub endpoint with retry on 429/timeout. Token passed via params, not URL."""
        from urllib.parse import urlparse, parse_qs, urlencode
        parsed = urlparse(f"https://finnhub.io/api/v1{path}")
        # Merge existing query params with token (token never in URL)
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        params["token"] = api_key
        url = f"https://finnhub.io{parsed.path}"
        last_error = None
        for attempt in range(retries + 1):
            try:
                resp = http.get(
                    url,
                    params=params,
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if "error" in data:
                        return None
                    return data
                elif resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                    logger.warning(f"Finnhub 429 — attempt {attempt+1}/{retries+1}, waiting {retry_after}s")
                    if attempt < retries:
                        _time_module.sleep(retry_after)
                        continue
                else:
                    if attempt < retries:
                        _time_module.sleep(2 ** attempt)
                        continue
            except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError):
                if attempt < retries:
                    _time_module.sleep(2 ** attempt)
                    continue
            except Exception as e:
                last_error = e
                if attempt < retries:
                    _time_module.sleep(1)
                    continue
        if last_error:
            logger.warning(f"Finnhub request failed after {retries+1} attempts: {last_error}")
        return None

    # Profile
    profile = _fh(f"/stock/profile2?symbol={ticker}")
    if not profile:
        logger.error(f"Finnhub profile2 failed for {ticker} — API key valid? Network ok?")
        return None

    # Quote
    quote = _fh(f"/quote?symbol={ticker}") or {}
    # Metrics
    metrics_raw = _fh(f"/stock/metric?symbol={ticker}&metric=all")
    metrics = metrics_raw.get("metric", {}) if metrics_raw else {}

    # Build result with same structure as get_yahoo_data()
    price = quote.get("c")
    prev_close = quote.get("pc")
    currency = profile.get("currency", "USD")

    result = {
        "ticker": ticker,
        "company_name": profile.get("name") or ticker,
        "sector": profile.get("finnhubIndustry"),
        "industry": profile.get("finnhubIndustry"),  # Finnhub has finnhubIndustry only
        "market_cap": (profile.get("marketCapitalization") or 0) * 1e6,  # Finnhub gives in millions
        "price": price,
        "prev_close": prev_close,
        "currency": currency,
        "financials": {
            "revenue_quarterly": None,
            "revenue_yoy_growth": _pct_to_decimal(metrics.get("revenueGrowthQuarterlyYoy")),
            "revenue_annual": None,
            "revenue_annual_growth": _pct_to_decimal(metrics.get("revenueGrowthTTMYoy")),
            "gross_margin": _pct_to_decimal(metrics.get("grossMarginTTM")),
            "operating_margin": _pct_to_decimal(metrics.get("operatingMarginTTM")),
            "net_income": None,
            "free_cash_flow": None,
            "net_debt": None,
            "guidance_official": _pct_to_decimal(metrics.get("revenueGrowthTTMYoy")),
        },
        "pe_current": metrics.get("peTTM") or metrics.get("peBasicExclExtraTTM"),
        "pe_forward": metrics.get("forwardPE"),
        "peg_ratio": metrics.get("pegTTM") or metrics.get("forwardPEG"),
        "expected_growth": metrics.get("epsGrowthTTMYoy"),
        "beta": metrics.get("beta"),
        "52w_high": metrics.get("52WeekHigh"),
        "52w_low": metrics.get("52WeekLow"),
        "description": "",  # Finnhub free tier doesn't provide business summary
    }

    logger.info(f"Finnhub OK for {ticker}: {profile.get('name')} — ${price}")
    return result


# ---------------------------------------------------------------------------
# Twelve Data wrapper (international fallback)
# ---------------------------------------------------------------------------

def _get_stock_data_twelvedata(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch stock data from Twelve Data. Returns None if unavailable.
    Free tier: 800 calls/day, global coverage including EU exchanges (MC.PA, ASML, etc.)."""
    api_key = os.getenv("TWELVEDATA_API_KEY", "")
    if not api_key:
        return None

    from backend.http_client import http

    try:
        # Quote endpoint (real-time price)
        resp = http.get(
            "https://api.twelvedata.com/quote",
            params={"symbol": ticker, "apikey": api_key},
            timeout=10
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if "code" in data and data.get("code") != 200:  # Twelve Data error codes
            logger.warning(f"Twelve Data error for {ticker}: {data.get('message', 'unknown')}")
            return None

        price = float(data.get("close")) if data.get("close") else None
        prev_close = float(data.get("previous_close")) if data.get("previous_close") else None
        currency = data.get("currency", "EUR" if "." in ticker else "USD")
        name = data.get("name") or ticker
        change_pct = float(data.get("percent_change")) if data.get("percent_change") else None
        high_52w = float(data.get("fifty_two_week", {}).get("high")) if isinstance(data.get("fifty_two_week"), dict) else None
        low_52w = float(data.get("fifty_two_week", {}).get("low")) if isinstance(data.get("fifty_two_week"), dict) else None

        result = {
            "ticker": ticker,
            "company_name": name,
            "sector": None,  # Twelve Data basic plan doesn't include sector
            "industry": None,
            "market_cap": None,  # Requires upgrade
            "price": price,
            "prev_close": prev_close,
            "currency": currency,
            "financials": {
                "revenue_quarterly": None,
                "revenue_yoy_growth": None,  # percent_change is PRICE change, not revenue growth
                "revenue_annual": None,
                "revenue_annual_growth": None,
                "gross_margin": None,
                "operating_margin": None,
                "net_income": None,
                "free_cash_flow": None,
                "net_debt": None,
                "guidance_official": None,
            },
            "pe_current": None,
            "pe_forward": None,
            "peg_ratio": None,
            "expected_growth": None,
            "beta": None,
            "52w_high": high_52w,
            "52w_low": low_52w,
            "description": "",
        }

        logger.info(f"Twelve Data OK for {ticker}: {name} — {price} {currency}")
        return result

    except Exception as e:
        logger.warning(f"Twelve Data failed for {ticker}: {e}")
        return None


# ---------------------------------------------------------------------------
# EODHD wrapper (international fallback — global coverage, 20 req/day free)
# ---------------------------------------------------------------------------

def _get_stock_data_eodhd(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch price data from EODHD. Returns None if unavailable.
    Free tier: 20 req/day, global coverage. Price + 52w only (fundamentals = paid tier).
    Used as price fallback for EU tickers where yfinance is blocked on Render."""
    api_key = os.getenv("EODHD_API_KEY", "")
    if not api_key:
        return None

    from backend.http_client import http

    try:
        # Real-time endpoint (delayed, free tier) — gives current price
        rt_resp = http.get(
            f"https://eodhd.com/api/real-time/{ticker}",
            params={"api_token": api_key, "fmt": "json"},
            timeout=10
        )
        if rt_resp.status_code != 200:
            logger.warning(f"EODHD real-time HTTP {rt_resp.status_code} for {ticker}")
            return None
        rt_data = rt_resp.json()
        if not rt_data or "close" not in rt_data:
            logger.warning(f"EODHD real-time empty for {ticker}")
            return None

        price = rt_data.get("close")
        prev_close = rt_data.get("previousClose")
        change_pct = rt_data.get("change_p")

        # Try EOD endpoint for 52-week high/low (last 260 trading days ≈ 1 year)
        high_52w = None
        low_52w = None
        try:
            eod_resp = http.get(
                f"https://eodhd.com/api/eod/{ticker}",
                params={"api_token": api_key, "fmt": "json", "period": "d", "from": "2025-05-01"},
                timeout=8
            )
            if eod_resp.status_code == 200:
                eod_data = eod_resp.json()
                if eod_data and isinstance(eod_data, list) and len(eod_data) > 0:
                    closes = [d["close"] for d in eod_data if "close" in d]
                    if closes:
                        high_52w = max(closes)
                        low_52w = min(closes)
        except Exception as e:
            logger.debug(f"Fallback: {e}")  # 52w is nice-to-have, not critical

        result = {
            "ticker": ticker,
            "company_name": ticker,  # No name on free tier — will be enriched by yfinance later
            "sector": None,
            "industry": None,
            "market_cap": None,
            "price": price,
            "prev_close": prev_close,
            "currency": "EUR" if "." in ticker else "USD",  # best guess
            "financials": {
                "revenue_quarterly": None,
                "revenue_yoy_growth": None,
                "revenue_annual": None,
                "revenue_annual_growth": None,
                "gross_margin": None,
                "operating_margin": None,
                "net_income": None,
                "free_cash_flow": None,
                "net_debt": None,
                "guidance_official": None,
            },
            "pe_current": None,
            "pe_forward": None,
            "peg_ratio": None,
            "expected_growth": None,
            "beta": None,
            "52w_high": high_52w,
            "52w_low": low_52w,
            "description": "",
        }

        logger.info(f"EODHD OK for {ticker}: price={price} prev={prev_close} 52w=({low_52w},{high_52w})")
        return result

    except Exception as e:
        logger.warning(f"EODHD failed for {ticker}: {e}")
        return None


# ---------------------------------------------------------------------------
# YFinance wrapper (fallback)
# ---------------------------------------------------------------------------

def _load_yfinance():
    """Lazy-import yfinance — slow on first load."""
    import yfinance as yf
    return yf


# B17: short-TTL in-run Ticker reuse. yfinance memoizes fetched statements on
# the Ticker object, so reusing it within one workflow removes duplicate
# network fetches (get_yahoo_data + get_yahoo_data_for_quarter both creating
# fresh Tickers). TTL well below the 1h file cache — no extra staleness.
# Set SA_YF_TICKER_TTL=0 to disable.
_TICKER_CACHE: dict = {}


def _ticker_cache_ttl() -> float:
    import os
    try:
        return float(os.getenv("SA_YF_TICKER_TTL", "300"))
    except ValueError:
        return 300.0


def _yf_ticker_safe(ticker: str, timeout: int = 120):
    """Create yf.Ticker with timeout to prevent hangs on slow Yahoo responses.
    Default 120s — mega-caps (NVDA, AAPL) need >60s for full financial statements."""
    import concurrent.futures
    import time as _t

    ttl = _ticker_cache_ttl()
    if ttl > 0:
        hit = _TICKER_CACHE.get(ticker)
        if hit and _t.monotonic() - hit[0] <= ttl:
            return hit[1]

    def _create():
        yf = _load_yfinance()
        return yf.Ticker(ticker)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_create)
        try:
            obj = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.warning(f"yfinance Ticker({ticker}) timed out after {timeout}s")
            raise TimeoutError(f"yfinance Ticker({ticker}) timed out after {timeout}s")
    if ttl > 0:
        _TICKER_CACHE[ticker] = (_t.monotonic(), obj)
    return obj


def _fiscal_period_label(period_end, info: Dict[str, Any]) -> Optional[str]:
    """Map a quarter period-end date to the company's fiscal label, e.g. 'FY2027 Q1'.

    Uses yfinance info['lastFiscalYearEnd'] (epoch) for the fiscal year-end month.
    Companies with offset fiscal years (NVDA ends late Jan, AAPL late Sep) must
    not be labeled with calendar quarters.
    """
    try:
        from datetime import datetime as _dt
        fy_end_epoch = (info or {}).get("lastFiscalYearEnd")
        fy_end_month = _dt.fromtimestamp(fy_end_epoch).month if fy_end_epoch else 12
        month, year = period_end.month, period_end.year
        fiscal_year = year if month <= fy_end_month else year + 1
        fy_start_month = fy_end_month % 12 + 1
        quarter_num = ((month - fy_start_month) % 12) // 3 + 1
        return f"FY{fiscal_year} Q{quarter_num}"
    except Exception:
        return None


def _net_position(total_debt: Optional[float], cash_eq: Optional[float],
                  marketable: Optional[float], combined: Optional[float] = None):
    """Return (net_debt, cash_and_marketable_securities).

    Net Cash = Cash & Equivalents + Marketable Securities - Total Debt.
    net_debt keeps the existing sign convention: positive = leveraged, negative = net cash.
    `combined` is the pre-summed yfinance row 'Cash Cash Equivalents And Short Term Investments'.
    """
    cash_total = combined
    if cash_total is None and cash_eq is not None:
        cash_total = cash_eq + (marketable or 0)
    net_debt = total_debt - cash_total if (total_debt is not None and cash_total is not None) else None
    return net_debt, cash_total


def get_yahoo_data(ticker: str) -> Dict[str, Any]:
    """Fetch all available fundamental + price data from Yahoo Finance.
    Uses file-based cache (TTL 1h) to avoid rate-limits."""
    # Check cache first
    cached = _cache_get(ticker)
    if cached is not None:
        fin_cached = cached.get("financials", {}) if isinstance(cached.get("financials"), dict) else {}
        new_financial_fields = {
            "eps_actual",
            "eps_estimate",
            "eps_yoy",
            "revenue_estimate",
            "operating_income",
            "roic",
            "roe",
            "pe_forward",
            "backlog",
            "guidance",
            "segments",
        }
        if all(key in fin_cached for key in new_financial_fields):
            return cached

    try:
        yf = _load_yfinance()
        stock = _yf_ticker_safe(ticker)
        info = stock.info or {}
    except Exception:
        if cached is not None:
            return cached
        raise

    # Price data
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    prev_close = info.get("previousClose")
    currency = info.get("currency", "USD")

    # Financial statements
    try:
        income = stock.financials  # annual
        quarterly_income = stock.quarterly_financials
        balance = stock.balance_sheet
        cashflow = stock.cashflow
    except Exception:
        income = None
        quarterly_income = None
        balance = None
        cashflow = None
    period_tag: Optional[str] = None

    # Build financial data
    financials = {
        "revenue_quarterly": None,
        "revenue_yoy_growth": None,
        "revenue_annual": None,
        "revenue_annual_growth": None,
        "eps_actual": None,
        "eps_estimate": None,
        "eps_yoy": None,
        "revenue_estimate": None,
        "gross_margin": None,
        "operating_margin": None,
        "operating_income": None,
        "net_income": None,
        "free_cash_flow": None,
        "operating_cash_flow": None,
        "capex": None,
        "net_debt": None,
        "roic": None,
        "roe": None,
        "pe_forward": None,
        "backlog": None,
        "guidance": None,
        "segments": {},
        "guidance_official": None,
        # v2.5 — new deep-dive fields
        "gross_profit": None,
        "opex": None,
        "rotce": None,
        "roa": None,
        "total_assets": None,
        "equity": None,
        "buybacks": None,
        "dividends": None,
    }

    if quarterly_income is not None and not quarterly_income.empty:
        try:
            latest_q = quarterly_income.columns[0]
            # Derive period tag like 'YYYYQ#' from pandas Period/Timestamp
            try:
                dt = latest_q.to_pydatetime() if hasattr(latest_q, 'to_pydatetime') else latest_q
                q_num = (dt.month - 1) // 3 + 1
                period_tag = f"{dt.year}Q{q_num}"
                financials["period_end_date"] = dt.date().isoformat() if hasattr(dt, 'date') else str(dt)[:10]
                financials["fiscal_period_label"] = _fiscal_period_label(dt, info)
            except Exception:
                period_tag = None
            financials["revenue_quarterly"] = _safe_float(
                quarterly_income.loc["Total Revenue", latest_q] if "Total Revenue" in quarterly_income.index else None
            )
            # YoY growth: compare to same quarter last year if available
            if len(quarterly_income.columns) >= 5:
                prev_year_q = quarterly_income.columns[4]
                prev_rev = _safe_float(
                    quarterly_income.loc["Total Revenue", prev_year_q] if "Total Revenue" in quarterly_income.index else None
                )
                curr_rev = financials["revenue_quarterly"]
                if prev_rev and curr_rev and prev_rev > 0:
                    financials["revenue_yoy_growth"] = round((curr_rev - prev_rev) / prev_rev, 4)

            # EPS extraction from quarterly income
            if "Diluted EPS" in quarterly_income.index:
                financials["eps_actual"] = _safe_float(quarterly_income.loc["Diluted EPS", latest_q])
                if len(quarterly_income.columns) >= 5:
                    prev_year_q = quarterly_income.columns[4]
                    prev_eps = _safe_float(quarterly_income.loc["Diluted EPS", prev_year_q])
                    curr_eps = financials["eps_actual"]
                    if prev_eps and curr_eps and prev_eps != 0:
                        financials["eps_yoy"] = round((curr_eps - prev_eps) / abs(prev_eps), 4)

            # Net income — use QUARTERLY, not annual
            if "Net Income" in quarterly_income.index:
                ni_q = _safe_float(quarterly_income.loc["Net Income", latest_q])
                if ni_q is not None:
                    financials["net_income"] = ni_q

            operating_income = None
            if "Operating Income" in quarterly_income.index:
                operating_income = _safe_float(quarterly_income.loc["Operating Income", latest_q])
                financials["operating_income"] = operating_income

            if "Gross Profit" in quarterly_income.index:
                gp = _safe_float(quarterly_income.loc["Gross Profit", latest_q])
                rev = financials.get("revenue_quarterly")
                if gp and rev and rev > 0:
                    financials["gross_margin"] = round(gp / rev, 4)

            rev = financials.get("revenue_quarterly")
            if operating_income and rev and rev > 0:
                financials["operating_margin"] = round(operating_income / rev, 4)
        except Exception as e:
            logger.warning(f"Quarterly income extraction failed for {ticker}: {e}")

    if income is not None and not income.empty:
        try:
            latest_year = income.columns[0]
            financials["revenue_annual"] = _safe_float(
                income.loc["Total Revenue", latest_year] if "Total Revenue" in income.index else None
            )
            financials["net_income_annual"] = _safe_float(
                income.loc["Net Income", latest_year] if "Net Income" in income.index else None
            )
            # Annual growth
            if len(income.columns) >= 2:
                prev_year = income.columns[1]
                prev_rev = _safe_float(
                    income.loc["Total Revenue", prev_year] if "Total Revenue" in income.index else None
                )
                curr_rev = financials["revenue_annual"]
                if prev_rev and curr_rev and prev_rev > 0:
                    financials["revenue_annual_growth"] = round((curr_rev - prev_rev) / prev_rev, 4)
        except Exception as e:
            logger.warning(f"Annual income extraction failed for {ticker}: {e}")

    if cashflow is not None and not cashflow.empty:
        try:
            latest = cashflow.columns[0]
            fcf = _safe_float(
                cashflow.loc["Free Cash Flow", latest] if "Free Cash Flow" in cashflow.index else None
            )
            financials["free_cash_flow"] = fcf
            ocf = _safe_float(
                cashflow.loc["Operating Cash Flow", latest] if "Operating Cash Flow" in cashflow.index else None
            )
            financials["operating_cash_flow"] = ocf
            capex_val = _safe_float(
                cashflow.loc["Capital Expenditure", latest] if "Capital Expenditure" in cashflow.index else None
            )
            financials["capex"] = abs(capex_val) if capex_val is not None else None
            # Buybacks & dividends (v2.5)
            financials["buybacks"] = _safe_float(
                cashflow.loc["Repurchase Of Capital Stock", latest] if "Repurchase Of Capital Stock" in cashflow.index else None
            )
            financials["dividends"] = _safe_float(
                cashflow.loc["Cash Dividends Paid", latest] if "Cash Dividends Paid" in cashflow.index else None
            )
        except Exception as e:
            logger.warning(f"Cashflow extraction failed for {ticker}: {e}")

    if quarterly_income is not None and not quarterly_income.empty:
        try:
            # Try latest quarter first, fall back to earlier quarters if NaN
            gross_profit = None
            opex_val = None
            for col_idx in range(min(4, len(quarterly_income.columns))):
                q_col = quarterly_income.columns[col_idx]
                gp = _safe_float(
                    quarterly_income.loc["Gross Profit", q_col] if "Gross Profit" in quarterly_income.index else None
                )
                te = _safe_float(
                    quarterly_income.loc["Total Expenses", q_col] if "Total Expenses" in quarterly_income.index else None
                )
                if gp is not None or te is not None:
                    gross_profit = gross_profit or gp
                    opex_val = opex_val or te
                    break
                # Fallback: R&D + SG&A
                rd = _safe_float(quarterly_income.loc["Research And Development", q_col] if "Research And Development" in quarterly_income.index else 0) or 0
                sga = _safe_float(quarterly_income.loc["Selling General And Administration", q_col] if "Selling General And Administration" in quarterly_income.index else 0) or 0
                if rd or sga:
                    opex_val = opex_val or (rd + sga)
                    break
            financials["gross_profit"] = gross_profit
            financials["opex"] = opex_val
        except Exception as e:
            logger.debug(f"Fallback: {e}")

    if balance is not None and not balance.empty:
        try:
            latest = balance.columns[0]
            total_debt = _safe_float(
                balance.loc["Total Debt", latest] if "Total Debt" in balance.index else None
            )
            cash_eq = _safe_float(
                balance.loc["Cash And Cash Equivalents", latest] if "Cash And Cash Equivalents" in balance.index else None
            )
            marketable = _safe_float(
                balance.loc["Other Short Term Investments", latest] if "Other Short Term Investments" in balance.index else None
            )
            combined_cash = _safe_float(
                balance.loc["Cash Cash Equivalents And Short Term Investments", latest]
                if "Cash Cash Equivalents And Short Term Investments" in balance.index else None
            )
            # Net Cash = Cash & Equivalents + Marketable Securities - Total Debt
            financials["net_debt"], financials["cash_and_marketable_securities"] = _net_position(
                total_debt, cash_eq, marketable, combined_cash
            )
            # Legacy value (cash-equivalents only) kept for the ROIC invested-capital
            # proxy below, so the net-debt correction does not silently change ROIC.
            legacy_net_debt = total_debt - cash_eq if (total_debt is not None and cash_eq is not None) else None
            # Total assets & equity (v2.5)
            total_assets = _safe_float(
                balance.loc["Total Assets", latest] if "Total Assets" in balance.index else None
            )
            financials["total_assets"] = total_assets
            equity = _safe_float(
                balance.loc["Stockholders Equity", latest] if "Stockholders Equity" in balance.index else None
            )
            financials["equity"] = equity
            # ROTCE = NI / (Total Assets - Goodwill - Intangibles - Total Liabilities)
            goodwill = _safe_float(
                balance.loc["Goodwill And Other Intangible Assets", latest] if "Goodwill And Other Intangible Assets" in balance.index else None
            ) or 0
            total_liab = _safe_float(
                balance.loc["Total Liabilities Net Minority Interest", latest] if "Total Liabilities Net Minority Interest" in balance.index else None
            )
            ni = financials.get("net_income")
            if ni and total_assets and total_liab is not None:
                tangible_equity = total_assets - goodwill - total_liab
                if tangible_equity and tangible_equity > 0:
                    financials["rotce"] = round(ni / tangible_equity, 4)

            eq = _safe_float(
                balance.loc["Total Equity Gross Minority Interest", latest]
                if "Total Equity Gross Minority Interest" in balance.index
                else financials.get("equity")
            )
            if eq is not None:
                financials["equity"] = eq
            if ni and eq and eq > 0:
                financials["roe"] = round(ni / eq, 4)

            ta = _safe_float(
                balance.loc["Total Assets", latest] if "Total Assets" in balance.index else financials.get("total_assets")
            )
            if ta is not None:
                financials["total_assets"] = ta
            if ni and ta and ta > 0:
                financials["roa"] = round(ni / ta, 4)

            oi = financials.get("operating_income")
            total_debt_val = legacy_net_debt if legacy_net_debt is not None else financials.get("net_debt")
            if oi and eq and total_debt_val is not None:
                invested = eq + abs(total_debt_val)
                if invested > 0:
                    financials["roic"] = round(oi / invested, 4)
        except Exception as e:
            logger.debug(f"Fallback: {e}")

    # ROA from info (v2.5) — fallback to calculation if available
    if financials["roa"] is None:
        financials["roa"] = info.get("returnOnAssets")

    # Margins from info
    if financials["gross_margin"] is None:
        financials["gross_margin"] = info.get("grossMargins")
    if financials["operating_margin"] is None:
        financials["operating_margin"] = info.get("operatingMargins")

    # EPS growth rate (NOT revenue guidance — revenue guidance comes from press release)
    financials["eps_growth_quarterly"] = info.get("earningsQuarterlyGrowth")

    # EPS consensus for the REPORTED quarter — use earnings_history, NOT forwardEps/4
    eps_consensus = None
    consensus_provider = None
    try:
        eh = stock.earnings_history
        if eh is not None and not eh.empty:
            # Most recent row = latest reported quarter; epsEstimate = consensus AT THAT TIME
            latest = eh.iloc[-1]
            eps_consensus = float(latest["epsEstimate"])
            consensus_provider = "yfinance earnings_history (consensus at quarter close)"
            logger.info(f"EPS consensus from earnings_history: {eps_consensus}")
    except Exception as e:
        logger.warning(f"earnings_history EPS estimate unavailable: {e}")
    # Fallback: earnings_estimate 0q (current quarter consensus) — less precise match
    if eps_consensus is None:
        try:
            ee = stock.earnings_estimate
            if ee is not None and not ee.empty and "0q" in ee.index:
                eps_consensus = float(ee.loc["0q", "avg"])
                consensus_provider = "yfinance earnings_estimate 0q (current quarter consensus)"
        except Exception as e:
            logger.warning(f"earnings_estimate fallback failed: {e}")
    # Last resort: earnings_dates latest row EPS Estimate
    if eps_consensus is None:
        try:
            ed = stock.earnings_dates
            if ed is not None and not ed.empty:
                eps_consensus = float(ed.iloc[0]["EPS Estimate"])
                consensus_provider = "yfinance earnings_dates (next quarter consensus, weak proxy)"
        except Exception as e:
            logger.warning(f"earnings_dates fallback failed: {e}")
    financials["eps_estimate"] = eps_consensus
    financials["eps_consensus"] = eps_consensus
    financials["estimate_period_tag"] = period_tag
    financials["consensus_provider"] = consensus_provider or "yfinance via Yahoo"
    financials["consensus_as_of"] = _today_str()
    # Guard: if estimate far above actual, flag it for review
    if eps_consensus is not None:
        try:
            ea = financials.get("eps_actual")
            if ea is not None and ea > 0 and eps_consensus > (ea * 1.5):
                financials["eps_estimate_flag"] = "OUTLIER_HIGH"
            else:
                financials["eps_estimate_flag"] = None
        except Exception:
            financials["eps_estimate_flag"] = None
    else:
        financials["eps_estimate_flag"] = None
    # Override eps_actual with adjusted EPS from earnings_history (matches analyst consensus metric)
    # GAAP diluted EPS from income statement often differs ($1.76 vs $1.62 for NVDA Q1 2026)
    try:
        eh = stock.earnings_history
        if eh is not None and not eh.empty:
            latest = eh.iloc[-1]
            adj_eps = float(latest["epsActual"])
            if adj_eps is not None and adj_eps > 0:
                gaap_eps = financials.get("eps_actual")
                financials["eps_actual_gaap"] = gaap_eps  # preserve GAAP for reference
                financials["eps_actual"] = adj_eps
                financials["eps_actual_source"] = "yfinance earnings_history (adjusted, matches consensus)"
                # B14: GAAP-based YoY is not comparable to the adjusted actual.
                # Show YoY only on a same-basis pair; otherwise leave undisclosed.
                financials["eps_yoy_gaap"] = financials.get("eps_yoy")
                prior_adj = None
                if len(eh) >= 5:
                    try:
                        prior_adj = float(eh.iloc[-5]["epsActual"])
                    except (TypeError, ValueError, KeyError, IndexError):
                        prior_adj = None
                financials["eps_yoy"] = (
                    round((adj_eps - prior_adj) / abs(prior_adj), 4) if prior_adj else None
                )
                logger.info(f"eps_actual overridden: GAAP={gaap_eps} → adjusted={adj_eps}")
    except Exception as e:
        logger.debug(f"earnings_history epsActual override skipped: {e}")
    # NOTE: revenue_estimate intentionally NOT populated from stock.revenue_estimate.iloc[0]
    # That field returns forward consensus for NEXT quarter, not the estimate for the *reported* quarter.
    # Comparing actual Q1 revenue against forward Q2 consensus is misleading.
    # Revenue estimate is left as None; the mapper will show "—" in comparison tables.
    financials["revenue_estimate"] = None
    financials["pe_forward"] = info.get("forwardPE")
    # NOTE: guidance field is NOT filled from yfinance (earningsGrowth/revenueGrowth are rates, not guidance $)
    # Revenue guidance comes from the press release fetcher, applied via _apply_press_release_metrics
    financials["guidance"] = None
    financials["backlog"] = info.get("backlog")
    # Analyst consensus data
    financials["analyst_consensus"] = info.get("recommendationKey")  # "buy", "strong_buy", "hold"
    financials["analyst_target"] = info.get("targetMeanPrice")
    financials["analyst_count"] = info.get("numberOfAnalystOpinions")
    if info.get("sector") or info.get("industry"):
        financials["segments"] = {
            "sector": info.get("sector"),
            "industry": info.get("industry"),
        }

    result = {
        "ticker": ticker,
        "company_name": info.get("longName") or info.get("shortName") or ticker,
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": info.get("marketCap"),
        "price": price,
        "prev_close": prev_close,
        "currency": currency,
        "financials": financials,
        "pe_current": info.get("trailingPE"),
        "pe_forward": info.get("forwardPE"),
        "peg_ratio": info.get("pegRatio"),
        "expected_growth": info.get("earningsGrowth"),
        "beta": info.get("beta"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "description": info.get("longBusinessSummary"),
        "period_tag": period_tag,
        "analyst_consensus": info.get("recommendationKey"),
        "analyst_target": info.get("targetMeanPrice"),
        "analyst_count": info.get("numberOfAnalystOpinions"),
        "_raw_info": info,  # raw yfinance info dict (camelCase keys) for V2.7 valuation context
    }

    # Save to cache — unless this fetch is materially poorer than the
    # previous snapshot (anti-degradation guard).
    return _guard_against_degraded_snapshot(ticker, result)


# ── Quarter-aware data (v2.5) ──

def list_available_quarters(ticker: str) -> List[str]:
    """List available quarterly periods for a ticker from yfinance.
    Returns list like ['2026Q1', '2025Q4', '2025Q3', ...].
    Always available (yfinance has ~4 years of quarterly data)."""
    yf = _load_yfinance()
    stock = _yf_ticker_safe(ticker)
    try:
        qf = stock.quarterly_financials
        if qf is None or qf.empty:
            return []
        quarters = []
        for col in qf.columns:
            dt = col.to_pydatetime() if hasattr(col, 'to_pydatetime') else col
            q_num = (dt.month - 1) // 3 + 1
            quarters.append(f"{dt.year}Q{q_num}")
        return quarters
    except Exception:
        return []


def get_yahoo_data_for_quarter(ticker: str, quarter: str) -> Optional[Dict[str, Any]]:
    """Fetch yfinance data for a specific quarter (e.g. '2025Q4').
    Returns same structure as get_yahoo_data() but for the specified quarter.
    Falls back to get_yahoo_data() if quarter not found."""
    yf = _load_yfinance()
    stock = _yf_ticker_safe(ticker)

    try:
        qf = stock.quarterly_financials
        cf = stock.quarterly_cashflow
        bs = stock.quarterly_balance_sheet
        info = stock.info or {}
    except Exception:
        return None

    if qf is None or qf.empty:
        return None

    # Find the column matching the quarter
    import re as _re
    m = _re.match(r'(\d{4})Q([1-4])', quarter.upper())
    if not m:
        return None
    year, q = int(m.group(1)), int(m.group(2))
    target_month = (q - 1) * 3 + 1  # Q1→Jan(1), Q2→Apr(4), Q3→Jul(7), Q4→Oct(10)

    target_col = None
    for col in qf.columns:
        dt = col.to_pydatetime() if hasattr(col, 'to_pydatetime') else col
        if dt.year == year and ((dt.month - 1) // 3 + 1) == q:
            target_col = col
            break

    if target_col is None:
        # Fallback to latest
        logger.warning(f"Quarter {quarter} not found for {ticker}, using latest")
        return get_yahoo_data(ticker)

    # Find matching column in cashflow and balance sheet
    cf_col = target_col if cf is not None and not cf.empty and target_col in cf.columns else (cf.columns[0] if cf is not None and not cf.empty else None)
    bs_col = target_col if bs is not None and not bs.empty and target_col in bs.columns else (bs.columns[0] if bs is not None and not bs.empty else None)

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    prev_close = info.get("previousClose")
    currency = info.get("currency", "USD")

    financials: Dict[str, Any] = {
        "revenue_quarterly": None, "revenue_yoy_growth": None,
        "revenue_annual": None, "revenue_annual_growth": None,
        "eps_actual": None, "eps_estimate": None, "eps_yoy": None,
        "revenue_estimate": None,  # NOT stock.revenue_estimate — that is forward consensus, not quarter estimate
        "gross_margin": info.get("grossMargins"),
        "operating_margin": info.get("operatingMargins"),
        "net_income": None, "free_cash_flow": None,
        "operating_cash_flow": None, "capex": None, "net_debt": None,
        # NOTE: guidance not filled from yfinance — press release provides real guidance
        "gross_profit": None, "opex": None, "rotce": None, "roa": info.get("returnOnAssets"),
        "total_assets": None, "equity": None, "buybacks": None, "dividends": None,
    }

    try:
        _dt_col = target_col.to_pydatetime() if hasattr(target_col, 'to_pydatetime') else target_col
        financials["period_end_date"] = _dt_col.date().isoformat()
        financials["fiscal_period_label"] = _fiscal_period_label(_dt_col, info)
    except Exception:
        pass

    # Extract from quarterly income
    try:
        financials["revenue_quarterly"] = _safe_float(
            qf.loc["Total Revenue", target_col] if "Total Revenue" in qf.index else None)
        financials["net_income"] = _safe_float(
            qf.loc["Net Income", target_col] if "Net Income" in qf.index else None)
        financials["gross_profit"] = _safe_float(
            qf.loc["Gross Profit", target_col] if "Gross Profit" in qf.index else None)
        financials["opex"] = _safe_float(
            qf.loc["Total Expenses", target_col] if "Total Expenses" in qf.index else None)
        if financials["opex"] is None:
            rd = _safe_float(qf.loc["Research And Development", target_col] if "Research And Development" in qf.index else 0) or 0
            sga = _safe_float(qf.loc["Selling General And Administration", target_col] if "Selling General And Administration" in qf.index else 0) or 0
            financials["opex"] = rd + sga if (rd or sga) else None
        # YoY growth
        for i, col in enumerate(qf.columns):
            dt = col.to_pydatetime() if hasattr(col, 'to_pydatetime') else col
            if dt.year == year - 1 and ((dt.month - 1) // 3 + 1) == q:
                prev_rev = _safe_float(qf.loc["Total Revenue", col] if "Total Revenue" in qf.index else None)
                curr_rev = financials["revenue_quarterly"]
                if prev_rev and curr_rev and prev_rev > 0:
                    financials["revenue_yoy_growth"] = round((curr_rev - prev_rev) / prev_rev, 4)
                # EPS extraction
                if "Diluted EPS" in qf.index:
                    eps_curr = _safe_float(qf.loc["Diluted EPS", target_col])
                    financials["eps_actual"] = eps_curr
                    prev_eps = _safe_float(qf.loc["Diluted EPS", col])
                    if prev_eps and eps_curr and prev_eps != 0:
                        financials["eps_yoy"] = round((eps_curr - prev_eps) / abs(prev_eps), 4)
                break
    except Exception as e:
        logger.debug(f"Fallback: {e}")

    # Extract from cashflow
    if cf is not None and not cf.empty and cf_col is not None:
        try:
            financials["free_cash_flow"] = _safe_float(
                cf.loc["Free Cash Flow", cf_col] if "Free Cash Flow" in cf.index else None)
            financials["operating_cash_flow"] = _safe_float(
                cf.loc["Operating Cash Flow", cf_col] if "Operating Cash Flow" in cf.index else None)
            financials["capex"] = abs(_safe_float(
                cf.loc["Capital Expenditure", cf_col] if "Capital Expenditure" in cf.index else None)) if cf_col is not None else None
            financials["buybacks"] = _safe_float(
                cf.loc["Repurchase Of Capital Stock", cf_col] if "Repurchase Of Capital Stock" in cf.index else None)
            financials["dividends"] = _safe_float(
                cf.loc["Cash Dividends Paid", cf_col] if "Cash Dividends Paid" in cf.index else None)
        except Exception as e:
            logger.debug(f"Fallback: {e}")

    # Extract from balance sheet
    if bs is not None and not bs.empty and bs_col is not None:
        try:
            total_assets = _safe_float(
                bs.loc["Total Assets", bs_col] if "Total Assets" in bs.index else None)
            financials["total_assets"] = total_assets
            equity = _safe_float(
                bs.loc["Stockholders Equity", bs_col] if "Stockholders Equity" in bs.index else None)
            financials["equity"] = equity
            goodwill = _safe_float(
                bs.loc["Goodwill And Other Intangible Assets", bs_col] if "Goodwill And Other Intangible Assets" in bs.index else None) or 0
            total_liab = _safe_float(
                bs.loc["Total Liabilities Net Minority Interest", bs_col] if "Total Liabilities Net Minority Interest" in bs.index else None)
            ni = financials.get("net_income")
            if ni and total_assets and total_liab is not None:
                tangible_equity = total_assets - goodwill - total_liab
                if tangible_equity and tangible_equity > 0:
                    financials["rotce"] = round(ni / tangible_equity, 4)
            total_debt = _safe_float(
                bs.loc["Total Debt", bs_col] if "Total Debt" in bs.index else None)
            cash_eq = _safe_float(
                bs.loc["Cash And Cash Equivalents", bs_col] if "Cash And Cash Equivalents" in bs.index else None)
            marketable = _safe_float(
                bs.loc["Other Short Term Investments", bs_col] if "Other Short Term Investments" in bs.index else None)
            combined_cash = _safe_float(
                bs.loc["Cash Cash Equivalents And Short Term Investments", bs_col]
                if "Cash Cash Equivalents And Short Term Investments" in bs.index else None)
            # Net Cash = Cash & Equivalents + Marketable Securities - Total Debt
            financials["net_debt"], financials["cash_and_marketable_securities"] = _net_position(
                total_debt, cash_eq, marketable, combined_cash)
        except Exception as e:
            logger.debug(f"Fallback: {e}")

    # EPS consensus for the REPORTED quarter — match to earnings_history, NOT forwardEps/4
    eps_consensus = None
    try:
        eh = stock.earnings_history
        if eh is not None and not eh.empty:
            import pandas as _pd
            # Convert quarter string to a target date for matching
            q_dt = _pd.Timestamp(year=year, month=target_month, day=1)
            # Try exact match on earnings_history index
            for idx in eh.index:
                idx_dt = idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else _pd.Timestamp(idx)
                if idx_dt.year == q_dt.year and idx_dt.month == q_dt.month:
                    eps_consensus = float(eh.loc[idx, "epsEstimate"])
                    logger.info(f"EPS consensus for {quarter} from earnings_history: {eps_consensus}")
                    break
    except Exception as e:
        logger.warning(f"earnings_history EPS estimate for {quarter}: {e}")
    # Fallback: earnings_estimate 0q
    if eps_consensus is None:
        try:
            ee = stock.earnings_estimate
            if ee is not None and not ee.empty and "0q" in ee.index:
                eps_consensus = float(ee.loc["0q", "avg"])
                logger.info(f"EPS consensus fallback (earnings_estimate 0q): {eps_consensus}")
        except Exception as e:
            logger.warning(f"earnings_estimate fallback: {e}")
    # Last resort: forwardEps/4 (weak proxy)
    if eps_consensus is None:
        forward_eps = info.get("forwardEps")
        if forward_eps:
            eps_consensus = forward_eps / 4.0
            logger.warning(f"EPS consensus last-resort (forwardEps/4): {eps_consensus}")
    financials["eps_estimate"] = eps_consensus

    # Override eps_actual with adjusted EPS from earnings_history (matches analyst consensus metric)
    try:
        eh = stock.earnings_history
        if eh is not None and not eh.empty:
            q_dt = _pd.Timestamp(year=year, month=target_month, day=1)
            for idx in eh.index:
                idx_dt = idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else _pd.Timestamp(idx)
                if idx_dt.year == q_dt.year and idx_dt.month == q_dt.month:
                    adj_eps = float(eh.loc[idx, "epsActual"])
                    if adj_eps is not None and adj_eps > 0:
                        financials["eps_actual_gaap"] = financials.get("eps_actual")
                        financials["eps_actual"] = adj_eps
                        financials["eps_actual_source"] = "yfinance earnings_history (adjusted, matches consensus)"
                        logger.info(f"eps_actual overridden: GAAP={financials.get('eps_actual_gaap')} → adjusted={adj_eps}")
                    break
    except Exception as e:
        logger.debug(f"earnings_history epsActual override for {quarter}: {e}")

    result = {
        "ticker": ticker,
        "company_name": info.get("longName") or info.get("shortName") or ticker,
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": info.get("marketCap"),
        "price": price,
        "prev_close": prev_close,
        "currency": currency,
        "financials": financials,
        "pe_current": info.get("trailingPE"),
        "pe_forward": info.get("forwardPE"),
        "peg_ratio": info.get("pegRatio"),
        "expected_growth": info.get("earningsGrowth"),
        "beta": info.get("beta"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "description": info.get("longBusinessSummary"),
        "quarter": quarter,
        "period_tag": quarter,
    }

    return result


# ---------------------------------------------------------------------------
# Finnhub wrapper
# ---------------------------------------------------------------------------

def _get_finnhub_client():
    """Get Finnhub client with API key from env."""
    api_key = os.getenv("FINNHUB_API_KEY", "")
    if not api_key:
        raise ValueError("FINNHUB_API_KEY not set in environment")
    import finnhub
    return finnhub.Client(api_key=api_key)


def get_finnhub_data(ticker: str) -> Dict[str, Any]:
    """Fetch fundamentals + news from Finnhub."""
    try:
        client = _get_finnhub_client()
    except (ValueError, ImportError):
        logger.warning("Finnhub unavailable — skipping")
        return {"news": [], "recommendation": None, "peers": []}

    result: Dict[str, Any] = {"news": [], "recommendation": None, "peers": []}

    try:
        news = client.company_news(ticker, _from=_days_ago(30), to=_today_str())
        result["news"] = news[:10] if news else []
    except Exception as e:
        logger.warning(f"Finnhub news failed for {ticker}: {e}")

    try:
        result["recommendation"] = client.recommendation_trends(ticker)
    except Exception as e:
        logger.debug(f"Fallback: {e}")

    try:
        result["peers"] = client.company_peers(ticker)
    except Exception as e:
        logger.debug(f"Fallback: {e}")

    return result


# ---------------------------------------------------------------------------
# SEC EDGAR — lightweight fetch (just latest filing metadata)
# ---------------------------------------------------------------------------

def get_sec_filings(ticker: str, cik: Optional[str] = None) -> Dict[str, Any]:
    """Get latest SEC filings metadata for a ticker."""
    from backend.http_client import http  # local import for testability

    result: Dict[str, Any] = {"filings": [], "cik": cik}

    # Resolve CIK if not provided
    if not cik:
        try:
            resp = http.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers={"User-Agent": "StockAnalysisPipeline/1.0"},
                timeout=10
            )
            if resp.status_code == 200:
                companies = resp.json()
                ticker_upper = ticker.upper()
                for _, company in companies.items():
                    if company.get("ticker") == ticker_upper:
                        cik = str(company["cik_str"]).zfill(10)
                        result["cik"] = cik
                        break
        except Exception as e:
            logger.debug(f"Fallback: {e}")

    if cik:
        try:
            resp = http.get(
                f"https://data.sec.gov/submissions/CIK{cik}.json",
                headers={"User-Agent": "StockAnalysisPipeline/1.0"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                filings_raw = data.get("filings", {}).get("recent", {})
                forms = filings_raw.get("form", [])
                dates = filings_raw.get("filingDate", [])
                urls = filings_raw.get("primaryDocument", [])
                accessions = filings_raw.get("accessionNumber", [])
                descriptions = filings_raw.get("primaryDocDescription", [])

                for i in range(min(20, len(forms))):
                    if forms[i] in ("10-K", "10-Q", "8-K"):
                        doc = urls[i] if i < len(urls) else ""
                        acc = accessions[i] if i < len(accessions) else ""
                        acc_clean = acc.replace("-", "") if acc else ""
                        filing_url = (
                            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{doc}"
                            if (doc and acc_clean) else ""
                        )
                        result["filings"].append({
                            "form": forms[i],
                            "date": dates[i] if i < len(dates) else "",
                            "description": descriptions[i] if i < len(descriptions) else "",
                            "accession": acc,
                            "url": filing_url
                        })
        except Exception as e:
            logger.debug(f"SEC filing parsing failed for {ticker}: {e}")

    return result


# ---------------------------------------------------------------------------
# EUR conversion
# ---------------------------------------------------------------------------

def convert_to_eur(amount_usd: float) -> Optional[float]:
    """Convert USD to EUR using yfinance EURUSD=X rate."""
    try:
        yf = _load_yfinance()
        eur = yf.Ticker("EURUSD=X")
        rate = eur.info.get("regularMarketPrice") or eur.info.get("currentPrice")
        if rate:
            return round(amount_usd / rate, 2)
    except Exception as e:
        logger.debug(f"Fallback: {e}")
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val: Any) -> Optional[float]:
    """Safely convert a value to float, treating NaN/Inf as None."""
    if val is None:
        return None
    try:
        import math
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# SEC EDGAR — text extraction from 10-K filings
# ---------------------------------------------------------------------------

def _resolve_cik(ticker: str) -> Optional[str]:
    """Resolve ticker to CIK number."""
    from backend.http_client import http
    try:
        resp = http.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": "StockAnalysisPipeline/1.0"},
            timeout=10
        )
        if resp.status_code == 200:
            companies = resp.json()
            ticker_upper = ticker.upper()
            for _, company in companies.items():
                if company.get("ticker") == ticker_upper:
                    return str(company["cik_str"]).zfill(10)
    except Exception as e:
        logger.debug(f"Fallback: {e}")
    return None


def _get_latest_10k_url(ticker: str) -> Optional[tuple]:
    """Get the URL and accession number of the latest 10-K filing."""
    from backend.http_client import http
    cik = _resolve_cik(ticker)
    if not cik:
        return None

    try:
        resp = http.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers={"User-Agent": "StockAnalysisPipeline/1.0"},
            timeout=10
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        docs = filings.get("primaryDocument", [])
        accessions = filings.get("accessionNumber", [])

        for i in range(len(forms)):
            if forms[i] == "10-K":
                doc = docs[i] if i < len(docs) else ""
                acc = accessions[i] if i < len(accessions) else ""
                cik_int = int(cik)
                # ACC format: 0001045810-25-000045 → strip dashes for URL
                acc_clean = acc.replace("-", "")
                url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{doc}"
                return (url, doc, acc)
    except Exception as e:
        logger.debug(f"Fallback: {e}")
    return None


def extract_10k_sections(ticker: str, output_dir: Optional[str] = None) -> Dict[str, str]:
    """Download latest 10-K and extract MD&A + Risk Factors sections.
    If output_dir is provided, saves raw HTML to 02_sec_or_regulatory_filings/.
    Returns {'mda': '...', 'risk_factors': '...', 'url': '...', 'local_path': '...'}
    """
    from backend.http_client import http
    result = {"mda": "", "risk_factors": "", "url": "", "error": "", "local_path": ""}

    filing = _get_latest_10k_url(ticker)
    if not filing:
        result["error"] = f"No 10-K found for {ticker}"
        return result

    url, doc, acc = filing
    result["url"] = url

    try:
        resp = http.get(
            url,
            headers={"User-Agent": "StockAnalysisPipeline/1.0 (contact@example.com)"},
            timeout=30
        )
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code} fetching 10-K"
            return result

        text = resp.text

        # Save raw HTML to disk
        if output_dir:
            raw_dir = os.path.join(output_dir, "02_sec_or_regulatory_filings")
            os.makedirs(raw_dir, exist_ok=True)
            # Sanitize filename: 10-K_NVDA_2026-01-25.htm
            filing_date = acc.replace("-", "")[:8] if "-" in acc else "unknown"
            fname = f"10-K_{ticker}_{filing_date}.htm"
            raw_path = os.path.join(raw_dir, fname)
            with open(raw_path, "w", encoding="utf-8") as f:
                f.write(text)
            result["local_path"] = raw_path
            logger.info(f"10-K saved: {raw_path} ({len(text)} bytes)")

        # Extract text from HTML
        try:
            from html.parser import HTMLParser

            class TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.text = []
                    self.skip = False

                def handle_starttag(self, tag, attrs):
                    if tag in ('script', 'style'):
                        self.skip = True

                def handle_endtag(self, tag):
                    if tag in ('script', 'style'):
                        self.skip = False
                    if tag in ('p', 'div', 'br', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5'):
                        self.text.append('\n')

                def handle_data(self, data):
                    if not self.skip:
                        self.text.append(data)

            extractor = TextExtractor()
            extractor.feed(text)
            clean_text = ' '.join(extractor.text)
        except Exception:
            import re
            clean_text = re.sub(r'<[^>]+>', ' ', text)
            clean_text = re.sub(r'&nbsp;', ' ', clean_text)
            clean_text = re.sub(r'\s+', ' ', clean_text)

        # Extract MD&A (Item 7)
        mda = _extract_section(clean_text, "ITEM 7", "ITEM 8")
        result["mda"] = mda[:10000] if mda else ""

        # Extract Risk Factors (Item 1A)
        rf = _extract_section(clean_text, "ITEM 1A", "ITEM 1B")
        if not rf:
            rf = _extract_section(clean_text, "ITEM 1A", "ITEM 2")
        result["risk_factors"] = rf[:5000] if rf else ""

        # Extract Market Risk (Item 7A)
        mkt_risk = _extract_section(clean_text, "ITEM 7A", "ITEM 8")
        result["market_risk"] = mkt_risk[:3000] if mkt_risk else ""

        # Extract Financial Statements (Item 8 — raw, not parsed)
        fin_stmts = _extract_section(clean_text, "ITEM 8", "ITEM 9")
        result["financial_statements"] = fin_stmts[:8000] if fin_stmts else ""

        # Extract Business description (Item 1)
        bus = _extract_section(clean_text, "ITEM 1", "ITEM 1A")
        if not bus:
            bus = _extract_section(clean_text, "ITEM 1", "ITEM 2")
        result["business"] = bus[:8000] if bus else ""

    except Exception as e:
        result["error"] = str(e)

    return result


def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
    """Extract text between two markers, case-insensitive.
    Skips first occurrence (TOC) and uses second (actual content).
    Uses word-boundary matching to avoid ITEM 7A matching ITEM 7."""
    import re
    t = text.upper()
    s = start_marker.upper()
    e = end_marker.upper()

    # Build regex with word boundary — ITEM 7 but not ITEM 7A
    s_pat = re.compile(r'\b' + re.escape(s) + r'\b')
    e_pat = re.compile(r'\b' + re.escape(e) + r'\b')

    # Find second occurrence of start marker
    matches = list(s_pat.finditer(t))
    if len(matches) < 2:
        return ""
    start_idx = matches[1].start()

    # Find end marker after start
    end_match = e_pat.search(t, start_idx + len(s))
    if not end_match:
        return text[start_idx:start_idx + 8000]
    return text[start_idx:end_match.start()]


# ---------------------------------------------------------------------------
# edgartools wrapper — structured SEC EDGAR fundamentals (replaces raw HTML parsing)
# ---------------------------------------------------------------------------

def get_edgar_financials(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch structured financial data from SEC EDGAR via edgartools.
    
    Returns dict with: revenue, net_income, free_cash_flow, operating_income,
    gross_profit, total_assets, total_liabilities, stockholders_equity,
    cash_and_equivalents, total_debt, shares_outstanding,
    current_ratio, debt_to_assets, and metrics dict.
    
    Computed fields: net_debt (= total_debt - cash), gross_margin (= gross_profit / revenue).
    
    Returns None if edgartools unavailable or ticker not found.
    
    Requires: pip install edgartools
    On Render, edgartools may be blocked (SEC rate-limits from shared IPs).
    Fall back to manual SEC parsing if this returns None.
    """
    try:
        from edgar import Company, set_identity
        
        # edgartools crashes on empty HTTPS_PROXY — unset before import
        for var in ('HTTPS_PROXY', 'HTTP_PROXY', 'https_proxy', 'http_proxy', 'ALL_PROXY', 'all_proxy',
                     'HTTPS_PROXIES', 'HTTP_PROXIES', 'NO_PROXY', 'no_proxy'):
            val = os.environ.get(var, None)
            if val is not None and val.strip() == '':
                del os.environ[var]
        
        set_identity('StockAnalysisPipeline/1.0 (contact@example.com)')
        
        company = Company(ticker)
        financials = company.get_financials()
        
        # Core financials (already extracted)
        revenue = financials.get_revenue()
        net_income = financials.get_net_income()
        free_cash_flow = financials.get_free_cash_flow()
        operating_income = financials.get_operating_income()
        
        # New fields for deeper scoring
        gross_profit = _safe_get(financials, 'get_gross_profit')
        cost_of_revenue = _safe_get(financials, 'get_cost_of_revenue')
        cash = _safe_get(financials, 'get_cash_and_equivalents') or _safe_get(financials, 'get_cash')
        total_debt = _safe_get(financials, 'get_total_debt')
        total_assets = financials.get_total_assets()
        total_liabilities = financials.get_total_liabilities()
        
        # Computed fields
        gross_margin = None
        if gross_profit and revenue and revenue > 0:
            gross_margin = round(gross_profit / revenue, 4)
        elif revenue and cost_of_revenue and revenue > 0:
            gross_profit = revenue - cost_of_revenue
            gross_margin = round(gross_profit / revenue, 4)
        
        net_debt = None
        if total_debt is not None and cash is not None:
            net_debt = round(total_debt - cash, 2)
        
        result = {
            "ticker": ticker,
            "cik": company.cik,
            "source": "sec_edgar_xbrl",
            "metrics": financials.get_financial_metrics(),
            "revenue": revenue,
            "net_income": net_income,
            "free_cash_flow": free_cash_flow,
            "operating_income": operating_income,
            "gross_profit": gross_profit,
            "gross_margin": gross_margin,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "stockholders_equity": financials.get_stockholders_equity(),
            "shares_outstanding": financials.get_shares_outstanding_basic(),
            "cash_and_equivalents": cash,
            "total_debt": total_debt,
            "net_debt": net_debt,
        }
        return result
    except ImportError:
        logger.debug("edgartools not installed — skipping structured SEC data")
        return None
    except Exception as e:
        logger.warning(f"edgartools failed for {ticker}: {e}")
        return None


def _safe_get(obj, method_name: str) -> Optional[Any]:
    """Safely call a getter method on an object, returning None on any error."""
    try:
        method = getattr(obj, method_name, None)
        if method is None:
            return None
        return method()
    except Exception:
        return None
