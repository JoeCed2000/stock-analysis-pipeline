"""Transcript source integration — Seeking Alpha + Motley Fool + web search."""
import os
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def find_transcripts(ticker: str, output_dir: str = "") -> Dict[str, any]:
    """
    Search for earnings call transcripts from free sources.
    Returns {'sources': [...], 'found': bool}
    Saves results to 04_transcripts_and_management/ if output_dir provided.
    """
    results = []
    primary_text = ""  # Full transcript text from primary source

    # 0. Alpha Vantage API — primary (structured JSON, 25 req/day free)
    try:
        from backend.alpha_vantage import fetch_transcript
        av = fetch_transcript(ticker)
        if av and av.get("content"):
            primary_text = av["content"]
            results.append({
                "source": "Alpha Vantage API",
                "type": "earnings_transcript",
                "title": f"{ticker} {av.get('quarter', '')} Earnings Call",
                "url": f"https://www.alphavantage.co/query?function=EARNINGS_CALL_TRANSCRIPT&symbol={ticker}",
                "text": av["content"][:8000],
                "text_length": len(av["content"]),
                "quarter": av.get("quarter", ""),
                "date": av.get("date", ""),
            })
            logger.info(f"Alpha Vantage transcript: {len(av['content'])} chars for {ticker}")
    except Exception as e:
        logger.warning(f"Alpha Vantage unavailable for {ticker}: {e}")

    # 1. Seeking Alpha RSS (links only, primary text from AV above)
    from backend.seeking_alpha import search_earnings_transcript, search_seeking_alpha
    sa_transcript = search_earnings_transcript(ticker)
    if sa_transcript:
        results.append({
            "source": "Seeking Alpha",
            "type": "earnings_transcript",
            "title": sa_transcript.get("title", ""),
            "url": sa_transcript.get("url", ""),
            "note": sa_transcript.get("snippet", ""),
        })

    # 2. Seeking Alpha articles (RSS)
    sa_articles = search_seeking_alpha(ticker, limit=3)
    for art in sa_articles:
        results.append({
            "source": "Seeking Alpha",
            "type": "article",
            "title": art.get("title", ""),
            "url": art.get("url", ""),
            "date": art.get("date", ""),
        })

    # 3. Motley Fool transcripts — fallback if Alpha Vantage failed
    if not primary_text:
        from backend.seeking_alpha import search_transcript_web, fetch_fool_transcript
        fool_results = search_transcript_web(ticker)
        for r in fool_results:
            url = r.get("url", "")
            # Attempt to fetch and extract full transcript text
            transcript_text = ""
            if url:
                try:
                    transcript_text = fetch_fool_transcript(url)
                    if transcript_text:
                        primary_text = transcript_text
                        logger.info(f"Fool.com transcript extracted: {len(transcript_text)} chars for {ticker}")
                except Exception as e:
                    logger.warning(f"Failed to fetch transcript text from {url}: {e}")
            results.append({
                "source": r.get("source", "Motley Fool"),
                "type": "earnings_transcript",
                "title": r.get("title", ""),
                "url": url,
                "free": r.get("free", True),
                "text": transcript_text[:5000] if transcript_text else "",
                "text_length": len(transcript_text) if transcript_text else 0,
            })
    else:
        logger.info(f"Skipping Fool.com — Alpha Vantage already provided {len(primary_text)} chars")

    # Save to disk if output_dir provided
    if output_dir and results:
        trans_dir = os.path.join(output_dir, "04_transcripts_and_management")
        os.makedirs(trans_dir, exist_ok=True)
        path = os.path.join(trans_dir, f"transcript_sources_{ticker}.json")
        with open(path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Transcript sources saved: {path}")

    return {"sources": results, "found": len(results) > 0}
