"""Seeking Alpha scraper — fetches earnings call transcripts and news."""
import re
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Seeking Alpha requires a more sophisticated approach.
# We'll use the public RSS feeds and article search.


def search_seeking_alpha(ticker: str, limit: int = 5) -> List[Dict]:
    """
    Search Seeking Alpha for recent articles about a ticker.
    Uses public RSS feed — no auth required.
    Returns list of {title, url, date, summary} dicts.
    """
    import requests
    from xml.etree import ElementTree

    results = []
    try:
        # Seeking Alpha RSS feed for ticker news
        url = f"https://seekingalpha.com/api/sa/combined/{ticker}.xml"
        resp = requests.get(
            url,
            headers={"User-Agent": "StockAnalysisPipeline/1.0"},
            timeout=10
        )
        if resp.status_code == 200:
            root = ElementTree.fromstring(resp.content)
            for item in root.findall(".//item")[:limit]:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")
                description = item.findtext("description", "")
                # Strip HTML from description
                desc_clean = re.sub(r'<[^>]+>', '', description)[:300] if description else ""
                results.append({
                    "title": title,
                    "url": link,
                    "date": pub_date,
                    "summary": desc_clean,
                })
    except Exception as e:
        logger.warning(f"Seeking Alpha RSS failed for {ticker}: {e}")

    return results


def search_earnings_transcript(ticker: str) -> Optional[Dict]:
    """
    Search for the latest earnings call transcript on Seeking Alpha.
    Note: Full transcript access may require authentication.
    Returns {title, url, snippet} or None.
    """
    import requests

    try:
        # Search for earnings transcript
        search_url = f"https://seekingalpha.com/symbol/{ticker}/earnings/transcripts"
        resp = requests.get(
            search_url,
            headers={"User-Agent": "StockAnalysisPipeline/1.0"},
            timeout=10
        )
        if resp.status_code == 200:
            # Extract transcript links from the page
            # The page contains links to individual transcript pages
            transcript_links = re.findall(
                r'href="(/article/\d+[^"]*earnings[^"]*transcript[^"]*)"',
                resp.text, re.IGNORECASE
            )
            if transcript_links:
                return {
                    "title": "Latest Earnings Call Transcript",
                    "url": f"https://seekingalpha.com{transcript_links[0]}",
                    "snippet": "Earnings call transcript available on Seeking Alpha (requires login for full access)"
                }
    except Exception as e:
        logger.warning(f"Seeking Alpha transcript search failed for {ticker}: {e}")

    return None


# Fallback: search for transcripts via web search
def search_transcript_web(ticker: str) -> List[Dict]:
    """
    Search the web for earnings call transcripts using public sources.
    Checks Fool.com, MarketBeat, and other free transcript providers.
    """
    results = []

    # The Motley Fool has free transcripts
    try:
        import requests
        url = f"https://www.fool.com/earnings/call-transcripts/{ticker.lower()}/"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if resp.status_code == 200 and "transcript" in resp.text.lower():
            # Find transcript links
            links = re.findall(r'href="(/earnings/call-transcripts/[^"]+)"', resp.text)
            for link in links[:3]:
                results.append({
                    "title": f"{ticker} Earnings Call Transcript",
                    "url": f"https://www.fool.com{link}",
                    "source": "The Motley Fool",
                    "free": True
                })
    except Exception:
        pass

    return results
