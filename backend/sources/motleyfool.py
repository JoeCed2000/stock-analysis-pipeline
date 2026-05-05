"""
Motley Fool Earnings Call Transcripts source.

Motley Fool publishes full earnings call transcripts (prepared remarks + Q&A)
with no paywall, no Cloudflare, and no authentication required.

URL pattern: https://www.fool.com/earnings/call-transcripts/{YYYY}/{MM}/{DD}/{slug}/

Strategy:
1. Try direct URL if provided
2. Search Bing for "ticker earnings call transcript fool.com"
3. Fall back gracefully — transcript is optional, not required
"""

import logging
import re
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

FOOL_TRANSCRIPT_BASE = "https://www.fool.com/earnings/call-transcripts"


def _extract_transcript(html: str) -> str:
    """Extract transcript text from Fool.com article HTML."""
    paragraphs = re.findall(r"<p[^>]*>\s*(.*?)\s*</p>", html, re.DOTALL)
    lines = []
    for p in paragraphs:
        clean = re.sub(r"<[^>]+>", " ", p).strip()
        clean = re.sub(r"\s+", " ", clean)
        if clean and len(clean) > 30:
            lines.append(clean)
    return "\n\n".join(lines)


def _search_bing(ticker: str) -> Optional[str]:
    """Search Bing for a Motley Fool transcript link."""
    query = f"{ticker}+earnings+call+transcript+fool.com"
    url = f"https://www.bing.com/search?q={query}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return None

        # Bing may embed results in JavaScript — search for any fool.com transcript URL
        pattern = rf'https?://www\.fool\.com/earnings/call-transcripts/[^\s"\'<>]+'
        matches = re.findall(pattern, r.text)
        if matches:
            # Prefer URLs containing the ticker
            ticker_lower = ticker.lower()
            for m in matches:
                if ticker_lower in m.lower():
                    return m
            # Fall back to first result
            return matches[0]

    except Exception as e:
        logger.error(f"Bing search failed for {ticker}: {e}")
    return None


def get_transcript(ticker: str, url: Optional[str] = None) -> Optional[dict]:
    """
    Fetch the latest earnings call transcript for a ticker from Motley Fool.

    Args:
        ticker: Stock ticker symbol
        url: Optional direct URL to the transcript page

    Returns dict with keys: 'source', 'ticker', 'url', 'text', 'date', 'participants'
    or None if not found.
    """
    transcript_url = url

    if not transcript_url:
        transcript_url = _search_bing(ticker)

    if not transcript_url:
        logger.warning(f"No Motley Fool transcript found for {ticker}")
        return None

    try:
        r = requests.get(transcript_url, timeout=20, headers={"User-Agent": "StockAnalysisPipeline/1.0"})
        if r.status_code != 200:
            logger.warning(f"Motley Fool transcript fetch failed: HTTP {r.status_code}")
            return None

        text = _extract_transcript(r.text)
        if not text or len(text) < 500:
            logger.warning(f"Motley Fool transcript too short for {ticker}: {len(text)} chars")
            return None

        # Extract date from URL: .../YYYY/MM/DD/...
        date_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", transcript_url)
        date_str = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}" if date_match else None

        # Try to extract participants from first few lines
        participants = ""
        first_lines = text[:2000]
        ceo_match = re.findall(r"(?:CEO|Chief Executive Officer)[:\s]+([^\.]+)", first_lines)
        cfo_match = re.findall(r"(?:CFO|Chief Financial Officer)[:\s]+([^\.]+)", first_lines)
        if ceo_match or cfo_match:
            parts = []
            if ceo_match:
                parts.append(f"CEO: {ceo_match[0].strip()}")
            if cfo_match:
                parts.append(f"CFO: {cfo_match[0].strip()}")
            participants = "; ".join(parts)

        return {
            "source": "motley_fool",
            "ticker": ticker,
            "url": transcript_url,
            "text": text,
            "date": date_str,
            "participants": participants,
        }

    except Exception as e:
        logger.error(f"Motley Fool transcript error for {ticker}: {e}")
        return None


# — Quick test —
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test with known Avista URL
    url = "https://www.fool.com/earnings/call-transcripts/2026/05/05/avista-ava-q1-2026-earnings-call-transcript/"
    result = get_transcript("AVA", url=url)
    if result:
        print(f"✅ Found: {result['url']}")
        print(f"   Date: {result['date']}")
        print(f"   Length: {len(result['text'])} chars")
        print(f"   Participants: {result['participants']}")
        print(f"   Preview:\n{result['text'][:400]}...")
    else:
        print("❌ Not found")

    # Test AAPL via search
    print("\n--- Searching for AAPL via Bing ---")
    result2 = get_transcript("AAPL")
    if result2:
        print(f"✅ Found: {result2['url']}")
        print(f"   Length: {len(result2['text'])} chars")
    else:
        print("⚠️  AAPL not found via search (may need JS rendering)")
