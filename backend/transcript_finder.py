"""Transcript source integration — RapidAPI Seeking Alpha + Alpha Vantage + Fool.com."""
import os
import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def find_transcripts(ticker: str, output_dir: str = "") -> Dict[str, Any]:
    """
    Search for earnings call transcripts from configured sources.
    Returns {'sources': [...], 'found': bool}
    Saves results to 04_transcripts_and_management/ if output_dir provided.
    """
    results = []
    primary_text = ""  # Full transcript text from primary source

    # 0. RapidAPI Seeking Alpha — primary full-text source.
    try:
        from backend.rapidapi_sa import fetch_sa_transcript, search_sa_transcripts

        for transcript in search_sa_transcripts(ticker)[:3]:
            transcript_id = transcript.get("id", "")
            if not transcript_id:
                continue

            details = fetch_sa_transcript(transcript_id)
            content = details.get("content", "") if details else ""
            if not content:
                continue

            primary_text = content
            results.append({
                "source": "RapidAPI Seeking Alpha",
                "type": "earnings_transcript",
                "title": details.get("title") or transcript.get("title", ""),
                "url": details.get("url") or transcript.get("url", ""),
                "text": content,
                "text_length": len(content),
                "quarter": details.get("quarter") or transcript.get("quarter", ""),
                "date": details.get("date") or transcript.get("date", ""),
                "id": details.get("id") or transcript_id,
            })
            logger.info(f"RapidAPI Seeking Alpha transcript: {len(content)} chars for {ticker}")
            break
    except Exception as e:
        logger.warning(f"RapidAPI Seeking Alpha unavailable for {ticker}: {e}")

    # 1. Alpha Vantage API — fallback (structured JSON, 25 req/day free).
    if not primary_text:
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
                    "text": av["content"],
                    "text_length": len(av["content"]),
                    "quarter": av.get("quarter", ""),
                    "date": av.get("date", ""),
                    "id": "",
                })
                logger.info(f"Alpha Vantage transcript: {len(av['content'])} chars for {ticker}")
        except Exception as e:
            logger.warning(f"Alpha Vantage unavailable for {ticker}: {e}")
    else:
        logger.info(f"Skipping Alpha Vantage — RapidAPI Seeking Alpha already provided {len(primary_text)} chars")

    # 2. Motley Fool transcripts — last resort if structured sources failed.
    if not primary_text:
        try:
            from backend.sources.motleyfool import get_transcript as get_fool_transcript

            fool = get_fool_transcript(ticker)
            if fool and fool.get("text"):
                primary_text = fool["text"]
                results.append({
                    "source": "The Motley Fool",
                    "type": "earnings_transcript",
                    "title": f"{ticker} Earnings Call Transcript",
                    "url": fool.get("url", ""),
                    "text": primary_text,
                    "text_length": len(primary_text),
                    "quarter": "",
                    "date": fool.get("date", ""),
                    "id": "",
                })
                logger.info(f"Motley Fool transcript: {len(primary_text)} chars for {ticker}")
        except Exception as e:
            logger.warning(f"Motley Fool unavailable for {ticker}: {e}")
    else:
        logger.info(f"Skipping Fool.com — higher-priority source already provided {len(primary_text)} chars")

    # Save to disk if output_dir provided
    if output_dir and results:
        trans_dir = os.path.join(output_dir, "04_transcripts_and_management")
        os.makedirs(trans_dir, exist_ok=True)
        path = os.path.join(trans_dir, f"transcript_sources_{ticker}.json")
        with open(path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Transcript sources saved: {path}")

    return {"sources": results, "found": len(results) > 0}
