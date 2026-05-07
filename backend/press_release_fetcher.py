"""Find and extract official earnings press release data."""

from __future__ import annotations

import html
import logging
import os
import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from backend.http_client import http

logger = logging.getLogger(__name__)

PRESS_RELEASE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_MONEY_RE = re.compile(
    r"\$?\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(billion|million|bn|m|b)?",
    re.IGNORECASE,
)

_TRUSTED_PRESS_HOSTS = (
    "nvidianews.nvidia.com",
    "investor.",
    "ir.",
    "newsroom.",
    "businesswire.com",
    "prnewswire.com",
)

_GENERIC_SEGMENT_RE = re.compile(
    r"^(?:total|revenue|net revenue|net revenues|net sales|gaap|non-gaap|"
    r"gross margin|operating income|net income|diluted eps|outlook)$",
    re.IGNORECASE,
)


class _TableTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: List[str] = []
        self.tables: List[List[List[str]]] = []
        self.links: List[str] = []
        self._skip_depth = 0
        self._current_table: Optional[List[List[str]]] = None
        self._current_row: Optional[List[str]] = None
        self._current_cell: Optional[List[str]] = None

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attr_map = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if tag == "a" and attr_map.get("href"):
            self.links.append(html.unescape(attr_map["href"] or ""))
        if self._skip_depth:
            return
        if tag == "table":
            self._current_table = []
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = []
        elif tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            cell = re.sub(r"\s+", " ", " ".join(self._current_cell)).strip()
            self._current_row.append(cell)
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None and self._current_table is not None:
            if any(cell.strip() for cell in self._current_row):
                self._current_table.append(self._current_row)
            self._current_row = None
        elif tag == "table" and self._current_table is not None:
            if self._current_table:
                self.tables.append(self._current_table)
            self._current_table = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        value = html.unescape(data)
        if self._current_cell is not None:
            self._current_cell.append(value)
        else:
            self.text_parts.append(value)

    @property
    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", "".join(self.text_parts))).strip()


def _parse_html(html_text: str) -> _TableTextParser:
    parser = _TableTextParser()
    parser.feed(html_text)
    parser.close()
    return parser


def _fetch_url(url: str, timeout: int = 15) -> Optional[httpx.Response]:
    try:
        response = http.get(
            url,
            headers={"User-Agent": PRESS_RELEASE_USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )
    except httpx.RequestError as exc:
        logger.warning("Press release request failed for %s: %s", url, exc)
        return None
    return response if response.status_code == 200 else None


def _nvidia_candidate_urls() -> List[str]:
    year = datetime.now().year
    return [
        f"https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-fourth-quarter-and-fiscal-{year}",
        f"https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-third-quarter-fiscal-{year}",
        f"https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-second-quarter-fiscal-{year}",
        f"https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-first-quarter-fiscal-{year}",
    ]


def _normalize_ddg_href(href: str) -> Optional[str]:
    href = html.unescape(href)
    if href.startswith("//duckduckgo.com/l/"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target) if target else None
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return None


def _extract_search_urls(html_text: str, limit: int = 8) -> List[str]:
    parser = _parse_html(html_text)
    urls: List[str] = []
    for href in parser.links:
        url = _normalize_ddg_href(href)
        if not url:
            continue
        lowered = url.lower()
        if "earnings" not in lowered and "financial-results" not in lowered:
            continue
        if not any(host in lowered for host in _TRUSTED_PRESS_HOSTS):
            continue
        if url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def find_press_release_url(ticker: str) -> Optional[str]:
    """Find the most likely official earnings press release URL."""
    ticker_clean = ticker.strip().upper()
    if not ticker_clean:
        return None

    if ticker_clean == "NVDA":
        for candidate in _nvidia_candidate_urls():
            response = _fetch_url(candidate, timeout=4)
            if response is not None and "financial results" in response.text.lower():
                return str(response.url)

    query = f"{ticker_clean} latest quarterly earnings press release financial results"
    ddg_url = "https://html.duckduckgo.com/html/"
    try:
        response = http.get(
            ddg_url,
            params={"q": query},
            headers={"User-Agent": PRESS_RELEASE_USER_AGENT},
            timeout=8,
            follow_redirects=True,
        )
    except httpx.RequestError as exc:
        logger.warning("DuckDuckGo press release search failed for %s: %s", ticker_clean, exc)
        if ticker_clean == "NVDA":
            return _nvidia_candidate_urls()[0]
        return None

    if response.status_code != 200:
        logger.warning("DuckDuckGo press release search returned HTTP %s for %s", response.status_code, ticker_clean)
        if ticker_clean == "NVDA":
            return _nvidia_candidate_urls()[0]
        return None

    for url in _extract_search_urls(response.text):
        if ticker_clean == "NVDA" and "nvidianews.nvidia.com" not in url.lower():
            continue
        return url

    return _nvidia_candidate_urls()[0] if ticker_clean == "NVDA" else None


def _money_to_int(match: re.Match[str], *, default_unit: Optional[str] = None) -> int:
    raw_value, raw_unit = match.groups()
    value = float(raw_value.replace(",", ""))
    unit = (raw_unit or default_unit or "").lower()
    if unit in {"billion", "bn", "b"}:
        return int(value * 1_000_000_000)
    if unit in {"million", "m"} or value < 1_000_000:
        return int(value * 1_000_000)
    return int(value)


def _first_money(text: str, *, default_unit: Optional[str] = None) -> Optional[int]:
    match = _MONEY_RE.search(text)
    if not match:
        return None
    return _money_to_int(match, default_unit=default_unit)


def _looks_like_segment_label(label: str) -> bool:
    label = re.sub(r"\s+", " ", label).strip(" :-")
    if not label or len(label) > 70:
        return False
    if any(ch.isdigit() for ch in label):
        return False
    if _GENERIC_SEGMENT_RE.match(label):
        return False
    lowered = label.lower()
    if any(token in lowered for token in (
        "margin", "income", "expense", "cash", "share", "tax",
        "cost", "profit", "loss", "asset", "property", "equipment",
        "goodwill", "intangible", "depreciation", "amortization",
        "liabilit", "payable", "receivable", "debt", "equity",
        "stock-based", "restructuring", "acquisition", "interest",
        "basic", "diluted", "weighted", "shares", "outstanding",
    )):
        return False
    return True


def _extract_revenue(text: str) -> Optional[int]:
    patterns = (
        r"(?:quarterly\s+)?revenue\s+(?:was|of|for .*? was|for .*? of)\s+(\$?\s*\d[\d,]*(?:\.\d+)?\s*(?:billion|million|bn|m|b)?)",
        r"reported\s+revenue\s+of\s+(\$?\s*\d[\d,]*(?:\.\d+)?\s*(?:billion|million|bn|m|b)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            money_match = _MONEY_RE.search(match.group(1))
            if money_match:
                return _money_to_int(money_match)
    return None


def _extract_segments_from_tables(tables: List[List[List[str]]]) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for table in tables:
        table_text = " ".join(" ".join(row) for row in table)
        default_unit = "million" if re.search(r"\bin millions\b|millions", table_text, re.IGNORECASE) else None
        for row in table:
            if len(row) < 2:
                continue
            name = re.sub(r"\s+", " ", row[0]).strip()
            if not _looks_like_segment_label(name):
                continue
            amount = _first_money(" ".join(row[1:]), default_unit=default_unit)
            if amount is None:
                continue
            key = name.lower()
            if key in seen:
                continue
            segments.append({
                "name": name,
                "revenue_quarterly": amount,
                "source": "Press release",
            })
            seen.add(key)

    return segments


def _extract_guidance(text: str) -> Dict[str, Any]:
    match = re.search(r"(?:outlook|guidance)(.{0,1800})", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return {}
    snippet = re.sub(r"\s+", " ", match.group(0)).strip()
    guidance: Dict[str, Any] = {"text": snippet[:1200]}
    revenue_match = re.search(r"revenue\s+(?:is\s+)?expected\s+to\s+be\s+(\$?\s*\d[\d,]*(?:\.\d+)?\s*(?:billion|million|bn|m|b)?)", snippet, re.IGNORECASE)
    if revenue_match:
        money_match = _MONEY_RE.search(revenue_match.group(1))
        if money_match:
            guidance["revenue"] = _money_to_int(money_match)
    margin_match = re.search(r"gross margins?.{0,80}?(\d+(?:\.\d+)?)\s*%", snippet, re.IGNORECASE)
    if margin_match:
        guidance["gross_margin_pct"] = float(margin_match.group(1))
    return guidance


def _extract_gaap_non_gaap_tables(tables: List[List[List[str]]]) -> List[List[List[str]]]:
    selected: List[List[List[str]]] = []
    for table in tables:
        table_text = " ".join(" ".join(row) for row in table).lower()
        if "gaap" in table_text and "non-gaap" in table_text:
            selected.append(table)
    return selected


def fetch_press_release_data(
    url: str,
    *,
    ticker: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch a press release and extract revenue, segment, guidance, and GAAP table data."""
    response = _fetch_url(url, timeout=20)
    if response is None:
        return {"source": "Press release", "url": url, "error": "fetch_failed"}

    html_text = response.text
    ticker_clean = ticker.strip().upper() if isinstance(ticker, str) and ticker.strip() else None
    if ticker_clean and output_dir:
        filing_dir = os.path.join(output_dir, "02_sec_or_regulatory_filings")
        os.makedirs(filing_dir, exist_ok=True)
        raw_path = os.path.join(filing_dir, f"press_release_{ticker_clean}.html")
        with open(raw_path, "w", encoding="utf-8") as handle:
            handle.write(html_text)
    else:
        raw_path = None

    parser = _parse_html(html_text)
    text = parser.text

    return {
        "source": "Press release",
        "url": str(response.url),
        "raw_html_path": raw_path,
        "revenue": _extract_revenue(text),
        "product_segments": _extract_segments_from_tables(parser.tables),
        "guidance": _extract_guidance(text),
        "gaap_non_gaap_tables": _extract_gaap_non_gaap_tables(parser.tables),
    }


def fetch_press_release_for_ticker(ticker: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """Find and fetch the latest earnings press release for a ticker."""
    url = find_press_release_url(ticker)
    if not url:
        return {"source": "Press release", "url": None, "error": "not_found"}
    return fetch_press_release_data(url, ticker=ticker, output_dir=output_dir)
