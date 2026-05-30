"""
StockAnalysis.com transcript fetcher — FREE, no API key required.
Fetches full earnings call transcripts from stockanalysis.com/stocks/{ticker}/transcripts/
"""

import re
import logging
from typing import Optional, Dict, List
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

BASE = "https://stockanalysis.com"


def _fetch_page(url: str) -> Optional[str]:
    """Fetch a page with browser-like headers."""
    from backend.http_client import http
    try:
        resp = http.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/135.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }, timeout=30)
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        logger.debug(f"StockAnalysis fetch failed: {e}")
    return None


def search_transcripts(ticker: str, limit: int = 5) -> List[Dict]:
    """
    Search StockAnalysis.com for earnings call transcripts.
    Returns list of {title, url, date} dicts — FREE, no auth needed.
    """
    ticker_lower = ticker.lower()
    url = f"{BASE}/stocks/{ticker_lower}/transcripts/"
    
    html = _fetch_page(url)
    if not html:
        return []
    
    results = []
    # Extract transcript links: href="/stocks/{ticker}/transcripts/{id}-{slug}/"
    pattern = rf'href="(/stocks/{re.escape(ticker_lower)}/transcripts/(\d+)-[^"]+/)"'
    seen = set()
    for match in re.finditer(pattern, html):
        href = match.group(1)
        transcript_id = match.group(2)
        if transcript_id in seen:
            continue
        seen.add(transcript_id)
        
        results.append({
            "title": "",  # Will be filled when fetching individual transcript
            "url": urljoin(BASE, href),
            "id": transcript_id,
            "source": "Seeking Alpha",  # Canonical source — StockAnalysis republishes SA transcripts verbatim
        })
        if len(results) >= limit:
            break
    
    logger.info(f"StockAnalysis: {len(results)} transcripts found for {ticker}")
    return results


def fetch_transcript(url: str) -> Optional[Dict]:
    """
    Fetch full transcript text from a StockAnalysis.com transcript page.
    Returns {title, content, date, speakers} dict or None.
    """
    html = _fetch_page(url)
    if not html:
        return None
    
    # Extract title
    title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    title = title_match.group(1).strip() if title_match else ""
    
    # Extract date
    date_match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
    if not date_match:
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', html)
    date = date_match.group(1) if date_match else ""
    
    # Extract transcript content — StockAnalysis uses a Svelte SSR page
    # The content is embedded in JSON-LD or in the page body
    content = ""
    
    # Try JSON-LD first
    ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    if ld_match:
        import json
        try:
            ld = json.loads(ld_match.group(1))
            if isinstance(ld, list):
                for item in ld:
                    if isinstance(item, dict) and item.get("@type") == "Article":
                        content = item.get("articleBody", "")
                        break
        except Exception:
            pass
    
    # Fallback: extract from page text between title and footer
    if not content:
        # Remove scripts/styles
        clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL)
        clean = re.sub(r'<nav[^>]*>.*?</nav>', '', clean, flags=re.DOTALL)
        clean = re.sub(r'<header[^>]*>.*?</header>', '', clean, flags=re.DOTALL)
        clean = re.sub(r'<footer[^>]*>.*?</footer>', '', clean, flags=re.DOTALL)
        # Extract text from remaining HTML
        text = re.sub(r'<[^>]+>', '\n', clean)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()
        if len(text) > 500:
            content = text
    
    if not content or len(content) < 200:
        logger.debug(f"StockAnalysis: insufficient content ({len(content)} chars) for {url}")
        return None
    
    logger.info(f"StockAnalysis transcript: {len(content)} chars from {url[:80]}")
    return {
        "title": title,
        "content": content,
        "date": date,
        "url": url,
        "source": "Seeking Alpha",  # Canonical source — StockAnalysis republishes SA transcripts verbatim
    }
