"""Data collection layer — yfinance, Finnhub, SEC EDGAR wrappers."""
import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache layer — file-based JSON cache with TTL
# ---------------------------------------------------------------------------

CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_TTL_SECONDS = 3600  # 1 hour


def _cache_path(ticker: str) -> Path:
    """Get cache file path for a ticker."""
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"{ticker.upper()}.json"


def _cache_get(ticker: str) -> Optional[Dict[str, Any]]:
    """Read from cache if still valid."""
    path = _cache_path(ticker)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            entry = json.load(f)
        age = datetime.now(timezone.utc).timestamp() - entry.get("timestamp", 0)
        if age < CACHE_TTL_SECONDS:
            logger.info(f"Cache HIT for {ticker} (age: {age:.0f}s)")
            return entry["data"]
        logger.info(f"Cache EXPIRED for {ticker} (age: {age:.0f}s)")
    except Exception:
        pass
    return None


def _cache_set(ticker: str, data: Dict[str, Any]) -> None:
    """Write data to cache."""
    try:
        entry = {
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "data": data,
        }
        with open(_cache_path(ticker), "w") as f:
            json.dump(entry, f)
        logger.info(f"Cache SET for {ticker}")
    except Exception:
        pass

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


def get_stock_data(ticker: str) -> Dict[str, Any]:
    """Fetch fundamental + price data. Multi-source chain:
    1. Finnhub (US equities, 60 calls/min, free)
    2. Twelve Data (international, 800 calls/day, free — needs TWELVEDATA_API_KEY)
    3. yfinance (last resort, may fail on shared-IP hosting like Render)
    Uses file-based cache (TTL 1h) to minimize API calls."""
    # Check cache first
    cached = _cache_get(ticker)
    if cached is not None:
        return cached

    # Try Finnhub (US only)
    result = _get_stock_data_finnhub(ticker)
    if result is not None:
        _cache_set(ticker, result)
        return result

    # Try Twelve Data (international)
    result = _get_stock_data_twelvedata(ticker)
    if result is not None:
        _cache_set(ticker, result)
        return result

    # Last resort: yfinance
    logger.info(f"Finnhub/Twelve Data unavailable for {ticker}, falling back to yfinance")
    try:
        result = get_yahoo_data(ticker)
        _cache_set(ticker, result)
        return result
    except Exception as e:
        logger.error(f"All sources failed for {ticker}: {e}")
        raise RuntimeError(
            f"No data source available for {ticker}. "
            f"US stocks: set FINNHUB_API_KEY. "
            f"International: set TWELVEDATA_API_KEY (free at twelvedata.com). "
            f"Or run analysis locally where yfinance works."
        )


def _get_stock_data_finnhub(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch stock data from Finnhub. Returns None if unavailable."""
    api_key = os.getenv("FINNHUB_API_KEY", "")
    if not api_key:
        return None

    import requests

    def _fh(path: str) -> Optional[Dict]:
        try:
            resp = requests.get(
                f"https://finnhub.io/api/v1{path}&token={api_key}",
                timeout=10
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if "error" in data:
                return None
            return data
        except Exception:
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
            "guidance_official": metrics.get("revenueGrowthTTMYoy"),
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

    import requests

    try:
        # Quote endpoint (real-time price)
        resp = requests.get(
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
                "revenue_yoy_growth": change_pct,  # Not ideal but better than nothing
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
# YFinance wrapper (fallback)
# ---------------------------------------------------------------------------

def _load_yfinance():
    """Lazy-import yfinance — slow on first load."""
    import yfinance as yf
    return yf


def get_yahoo_data(ticker: str) -> Dict[str, Any]:
    """Fetch all available fundamental + price data from Yahoo Finance.
    Uses file-based cache (TTL 1h) to avoid rate-limits."""
    # Check cache first
    cached = _cache_get(ticker)
    if cached is not None:
        return cached

    yf = _load_yfinance()
    stock = yf.Ticker(ticker)
    info = stock.info or {}

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

    # Build financial data
    financials = {
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
    }

    if quarterly_income is not None and not quarterly_income.empty:
        try:
            latest_q = quarterly_income.columns[0]
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
        except Exception:
            pass

    if income is not None and not income.empty:
        try:
            latest_year = income.columns[0]
            financials["revenue_annual"] = _safe_float(
                income.loc["Total Revenue", latest_year] if "Total Revenue" in income.index else None
            )
            financials["net_income"] = _safe_float(
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
        except Exception:
            pass

    if cashflow is not None and not cashflow.empty:
        try:
            latest = cashflow.columns[0]
            fcf = _safe_float(
                cashflow.loc["Free Cash Flow", latest] if "Free Cash Flow" in cashflow.index else None
            )
            financials["free_cash_flow"] = fcf
        except Exception:
            pass

    if balance is not None and not balance.empty:
        try:
            latest = balance.columns[0]
            total_debt = _safe_float(
                balance.loc["Total Debt", latest] if "Total Debt" in balance.index else None
            )
            cash_eq = _safe_float(
                balance.loc["Cash And Cash Equivalents", latest] if "Cash And Cash Equivalents" in balance.index else None
            )
            if total_debt is not None and cash_eq is not None:
                financials["net_debt"] = total_debt - cash_eq
        except Exception:
            pass

    # Margins from info
    financials["gross_margin"] = info.get("grossMargins")
    financials["operating_margin"] = info.get("operatingMargins")

    # Guidance
    financials["guidance_official"] = info.get("earningsQuarterlyGrowth")

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
    }

    # Save to cache
    _cache_set(ticker, result)

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
    except Exception:
        pass

    try:
        result["peers"] = client.company_peers(ticker)
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# SEC EDGAR — lightweight fetch (just latest filing metadata)
# ---------------------------------------------------------------------------

def get_sec_filings(ticker: str, cik: Optional[str] = None) -> Dict[str, Any]:
    """Get latest SEC filings metadata for a ticker."""
    import requests  # local import for testability

    result: Dict[str, Any] = {"filings": [], "cik": cik}

    # Resolve CIK if not provided
    if not cik:
        try:
            resp = requests.get(
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
        except Exception:
            pass

    if cik:
        try:
            resp = requests.get(
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
                descriptions = filings_raw.get("primaryDocDescription", [])

                for i in range(min(20, len(forms))):
                    if forms[i] in ("10-K", "10-Q", "8-K"):
                        doc_url = urls[i] if i < len(urls) else ""
                        filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{doc_url.replace('/', '')}/{doc_url}" if doc_url else ""
                        result["filings"].append({
                            "form": forms[i],
                            "date": dates[i] if i < len(dates) else "",
                            "description": descriptions[i] if i < len(descriptions) else "",
                            "url": filing_url
                        })
        except Exception:
            pass

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
            return round(amount_usd * rate, 2)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val: Any) -> Optional[float]:
    """Safely convert a value to float."""
    if val is None:
        return None
    try:
        return float(val)
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
    import requests
    try:
        resp = requests.get(
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
    except Exception:
        pass
    return None


def _get_latest_10k_url(ticker: str) -> Optional[tuple]:
    """Get the URL and accession number of the latest 10-K filing."""
    import requests
    cik = _resolve_cik(ticker)
    if not cik:
        return None

    try:
        resp = requests.get(
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

        for i in range(min(100, len(forms))):
            if forms[i] == "10-K":
                doc = docs[i] if i < len(docs) else ""
                acc = accessions[i] if i < len(accessions) else ""
                cik_int = int(cik)
                # ACC format: 0001045810-25-000045 → strip dashes for URL
                acc_clean = acc.replace("-", "")
                url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{doc}"
                return (url, doc, acc)
    except Exception:
        pass
    return None


def extract_10k_sections(ticker: str, output_dir: Optional[str] = None) -> Dict[str, str]:
    """Download latest 10-K and extract MD&A + Risk Factors sections.
    If output_dir is provided, saves raw HTML to 02_sec_or_regulatory_filings/.
    Returns {'mda': '...', 'risk_factors': '...', 'url': '...', 'local_path': '...'}
    """
    result = {"mda": "", "risk_factors": "", "url": "", "error": "", "local_path": ""}
    import requests

    filing = _get_latest_10k_url(ticker)
    if not filing:
        result["error"] = f"No 10-K found for {ticker}"
        return result

    url, doc, acc = filing
    result["url"] = url

    try:
        resp = requests.get(
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
