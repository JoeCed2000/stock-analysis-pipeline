"""Generic web transcript discovery through Google Custom Search + Tavily fallback."""
import html
import json
import logging
import os
import re
from html.parser import HTMLParser
from typing import Dict, List

import httpx

from backend.google_search import search_google
from backend.http_client import http
from backend.seeking_alpha_access import build_request_headers
from backend.storage_paths import REPO_ROOT

logger = logging.getLogger(__name__)

MIN_TRANSCRIPT_CHARS = 10_000
TRUSTED_TRANSCRIPT_HOSTS = (
    "seekingalpha.com",
)
SA_ARTICLE_CACHE_PATH = REPO_ROOT / ".state" / "seeking_alpha_article_cache.json"


def _read_article_cache() -> dict[str, list[dict[str, str]]]:
    try:
        if not SA_ARTICLE_CACHE_PATH.exists():
            return {}
        with SA_ARTICLE_CACHE_PATH.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        logger.warning(f"Failed to read SA article cache: {exc}")
        return {}


def _write_article_cache(cache: dict[str, list[dict[str, str]]]) -> None:
    try:
        SA_ARTICLE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SA_ARTICLE_CACHE_PATH.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
        tmp.replace(SA_ARTICLE_CACHE_PATH)
    except Exception as exc:
        logger.warning(f"Failed to write SA article cache: {exc}")


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = False
        if tag in ("p", "div", "br", "tr", "li", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def _search_sa_direct(ticker: str, company: str | None = None, limit: int = 5) -> List[Dict[str, str]]:
    """Search Seeking Alpha directly using stored cookies — no external search API needed."""
    ticker_clean = ticker.strip().upper()
    headers = build_request_headers()
    
    if "Cookie" not in headers:
        logger.info(f"[{ticker_clean}] No SA cookies configured, skipping direct SA search")
        return []
    
    # Step 1: Fetch the transcript listing page
    list_url = f"https://seekingalpha.com/symbol/{ticker_clean}/earnings/transcripts"
    try:
        resp = http.get(list_url, headers=headers, timeout=20, follow_redirects=True)
        if resp.status_code != 200:
            logger.warning(f"[{ticker_clean}] SA listing returned {resp.status_code}")
            return []
    except Exception as e:
        logger.warning(f"[{ticker_clean}] SA listing fetch failed: {e}")
        return []
    
    # Step 2: Extract article IDs from the listing page
    article_ids = re.findall(r'/(\d{5,8})-[\w-]+', resp.text)
    if not article_ids:
        article_ids = re.findall(r'/article/(\d{5,8})', resp.text)
    
    if not article_ids:
        logger.info(f"[{ticker_clean}] No article IDs found on SA listing page")
        return []
    
    # Take unique IDs, sorted (newest = highest ID typically)
    unique_ids = list(dict.fromkeys(article_ids))[:limit]
    logger.info(f"[{ticker_clean}] Found {len(unique_ids)} SA article IDs: {unique_ids[:3]}...")
    
    results = []
    for aid in unique_ids:
        article_url = f"https://seekingalpha.com/article/{aid}"
        text = _fetch_page_text_sa(article_url, headers)
        if not text or not _looks_like_transcript(text, ticker_clean):
            continue
        
        # Extract title and metadata from the page
        title_match = re.search(r'<title>(.*?)</title>', resp.text if hasattr(resp, 'text') else '', re.I)
        title = title_match.group(1) if title_match else f"{ticker_clean} Earnings Call Transcript"
        title = html.unescape(title.replace(" | Seeking Alpha", "").strip())
        
        results.append({
            "source": "Seeking Alpha",
            "type": "earnings_transcript",
            "title": title,
            "url": article_url,
            "text": text,
            "text_length": len(text),
            "quarter": _extract_quarter(title + " " + text[:1000]),
            "date": _extract_date(title + " " + text[:1000]),
            "id": aid,
        })
        break  # Just the first (most recent) transcript
    
    return results


def _fetch_page_text_sa(url: str, headers: dict = None) -> str:
    """Fetch and extract text from an SA page using cookie auth."""
    try:
        h = headers or build_request_headers()
        response = http.get(url, headers=h, timeout=20, follow_redirects=True)
    except Exception as exc:
        logger.warning(f"SA page fetch failed for {url}: {exc}")
        return ""
    if response.status_code != 200:
        return ""
    
    extractor = _TextExtractor()
    extractor.feed(response.text)
    text = html.unescape(" ".join(extractor.parts))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip()


def _search_brave(ticker: str, company: str | None = None, limit: int = 5) -> List[Dict[str, str]]:
    """Discover concrete Seeking Alpha article URLs through Brave's public search page.

    The Seeking Alpha transcript listing route is often blocked by PerimeterX even when
    direct transcript article URLs are readable with the stored browser cookies.  This
    helper is discovery-only: it never returns StockAnalysis links and never fabricates
    the generic `/symbol/.../earnings/transcripts` listing URL.
    """
    import urllib.parse

    ticker_clean = ticker.strip().upper()
    company_part = f" {company.strip()}" if isinstance(company, str) and company.strip() else ""
    cache_key = f"{ticker_clean}|{company_part.strip()}"
    cache = _read_article_cache()
    cached_results = cache.get(cache_key) or []
    query = f"site:seekingalpha.com/article {ticker_clean}{company_part} earnings call transcript"
    search_url = f"https://search.brave.com/search?q={urllib.parse.quote(query)}"

    try:
        resp = http.get(
            search_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "identity",
            },
            timeout=20,
            follow_redirects=True,
        )
    except Exception as exc:
        logger.warning(f"[{ticker_clean}] Brave SA transcript search failed: {exc}")
        return cached_results

    if resp.status_code != 200:
        logger.warning(f"[{ticker_clean}] Brave SA transcript search returned {resp.status_code}")
        return cached_results

    body = html.unescape(resp.text)
    urls: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"https://seekingalpha\.com/article/\d{5,8}[-\w]*", body):
        url = match.group(0).rstrip("/.,)")
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) >= limit:
            break

    results = [{"url": url, "title": f"{ticker_clean} earnings transcript"} for url in urls]
    if results:
        cache[cache_key] = results
        if company_part.strip():
            cache.setdefault(f"{ticker_clean}|", results)
        _write_article_cache(cache)
    logger.info(f"[{ticker_clean}] Brave SA transcript search: {len(results)} candidate(s)")
    return results



def _search_tavily(ticker: str, company: str | None = None, limit: int = 5) -> List[Dict[str, str]]:
    """Search Seeking Alpha transcripts via Tavily API."""
    import urllib.request
    import urllib.error
    
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not tavily_key:
        logger.warning("TAVILY_API_KEY not set, cannot search transcripts via Tavily")
        return []
    
    company_part = f" {company.strip()}" if isinstance(company, str) and company.strip() else ""
    query = f"{ticker}{company_part} earnings call transcript site:seekingalpha.com"
    
    try:
        data = json.dumps({
            "api_key": tavily_key,
            "query": query,
            "max_results": limit,
            "include_domains": ["seekingalpha.com"],
        }).encode()
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=20)
        body = json.loads(resp.read())
        results = []
        for r in body.get("results", []):
            url = r.get("url", "")
            if not url:
                continue
            results.append({
                "url": url,
                "title": r.get("title", ""),
            })
        logger.info(f"[{ticker}] Tavily transcript search: {len(results)} results")
        return results
    except urllib.error.HTTPError as e:
        logger.warning(f"[{ticker}] Tavily transcript search HTTP {e.code}: {e.reason}")
        return []
    except Exception as e:
        logger.warning(f"[{ticker}] Tavily transcript search failed: {e}")
        return []


def search_transcript_pages(ticker: str, company: str | None = None, limit: int = 5) -> List[Dict[str, str]]:
    ticker_clean = ticker.strip().upper()
    company_part = f" {company.strip()}" if isinstance(company, str) and company.strip() else ""
    queries = [
        f'{ticker_clean}{company_part} earnings call transcript site:seekingalpha.com',
        f'{ticker_clean}{company_part} \"earnings call transcript\" seekingalpha',
        f'{ticker_clean} seeking alpha earnings transcript quarter',
    ]

    candidates: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    
    # ── PRIORITY 1: Direct SA access with cookies (no search API needed) ──
    sa_direct = _search_sa_direct(ticker_clean, company, limit)
    if sa_direct:
        logger.info(f"[{ticker_clean}] SA direct access succeeded ({len(sa_direct)} transcripts)")
        return sa_direct
    
    # ── PRIORITY 2: Google Custom Search ──
    for query in queries:
        for result in search_google(query, limit=limit):
            url = result.get("url", "")
            if not _is_candidate_url(url) or url in seen_urls:
                continue
            seen_urls.add(url)
            candidates.append(result)
            if len(candidates) >= limit:
                break
        if len(candidates) >= limit:
            break
    
    # Fallback: Brave public search if Google returned nothing.  Brave often
    # exposes the concrete Seeking Alpha article URL even when the SA listing
    # route itself is PerimeterX-blocked.
    if not candidates:
        logger.info(f"[{ticker_clean}] Google Search returned 0 results, trying Brave fallback...")
        brave_results = _search_brave(ticker_clean, company, limit)
        for r in brave_results:
            url = r.get("url", "")
            if url and _is_candidate_url(url) and url not in seen_urls:
                seen_urls.add(url)
                candidates.append(r)
                if len(candidates) >= limit:
                    break

    # Fallback: Tavily search if Google/Brave returned nothing
    if not candidates:
        logger.info(f"[{ticker_clean}] Google/Brave returned 0 results, trying Tavily fallback...")
        tavily_results = _search_tavily(ticker_clean, company, limit)
        for r in tavily_results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                candidates.append(r)
                if len(candidates) >= limit:
                    break

    transcripts: List[Dict[str, str]] = []
    for candidate in candidates:
        url = candidate["url"]
        text = _fetch_page_text_sa(url) if "seekingalpha.com" in url.lower() else _fetch_page_text(url)
        if not _looks_like_transcript(text, ticker_clean):
            continue
        transcripts.append(
            {
                "source": "Seeking Alpha",
                "type": "earnings_transcript",
                "title": candidate.get("title", "") or f"{ticker_clean} earnings transcript",
                "url": url,
                "text": text,
                "text_length": len(text),
                "quarter": _extract_quarter(candidate.get("title", "") + " " + text[:1000]),
                "date": _extract_date(candidate.get("title", "") + " " + text[:1000]),
                "id": "",
            }
        )
        break

    return transcripts


def _is_candidate_url(url: str) -> bool:
    lower = url.lower()
    return lower.startswith("https://") and any(host in lower for host in TRUSTED_TRANSCRIPT_HOSTS)


def _resolve_stockanalysis_url(url: str, ticker: str) -> str:
    """If url is a stockanalysis.com listing page, extract the first specific transcript link.
    
    Example: /stocks/msft/transcripts/ → /stocks/msft/transcripts/547930-q3-2026/
    """
    ticker_lower = ticker.lower()
    listing_pattern = re.compile(
        rf"https?://stockanalysis\.com/stocks/{re.escape(ticker_lower)}/transcripts/?$",
        re.IGNORECASE,
    )
    if not listing_pattern.search(url):
        return url

    try:
        resp = http.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=20,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return url
        specific = re.search(
            rf'href="(/stocks/{re.escape(ticker_lower)}/transcripts/\d+-[^"]+/)"',
            resp.text,
        )
        if specific:
            resolved = f"https://stockanalysis.com{specific.group(1)}"
            logger.info(f"Resolved stockanalysis.com listing → {resolved}")
            return resolved
    except Exception as exc:
        logger.warning(f"Failed to resolve stockanalysis.com listing: {exc}")
    return url


def _fetch_page_text(url: str) -> str:
    try:
        response = http.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    except httpx.RequestError as exc:
        logger.warning(f"Transcript page fetch failed for {url}: {exc}")
        return ""
    if response.status_code != 200:
        return ""

    extractor = _TextExtractor()
    extractor.feed(response.text)
    text = html.unescape(" ".join(extractor.parts))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip()


def _looks_like_transcript(text: str, ticker: str) -> bool:
    if len(text) < MIN_TRANSCRIPT_CHARS:
        return False
    lower = text.lower()
    signals = (
        "earnings call",
        "transcript",
        "operator",
        "revenue",
        "eps",
        "earnings per share",
    )
    return ticker.lower() in lower and sum(1 for signal in signals if signal in lower) >= 3


def _extract_quarter(text: str) -> str:
    match = re.search(r"\b(?:FY|Fiscal Year)\s?(\d{2,4})\s*(?:Q|Quarter)\s?([1-4])\b", text, re.I)
    if match:
        year = match.group(1)
        if len(year) == 2:
            year = f"20{year}"
        return f"FY{year} Q{match.group(2)}"
    match = re.search(r"\bQ([1-4])\s*(?:FY)?\s?(\d{4})\b", text, re.I)
    if match:
        return f"FY{match.group(2)} Q{match.group(1)}"
    return ""


def _extract_date(text: str) -> str:
    match = re.search(r"\b(20\d{2})[-/](\d{2})[-/](\d{2})\b", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return ""
