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

    # 1. Seeking Alpha RSS
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

    # 3. Motley Fool transcripts
    from backend.seeking_alpha import search_transcript_web
    fool_results = search_transcript_web(ticker)
    for r in fool_results:
        results.append({
            "source": r.get("source", "Motley Fool"),
            "type": "earnings_transcript",
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "free": r.get("free", True),
        })

    # Save to disk if output_dir provided
    if output_dir and results:
        trans_dir = os.path.join(output_dir, "04_transcripts_and_management")
        os.makedirs(trans_dir, exist_ok=True)
        path = os.path.join(trans_dir, f"transcript_sources_{ticker}.json")
        with open(path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Transcript sources saved: {path}")

    return {"sources": results, "found": len(results) > 0}
