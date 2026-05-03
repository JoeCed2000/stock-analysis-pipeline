"""Data collection layer — yfinance, Finnhub, SEC EDGAR wrappers."""
import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# YFinance wrapper
# ---------------------------------------------------------------------------

def _load_yfinance():
    """Lazy-import yfinance — slow on first load."""
    import yfinance as yf
    return yf


def get_yahoo_data(ticker: str) -> Dict[str, Any]:
    """Fetch all available fundamental + price data from Yahoo Finance."""
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

    return {
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
