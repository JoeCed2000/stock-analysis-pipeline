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
    from backend.http_client import http
    from xml.etree import ElementTree

    results = []
    try:
        # Seeking Alpha RSS feed for ticker news
        url = f"https://seekingalpha.com/api/sa/combined/{ticker}.xml"
        resp = http.get(
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
    from backend.http_client import http

    try:
        # Search for earnings transcript
        search_url = f"https://seekingalpha.com/symbol/{ticker}/earnings/transcripts"
        resp = http.get(
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


def fetch_fool_transcript(url: str) -> str:
    """
    Fetch and extract the actual transcript text from a Fool.com transcript page.
    Returns the clean text content or empty string on failure.
    """
    from backend.http_client import http
    try:
        # Fetch the transcript page
        resp = http.get(
            url,
            headers={"User-Agent": "StockAnalysisPipeline/1.0"},
            timeout=15
        )
        if resp.status_code != 200:
            logger.warning(f"Failed to fetch Fool.com transcript: {resp.status_code}")
            return ""

        # Extract the article content using regex patterns
        content = resp.text
        
        # Try to find the main article content
        # Look for common article content patterns
        patterns = [
            r'<div[^>]*class="[^"]*article-content[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*id="[^"]*article-content[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*article-body[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*transcript[^"]*"[^>]*>(.*?)</div>',
            r'<article[^>]*>(.*?)</article>',
        ]
        
        # Try each pattern to extract content
        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                content_text = match.group(1)
                # Clean HTML tags
                clean_text = re.sub(r'<[^>]+>', '', content_text)
                # Remove extra whitespace
                clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                return clean_text
        
        # Fallback: if no specific content area found, try to get content from the full page
        # First try to find the article content section
        article_match = re.search(r'<article[^>]*>(.*?)</article>', content, re.DOTALL | re.IGNORECASE)
        if article_match:
            article_content = article_match.group(1)
            # Clean HTML tags
            clean_text = re.sub(r'<[^>]+>', '', article_content)
            # Remove extra whitespace
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            return clean_text
            
        # If no article tag found, try to get body content
        body_match = re.search(r'<body[^>]*>(.*?)</body>', content, re.DOTALL | re.IGNORECASE)
        if body_match:
            body_content = body_match.group(1)
            # Clean HTML tags
            clean_text = re.sub(r'<[^>]+>', '', body_content)
            # Remove extra whitespace
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            return clean_text
            
        # Last resort: return cleaned version of full content
        clean_text = re.sub(r'<[^>]+>', '', content)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        return clean_text[:2000] if clean_text else ""
            
    except Exception as e:
        logger.warning(f"Failed to fetch/parse Fool.com transcript from {url}: {e}")
        return ""


# Fallback: search for transcripts via web search
def search_transcript_web(ticker: str) -> List[Dict]:
    """
    Search the web for earnings call transcripts using public sources.
    Checks Fool.com, MarketBeat, and other free transcript providers.
    """
    results = []

    # The Motley Fool has free transcripts
    try:
        from backend.http_client import http
        url = f"https://www.fool.com/earnings/call-transcripts/{ticker.lower()}/"
        resp = http.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if resp.status_code == 200 and "transcript" in resp.text.lower():
            # Find transcript links
            links = re.findall(r'href="(/earnings/call-transcripts/[^"]+)"', resp.text)
            if links:
                # Get the first link and fetch its transcript text
                first_link = f"https://www.fool.com{links[0]}"
                transcript_text = fetch_fool_transcript(first_link)
                results.append({
                    "title": f"{ticker} Earnings Call Transcript",
                    "url": first_link,
                    "source": "The Motley Fool",
                    "free": True,
                    "text": transcript_text if transcript_text else ""
                })
                # Add additional links without text to keep consistent with current behavior
                for link in links[1:3]:  # Only process a few more links
                    results.append({
                        "title": f"{ticker} Earnings Call Transcript",
                        "url": f"https://www.fool.com{link}",
                        "source": "The Motley Fool",
                        "free": True,
                        "text": ""
                    })
    except Exception as e:
        logger.warning(f"Failed to search Fool.com transcripts: {e}")
        pass

    return results
