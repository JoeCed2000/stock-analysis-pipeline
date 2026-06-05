"""StockAnalysis.com transcript fetcher — FREE, no API key required.
Fetches full earnings call transcripts from stockanalysis.com/stocks/{ticker}/transcripts/

IMPORTANT: Filters out non-earnings-call events (keynotes, conferences, summits)
so the deep dive generator gets real financial call transcripts.
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


def _is_earnings_call_title(title: str) -> bool:
    """Check if a transcript title looks like an earnings call (not a keynote/conference/summit)."""
    title_lower = title.lower()
    # Must contain a quarter indicator (Q1-Q4)
    if not re.search(r'\bq[1-4]\b', title_lower):
        return False
    # Exclude known non-earnings event patterns
    exclude = [
        'keynote', 'conference', 'summit', 'i/o ', "i/o'",
        'google cloud next', 'developer', 'opening', 'm&a announcement',
    ]
    for ex in exclude:
        if ex in title_lower:
            return False
    return True


def search_transcripts(ticker: str, limit: int = 5) -> List[Dict]:
    """Search StockAnalysis.com for earnings call transcripts.
    Only returns actual earnings calls (Q1-Q4), filtering out keynotes and conferences.
    """
    ticker_lower = ticker.lower()
    url = f"{BASE}/stocks/{ticker_lower}/transcripts/"
    
    html = _fetch_page(url)
    if not html:
        return []
    
    results = []
    # Extract transcript links WITH title text: <a href="...">Title Text</a>
    pattern = (
        r'<a\b[^>]*\bhref\s*=\s*"'
        r'(/stocks/' + re.escape(ticker_lower) + r'/transcripts/(\d+)-[^"]+/)"'
        r'[^>]*>([^<]+)</a>'
    )
    seen = set()
    for match in re.finditer(pattern, html, re.IGNORECASE):
        href = match.group(1)
        transcript_id = match.group(2)
        title = match.group(3).strip()
        
        if transcript_id in seen:
            continue
        
        # Filter: only actual earnings calls
        if not _is_earnings_call_title(title):
            logger.debug(f"StockAnalysis: skipping non-earnings transcript #{transcript_id}: {title}")
            continue
        
        seen.add(transcript_id)
        results.append({
            "title": title,
            "url": urljoin(BASE, href),
            "id": transcript_id,
            "source": "Seeking Alpha",  # Canonical source — StockAnalysis republishes SA transcripts verbatim
        })
        if len(results) >= limit:
            break
    
    logger.info(
        f"StockAnalysis: {len(results)} earnings-call transcripts found for {ticker} "
        f"(filtered from listing page)"
    )
    return results


def fetch_transcript(url: str) -> Optional[Dict]:
    """Fetch full transcript text from a StockAnalysis.com transcript page."""
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
        clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL)
        clean = re.sub(r'<nav[^>]*>.*?</nav>', '', clean, flags=re.DOTALL)
        clean = re.sub(r'<header[^>]*>.*?</header>', '', clean, flags=re.DOTALL)
        clean = re.sub(r'<footer[^>]*>.*?</footer>', '', clean, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', '\n', clean)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()
        if len(text) > 500:
            content = text
    
    if not content or len(content) < 200:
        logger.debug(f"StockAnalysis: insufficient content ({len(content)} chars) for {url}")
        return None
    
    logger.info(f"StockAnalysis transcript: {len(content)} chars from {url[:80]}")
    
    # Extract original Seeking Alpha article URL from the page
    sa_url = ""
    sa_link = re.search(r'<a[^>]*href="(https://seekingalpha\.com/article/\d+[^"]*)"[^>]*>', html)
    if not sa_link:
        sa_link = re.search(r'href="(https://seekingalpha\.com/article/\d+[^"]*)"', html)
    if sa_link:
        sa_url = sa_link.group(1)
        logger.info(f"StockAnalysis: found SA original URL: {sa_url[:80]}")
    
    return {
        "title": title,
        "content": content,
        "date": date,
        "url": sa_url or url,  # Prefer the concrete SA article; otherwise cite StockAnalysis fallback.
        "stockanalysis_url": url,
        "source": "Seeking Alpha" if sa_url else "StockAnalysis",
        "retrieval_provider": "StockAnalysis",
    }
