"""
Preload store — writes structured data to analyses/preload/{TICKER}/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

PRELOAD_ROOT = Path(__file__).parent.parent.parent / "analyses" / "preload"


def _ticker_dir(ticker: str) -> Path:
    d = PRELOAD_ROOT / ticker.upper()
    d.mkdir(parents=True, exist_ok=True)
    return d


def ticker_dir(ticker: str) -> Path:
    """Public accessor for ticker directory (used by scheduler)."""
    return _ticker_dir(ticker)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def save_financials(ticker: str, data: Dict) -> str:
    """Save yfinance financial data (5 years quarterly)."""
    path = _ticker_dir(ticker) / "normalized" / "financials.json"
    _write_json(path, data)
    return str(path)


def save_transcript(ticker: str, text: str, source: str, url: str = "",
                    quarter: str = "", date: str = "") -> str:
    """Save a raw transcript text file."""
    raw_dir = _ticker_dir(ticker) / "raw" / "transcripts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    safe_source = source.lower().replace(" ", "_")[:30]
    stamp = quarter or date or datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"{stamp}_{safe_source}.txt"
    path = raw_dir / filename
    
    with open(path, "w") as f:
        f.write(f"Source: {source}\nURL: {url}\nQuarter: {quarter}\nDate: {date}\n")
        f.write("=" * 60 + "\n\n")
        f.write(text)
    
    # Update transcript index
    idx = _read_transcript_index(ticker)
    idx.append({
        "filename": filename,
        "source": source,
        "url": url,
        "quarter": quarter,
        "date": date,
        "chars": len(text),
        "collected_at": datetime.now(timezone.utc).isoformat(),
    })
    _write_json(_ticker_dir(ticker) / "normalized" / "transcript_index.json", idx)
    
    return str(path)


def _read_transcript_index(ticker: str) -> list:
    path = _ticker_dir(ticker) / "normalized" / "transcript_index.json"
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_sec_filing(ticker: str, filing_type: str, data: Dict) -> str:
    """Save SEC filing metadata/JSON."""
    raw_dir = _ticker_dir(ticker) / "raw" / "sec"
    raw_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = raw_dir / f"{stamp}_{filing_type}.json"
    _write_json(path, data)
    return str(path)


def save_press_release(ticker: str, data: Dict) -> str:
    """Save press release metadata + content."""
    raw_dir = _ticker_dir(ticker) / "raw" / "press_releases"
    raw_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = raw_dir / f"{stamp}.json"
    _write_json(path, data)
    return str(path)


def save_earnings_calendar(ticker: str, data: Dict) -> str:
    """Save earnings dates/history."""
    path = _ticker_dir(ticker) / "normalized" / "earnings_calendar.json"
    _write_json(path, data)
    return str(path)


def save_ir_page(ticker: str, html: str, url: str = "") -> str:
    """Save raw investor relations page HTML."""
    raw_dir = _ticker_dir(ticker) / "raw" / "ir"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / "investor_relations.html"
    with open(path, "w") as f:
        f.write(f"<!-- URL: {url} -->\n")
        f.write(f"<!-- Collected: {datetime.now(timezone.utc).isoformat()} -->\n")
        f.write(html)
    return str(path)


def save_audio(ticker: str, audio_data: bytes, source: str, url: str = "",
               quarter: str = "", date: str = "") -> str:
    """Save earnings call audio file (MP3/M4A)."""
    raw_dir = _ticker_dir(ticker) / "raw" / "audio"
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    safe_source = source.lower().replace(" ", "_")[:20]
    stamp = quarter or date or datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"{stamp}_{safe_source}.mp3"
    path = raw_dir / filename
    
    with open(path, "wb") as f:
        f.write(audio_data)
    
    return str(path)


def update_manifest(ticker: str, **fields) -> str:
    """Update the ticker manifest with latest collection status."""
    path = _ticker_dir(ticker) / "manifest.json"
    manifest = {}
    if path.exists():
        try:
            with open(path) as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    
    manifest.setdefault("ticker", ticker)
    manifest["last_full_refresh"] = datetime.now(timezone.utc).isoformat()
    manifest.update(fields)
    
    _write_json(path, manifest)
    return str(path)


def get_manifest(ticker: str) -> Dict:
    """Read the manifest for a ticker."""
    path = _ticker_dir(ticker) / "manifest.json"
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"ticker": ticker, "status": "not_collected"}
