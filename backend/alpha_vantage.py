"""Alpha Vantage API wrapper — earnings call transcripts (free tier: 25 req/day)."""
import os
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

AV_BASE = "https://www.alphavantage.co/query"


def get_api_key() -> str:
    """Get Alpha Vantage API key from environment."""
    key = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    if not key:
        logger.warning("ALPHA_VANTAGE_API_KEY not set — Alpha Vantage disabled")
    return key


def fetch_transcript(ticker: str, quarter: Optional[str] = None) -> Optional[Dict]:
    """
    Fetch earnings call transcript from Alpha Vantage.
    
    Args:
        ticker: Stock symbol (e.g., NVDA, MSFT, AAPL)
        quarter: Optional quarter filter (e.g., '2025Q4'). If None, returns latest.
    
    Returns:
        {
            'symbol': str,
            'quarter': str,
            'year': int,
            'date': str,
            'content': str,        # Full transcript text
            'source': 'alpha_vantage',
            'error': str | None
        }
        or None if API key not set or request failed.
    """
    import requests

    api_key = get_api_key()
    if not api_key:
        return None

    params = {
        "function": "EARNINGS_CALL_TRANSCRIPT",
        "symbol": ticker.upper(),
        "apikey": api_key,
    }
    if quarter:
        params["quarter"] = quarter

    try:
        resp = requests.get(AV_BASE, params=params, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Alpha Vantage HTTP {resp.status_code} for {ticker}")
            return None

        data = resp.json()

        # Check for rate limit or error messages
        if "Information" in data:
            logger.warning(f"Alpha Vantage rate limit: {data['Information'][:100]}")
            return None
        if "Error Message" in data:
            logger.warning(f"Alpha Vantage error for {ticker}: {data['Error Message']}")
            return None

        # The API returns different formats:
        # - Newer format: {"data": [{"content": "...", ...}]}
        # - Older format: {"symbol": "...", "quarter": "...", "transcript": [...]}
        # - String format: {"symbol": "...", "content": "..."}
        
        transcripts = data.get("data", [])
        
        # Single-object format (no "data" wrapper)
        if not transcripts and "symbol" in data:
            transcripts = [data]

        if not transcripts:
            logger.info(f"No transcripts found for {ticker} on Alpha Vantage")
            return None

        # Take the latest transcript
        latest = transcripts[0]
        
        # Extract content from various possible fields
        content = latest.get("content", "")
        if not content:
            transcript_val = latest.get("transcript", "")
            if isinstance(transcript_val, list):
                # Array of speaker segments — join them
                parts = []
                for seg in transcript_val:
                    if isinstance(seg, dict):
                        speaker = seg.get("speaker", "")
                        text = seg.get("text", seg.get("content", ""))
                        if text:
                            parts.append(f"{speaker}: {text}" if speaker else text)
                    elif isinstance(seg, str):
                        parts.append(seg)
                content = "\n".join(parts)
            elif isinstance(transcript_val, str):
                content = transcript_val

        if not content or len(content.strip()) < 100:
            logger.warning(f"Alpha Vantage transcript for {ticker} too short or empty "
                          f"(len={len(content)}, keys={list(latest.keys())})")
            return None

        return {
            "symbol": latest.get("symbol", ticker),
            "quarter": latest.get("quarter", latest.get("fiscalQuarter", "")),
            "year": latest.get("year", 0),
            "date": latest.get("date", ""),
            "content": content,
            "source": "alpha_vantage",
            "error": None,
        }

    except requests.RequestException as e:
        logger.warning(f"Alpha Vantage network error for {ticker}: {e}")
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"Alpha Vantage parse error for {ticker}: {e}")

    return None


def fetch_latest_transcripts(tickers: List[str]) -> Dict[str, Optional[Dict]]:
    """
    Fetch latest transcript for multiple tickers.
    Respects 25 req/day rate limit — stops if quota reached.
    Returns {ticker: transcript_dict | None}
    """
    results = {}
    api_key = get_api_key()
    if not api_key:
        return {t: None for t in tickers}

    for ticker in tickers:
        transcript = fetch_transcript(ticker)
        results[ticker] = transcript
        if transcript and transcript.get("error"):
            break  # Rate limit hit — stop

    return results
