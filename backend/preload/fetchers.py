"""
Preload fetchers — collect maximum data for prioritized tickers.

Calls existing pipeline modules (yfinance, transcript_finder, etc.)
to gather financials, transcripts, SEC filings, press releases, audio.
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure backend is importable
_backend_root = Path(__file__).parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root.parent))

logger = logging.getLogger(__name__)

# ── Rate limiter ─────────────────────────────────────────────────────────
_provider_last_call: Dict[str, float] = {}
_PROVIDER_DELAYS = {
    "yfinance": 2.0,
    "finnhub": 1.0,
    "sec_edgar": 0.5,
    "duckduckgo": 3.0,
    "fool": 2.0,
    "rapidapi": 5.0,
    "alphavantage": 15.0,  # 5 req/min free tier
}


def _rate_limit(provider: str):
    """Enforce minimum delay between calls to the same provider."""
    delay = _PROVIDER_DELAYS.get(provider, 1.0)
    last = _provider_last_call.get(provider, 0)
    elapsed = time.time() - last
    if elapsed < delay:
        time.sleep(delay - elapsed)
    _provider_last_call[provider] = time.time()


# ── Financials (yfinance) ────────────────────────────────────────────────
def fetch_financials(ticker: str) -> Dict[str, Any]:
    """Fetch 5 years of quarterly financials via yfinance."""
    _rate_limit("yfinance")
    import yfinance as yf
    
    stock = yf.Ticker(ticker)
    result = {
        "ticker": ticker,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    
    # Info dict
    try:
        info = stock.info
        result["info"] = {
            k: info.get(k) for k in [
                "shortName", "longName", "sector", "industry",
                "marketCap", "enterpriseValue", "trailingPE", "forwardPE",
                "pegRatio", "priceToBook", "priceToSales",
                "dividendYield", "payoutRatio",
                "beta", "52WeekChange",
                "revenueGrowth", "earningsGrowth",
                "grossMargins", "operatingMargins", "profitMargins",
                "returnOnEquity", "returnOnAssets",
                "debtToEquity", "currentRatio", "quickRatio",
                "website", "irWebsite",
            ] if k in info
        }
    except Exception as e:
        logger.warning(f"[{ticker}] Info fetch failed: {e}")
        result["info"] = {}
    
    # Quarterly financials — 5 years (20 quarters)
    for name, attr in [
        ("quarterly_income", "quarterly_income_stmt"),
        ("quarterly_balance", "quarterly_balance_sheet"),
        ("quarterly_cashflow", "quarterly_cashflow"),
        ("quarterly_eps", "quarterly_earnings"),
    ]:
        try:
            df = getattr(stock, attr, None)
            if df is not None and not df.empty:
                # Last 20 quarters
                df = df.iloc[:, :20]
                # Convert to dict, handle NaN
                result[name] = json.loads(
                    df.fillna(0).to_json(orient="index", date_format="iso")
                )
            else:
                result[name] = {}
        except Exception as e:
            logger.warning(f"[{ticker}] {name} fetch failed: {e}")
            result[name] = {}
    
    # Earnings dates
    try:
        cal = stock.calendar
        if cal is not None:
            result["earnings_dates"] = {
                "next_earnings_date": str(cal.get("Earnings Date", [""])[0]) if cal.get("Earnings Date") else None,
                "earnings_avg": cal.get("Earnings Average"),
                "earnings_low": cal.get("Earnings Low"),
                "earnings_high": cal.get("Earnings High"),
                "revenue_avg": cal.get("Revenue Average"),
            }
    except Exception as e:
        logger.warning(f"[{ticker}] Calendar fetch failed: {e}")
        result["earnings_dates"] = {}
    
    # Analyst recommendations
    try:
        recs = stock.recommendations
        if recs is not None and not recs.empty:
            result["recommendations"] = recs.tail(20).fillna(0).to_dict(orient="records")
    except Exception:
        result["recommendations"] = []
    
    # Institutional holders
    try:
        inst = stock.institutional_holders
        if inst is not None and not inst.empty:
            result["institutional_holders"] = inst.head(20).fillna(0).to_dict(orient="records")
    except Exception:
        result["institutional_holders"] = []
    
    return result


# ── Transcripts ──────────────────────────────────────────────────────────
def _fetch_stockanalysis_playwright(ticker: str) -> Optional[Dict[str, Any]]:
    """Scrape the latest earnings transcript from StockAnalysis.com using Playwright.
    
    StockAnalysis republishes full Seeking Alpha transcripts. Playwright is needed
    because the page is JS-rendered (no __NEXT_DATA__ in initial HTML).
    Returns None if no transcript found or scraping fails.
    """
    import asyncio
    import re
    
    ticker_lower = ticker.strip().lower()
    
    async def _scrape():
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = await context.new_page()
            
            try:
                # Step 1: Get the transcript listing page to find the latest quarter
                list_url = f"https://stockanalysis.com/stocks/{ticker_lower}/transcripts/"
                resp = await page.goto(list_url, timeout=20000, wait_until="domcontentloaded")
                if resp.status != 200:
                    await browser.close()
                    return None
                
                # Find the first (latest) transcript link
                links = await page.eval_on_selector_all(
                    "a[href*='/transcripts/']",
                    "els => els.map(e => ({href: e.href, text: e.textContent.trim()}))"
                )
                detail_url = None
                for l in links:
                    if '/transcripts/' in l['href'] and l['href'] != list_url and 'Earnings Call' in l.get('text', ''):
                        detail_url = l['href']
                        break
                
                if not detail_url and links:
                    # Fallback: take the first non-listing transcript link
                    for l in links:
                        if '/transcripts/' in l['href'] and l['href'] != list_url:
                            detail_url = l['href']
                            break
                
                if not detail_url:
                    await browser.close()
                    return None
                
                # Step 2: Navigate to the transcript detail page
                await page.goto(detail_url, timeout=20000, wait_until="networkidle")
                await page.wait_for_timeout(2000)  # Let JS render
                
                # Step 3: Extract the full transcript text
                body_text = await page.eval_on_selector("body", "el => el.textContent")
                
                # Find where the transcript starts (after nav/metadata)
                markers = ["Operator", "Good afternoon", "Good morning", "Ladies and gentlemen", "Welcome to"]
                start_idx = len(body_text)
                for marker in markers:
                    idx = body_text.find(marker)
                    if 0 < idx < start_idx:
                        start_idx = idx
                
                if start_idx < len(body_text):
                    transcript_text = body_text[start_idx:].strip()
                else:
                    transcript_text = body_text
                
                title = await page.title()
                
                await browser.close()
                
                return {
                    "source": "Seeking Alpha",
                    "url": detail_url,
                    "text": transcript_text,
                    "quarter": "",
                    "date": "",
                    "chars": len(transcript_text),
                }
            except Exception as e:
                logger.warning(f"[{ticker}] Playwright scrape error: {e}")
                await browser.close()
                return None
    
    try:
        return asyncio.run(_scrape())
    except Exception as e:
        logger.warning(f"[{ticker}] Playwright async error: {e}")
        return None


def fetch_transcripts(ticker: str, company: str = "") -> List[Dict[str, Any]]:
    """Search for earnings call transcripts — Seeking Alpha content via StockAnalysis.com.
    
    Seeking Alpha's article pages are behind a paywall (403 even with cookies).
    StockAnalysis.com republishes the full SA transcripts without restriction.
    Playwright is used to scrape the JS-rendered pages.
    """
    results = []

    # ── Primary: Seeking Alpha direct (with cookies) ──
    try:
        from backend.transcript_web_search import search_transcript_pages
        sa_results = search_transcript_pages(ticker, company=company)
        for r in sa_results:
            if r.get("text") and len(r.get("text", "")) >= 2000:
                results.append({
                    "source": r.get("source", "Seeking Alpha"),
                    "url": r.get("url", ""),
                    "text": r["text"],
                    "quarter": r.get("quarter", ""),
                    "date": r.get("date", ""),
                    "chars": len(r["text"]),
                })
    except Exception as e:
        logger.warning(f"[{ticker}] Seeking Alpha transcript search failed: {e}")

    # ── Fallback: Playwright scrape of StockAnalysis.com ──
    if not results:
        logger.info(f"[{ticker}] SA direct returned 0, trying StockAnalysis via Playwright...")
        try:
            sa_fallback = _fetch_stockanalysis_playwright(ticker)
            if sa_fallback:
                results.append(sa_fallback)
        except Exception as e:
            logger.warning(f"[{ticker}] Playwright StockAnalysis fallback failed: {e}")

    return results


# ── Earnings audio ───────────────────────────────────────────────────────
def fetch_audio_urls(ticker: str) -> List[Dict[str, str]]:
    """Find earnings call audio URLs (Fool.com, IR pages, etc.).
    Returns list of {source, url, date, quarter} — download not attempted here."""
    urls = []
    
    # Fool.com often has audio alongside transcripts
    try:
        _rate_limit("fool")
        from backend.http_client import http
        # Search Fool.com for ticker earnings
        resp = http.get(
            f"https://www.fool.com/earnings/call-transcripts/{ticker.lower()}/",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            import re
            # Find audio/mp3 links
            audio_matches = re.findall(
                r'https?://[^\s"\']+\.(?:mp3|m4a|ogg|wav)[^\s"\']*',
                resp.text,
                re.IGNORECASE
            )
            for url in audio_matches[:3]:
                urls.append({"source": "Fool.com", "url": url})
    except Exception as e:
        logger.debug(f"[{ticker}] Audio search failed: {e}")
    
    return urls


# ── SEC filings ──────────────────────────────────────────────────────────
def fetch_sec_filings(ticker: str) -> Dict[str, Any]:
    """Fetch recent SEC filings metadata (8-K, 10-Q, 10-K)."""
    _rate_limit("sec_edgar")
    try:
        from backend.sources_collector import get_sec_filings
        filings = get_sec_filings(ticker)
        # Keep only relevant forms
        relevant = []
        for f in filings.get("filings", []):
            form = f.get("form", "")
            if form in ("8-K", "10-Q", "10-K", "8-K/A"):
                relevant.append(f)
        return {
            "ticker": ticker,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "filings": relevant[:50],  # Last 50 relevant filings
        }
    except Exception as e:
        logger.warning(f"[{ticker}] SEC filings failed: {e}")
        return {"ticker": ticker, "filings": [], "error": str(e)}


# ── Press releases (IR page) ─────────────────────────────────────────────
def fetch_press_releases(ticker: str, company: str = "") -> List[Dict[str, Any]]:
    """Find earnings press releases from IR page or DDG search."""
    results = []
    
    try:
        _rate_limit("duckduckgo")
        from backend.transcript_finder import find_earnings_documents
        docs = find_earnings_documents(ticker, company=company)
        if docs.get("press_release", {}).get("status") == "FOUND":
            results.append({
                "type": "press_release",
                "url": docs["press_release"]["url"],
                "source": docs["press_release"].get("source", "corporate"),
                "found_at": datetime.now(timezone.utc).isoformat(),
            })
        if docs.get("presentation", {}).get("status") == "FOUND":
            results.append({
                "type": "presentation",
                "url": docs["presentation"]["url"],
                "source": docs["presentation"].get("source", "corporate"),
                "found_at": datetime.now(timezone.utc).isoformat(),
            })
    except Exception as e:
        logger.warning(f"[{ticker}] Press release search failed: {e}")
    
    return results


# ── IR page ──────────────────────────────────────────────────────────────
def fetch_ir_page(ticker: str, ir_url: str = "") -> Optional[str]:
    """Download raw investor relations page HTML."""
    if not ir_url:
        # Try to discover IR URL from yfinance
        try:
            _rate_limit("yfinance")
            import yfinance as yf
            info = yf.Ticker(ticker).info
            ir_url = info.get("irWebsite") or info.get("website") or ""
            if ir_url and "investor" not in ir_url.lower():
                ir_url = ""  # Not actually an IR page
        except Exception:
            pass
    
    if not ir_url:
        return None
    
    try:
        _rate_limit("duckduckgo")
        from backend.http_client import http
        resp = http.get(
            ir_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        logger.warning(f"[{ticker}] IR page fetch failed: {e}")
    
    return None
