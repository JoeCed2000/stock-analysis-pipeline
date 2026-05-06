"""DuckDuckGo web search for earnings call transcripts — no API key needed."""
import html as html_mod
import logging
import re
from html.parser import HTMLParser
from typing import Dict, List
from urllib.parse import quote_plus

import httpx

from backend.http_client import http

logger = logging.getLogger(__name__)

MIN_TRANSCRIPT_CHARS = 2000
TRUSTED_HOSTS = (
    "fool.com", "seekingalpha.com", "stockanalysis.com",
    "yahoo.com", "nasdaq.com", "marketbeat.com", "zacks.com",
    "investor.", "ir.", "earningscast.com", "tickertrends.io",
    "fintool.com", "earningscall.ai",
)


def search_transcripts_ddg(ticker: str, company: str | None = None, limit: int = 5) -> List[Dict[str, str]]:
    """Search DuckDuckGo for earnings call transcripts. Free, no API key."""
    ticker_clean = ticker.strip().upper()
    company_part = f" {company.strip()}" if company and company.strip() else ""
    query = f"{ticker_clean}{company_part} earnings call transcript"

    try:
        ddg_url = "https://html.duckduckgo.com/html/"
        resp = http.get(
            ddg_url,
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15,
        )
    except httpx.RequestError as exc:
        logger.warning(f"DuckDuckGo search failed: {exc}")
        return []

    if resp.status_code != 200:
        logger.warning(f"DuckDuckGo returned HTTP {resp.status_code}")
        return []

    # Parse DDG HTML results
    urls = _extract_urls(resp.text, limit)
    if not urls:
        logger.info(f"DuckDuckGo: no transcript URLs found for {ticker_clean}")
        return []

    transcripts = []
    for url in urls:
        text = _fetch_page_text(url)
        if not _looks_like_transcript(text, ticker_clean):
            continue
        transcripts.append({
            "source": "DuckDuckGo Web Search",
            "type": "earnings_transcript",
            "title": f"{ticker_clean} Earnings Call Transcript",
            "url": url,
            "text": text,
            "text_length": len(text),
            "quarter": _extract_quarter(text),
            "date": _extract_date(text),
            "id": "",
        })
        logger.info(f"DuckDuckGo transcript: {len(text)} chars for {ticker_clean} from {url[:80]}")
        break

    return transcripts


def _extract_urls(html_text: str, limit: int) -> List[str]:
    """Extract result URLs from DuckDuckGo HTML results page."""
    # DDG HTML results have links in class='result__a' or similar
    urls = []
    # Match href attributes in result links
    for match in re.finditer(r'class="result__url"[^>]*>(?:https?://)?([^<]+)', html_text):
        domain = match.group(1).strip()
        # Normalize to full URL
        if not domain.startswith("http"):
            domain = f"https://{domain}"
        if any(host in domain.lower() for host in TRUSTED_HOSTS):
            if domain not in urls:
                urls.append(domain)
                if len(urls) >= limit:
                    break
    return urls


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: List[str] = []
        self.skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "nav", "header", "footer"):
            self.skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "nav", "header", "footer"):
            self.skip = False
        if tag in ("p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def _fetch_page_text(url: str) -> str:
    try:
        resp = http.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=20,
            follow_redirects=True,
        )
    except httpx.RequestError as exc:
        logger.warning(f"Transcript page fetch failed for {url[:80]}: {exc}")
        return ""
    if resp.status_code != 200:
        return ""

    extractor = _TextExtractor()
    extractor.feed(resp.text)
    text = html_mod.unescape(" ".join(extractor.parts))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip()


def _looks_like_transcript(text: str, ticker: str) -> bool:
    if len(text) < MIN_TRANSCRIPT_CHARS:
        return False
    lower = text.lower()
    signals = ("earnings call", "transcript", "operator", "revenue", "eps", "earnings per share")
    return ticker.lower() in lower and sum(1 for s in signals if s in lower) >= 3


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
