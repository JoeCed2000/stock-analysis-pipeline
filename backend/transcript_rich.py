"""Earnings call transcript finder — web search + text extraction."""
import os
import re
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


def find_transcripts_rich(ticker: str, output_dir: str) -> Dict[str, Any]:
    """Search for earnings call transcripts and save the best match.
    
    Returns a dict with:
        - found: bool
        - text: extracted transcript text (or empty)
        - url: source URL
        - local_path: path to saved transcript file
    """
    result: Dict[str, Any] = {
        "found": False,
        "text": "",
        "url": "",
        "local_path": "",
        "error": "",
    }

    # Strategy 1: Try Alpha Vantage earnings endpoint (has call summaries)
    text = _try_alpha_vantage_earnings(ticker)
    if text and len(text) > 200:
        result["found"] = True
        result["text"] = text
        result["url"] = "https://www.alphavantage.co/"
        result = _save_transcript(result, ticker, output_dir, "alphavantage")
        return result

    # Strategy 2: Web search for public transcripts (Seeking Alpha, Motley Fool, etc.)
    text, url = _try_web_search_transcript(ticker)
    if text and len(text) > 200:
        result["found"] = True
        result["text"] = text
        result["url"] = url
        result = _save_transcript(result, ticker, output_dir, "web_search")
        return result

    result["error"] = "No transcript found — premium sources may be paywalled"
    return result


def _try_alpha_vantage_earnings(ticker: str) -> str:
    """Try Alpha Vantage earnings endpoint for recent call data."""
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    if not api_key:
        return ""

    import requests
    try:
        resp = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "EARNINGS",
                "symbol": ticker,
                "apikey": api_key,
            },
            timeout=10
        )
        if resp.status_code != 200:
            return ""

        data = resp.json()
        if "Information" in data or "Note" in data:
            logger.info(f"Alpha Vantage rate-limited for {ticker}")
            return ""

        quarterly = data.get("quarterlyEarnings", [])
        if not quarterly:
            return ""

        # Build a text summary from the latest 4 quarters
        lines = [f"=== {ticker} Earnings History ===\n"]
        for q in quarterly[:4]:
            reported = q.get("reportedDate", "N/A")
            eps_est = q.get("estimatedEPS", "N/A")
            eps_act = q.get("reportedEPS", "N/A")
            surprise = q.get("surprise", "N/A")
            surprise_pct = q.get("surprisePercentage", "N/A")
            lines.append(
                f"Q {reported}: EPS est={eps_est} act={eps_act} "
                f"surprise={surprise} ({surprise_pct})"
            )

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Alpha Vantage earnings failed for {ticker}: {e}")
        return ""


def _try_web_search_transcript(ticker: str) -> tuple:
    """Search the web for public earnings call transcripts."""
    import requests

    queries = [
        f"{ticker} earnings call transcript Q1 2026 site:seekingalpha.com",
        f"{ticker} earnings call transcript 2026 site:fool.com",
        f"{ticker} Q1 2026 earnings call transcript",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; StockAnalysisPipeline/1.0; +https://stock-analysis.example.com)"
    }

    for query in queries[:1]:  # Just try first query for speed
        try:
            # Use DuckDuckGo instant answer API (no API key needed, rate-limited to ~30/min)
            resp = requests.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1},
                headers=headers,
                timeout=10
            )
            if resp.status_code != 200:
                continue

            data = resp.json()
            abstract = data.get("AbstractText", "")
            results = data.get("Results", [])

            if abstract and len(abstract) > 100:
                return abstract, data.get("AbstractURL", "")

            # Try related topics
            related = data.get("RelatedTopics", [])
            for topic in related[:3]:
                text = topic.get("Text", "")
                url = topic.get("FirstURL", "")
                if "earnings" in text.lower() or "transcript" in text.lower():
                    return text, url

        except Exception as e:
            logger.debug(f"Web search failed for '{query}': {e}")
            continue

    return "", ""


def _save_transcript(result: Dict, ticker: str, output_dir: str, source: str) -> Dict:
    """Save transcript text to file."""
    trans_dir = os.path.join(output_dir, "04_transcripts_and_management")
    os.makedirs(trans_dir, exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"transcript_{ticker}_{source}_{date_str}.txt"
    local_path = os.path.join(trans_dir, filename)

    with open(local_path, "w") as f:
        f.write(f"Source: {result['url']}\n")
        f.write(f"Ticker: {ticker}\n")
        f.write(f"Date: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"{'='*60}\n\n")
        f.write(result["text"])

    result["local_path"] = local_path
    logger.info(f"Transcript saved: {local_path} ({len(result['text'])} chars)")
    return result
