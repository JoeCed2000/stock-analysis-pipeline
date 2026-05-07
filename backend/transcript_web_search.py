"""Generic web transcript discovery through Google Custom Search."""
import html
import logging
import re
from html.parser import HTMLParser
from typing import Dict, List

import httpx

from backend.google_search import search_google
from backend.http_client import http

logger = logging.getLogger(__name__)

MIN_TRANSCRIPT_CHARS = 500
TRUSTED_TRANSCRIPT_HOSTS = (
    "microsoft.com",
    "investor.",
    "ir.",
    "stockanalysis.com",
    "fool.com",
    "seekingalpha.com",
    "earningscall.ai",
    "tickertrends.io",
    "fintool.com",
)


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


def search_transcript_pages(ticker: str, company: str | None = None, limit: int = 5) -> List[Dict[str, str]]:
    ticker_clean = ticker.strip().upper()
    company_part = f" {company.strip()}" if isinstance(company, str) and company.strip() else ""
    queries = [
        f"{ticker_clean}{company_part} earnings call transcript official investor relations",
        f"{ticker_clean}{company_part} fiscal quarter earnings transcript EPS revenue",
        f"{ticker_clean} earnings call transcript stockanalysis",
    ]

    candidates: list[dict[str, str]] = []
    seen_urls: set[str] = set()
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

    transcripts: List[Dict[str, str]] = []
    for candidate in candidates:
        url = candidate["url"]
        # Resolve stockanalysis.com listing pages to specific transcript links
        resolved_url = _resolve_stockanalysis_url(url, ticker_clean)
        text = _fetch_page_text(resolved_url)
        if not _looks_like_transcript(text, ticker_clean):
            continue
        transcripts.append(
            {
                "source": "Google Search Transcript",
                "type": "earnings_transcript",
                "title": candidate.get("title", "") or f"{ticker_clean} earnings transcript",
                "url": resolved_url,
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
