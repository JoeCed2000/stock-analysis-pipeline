"""
Nami Feedback Store — persists text + files to analyses/{TICKER}/feedback/.

Design:
    analyses/{TICKER}/feedback/
        index.json       ← list of all feedback entries
        2026-05-10_143022.json  ← one entry per submission
        2026-05-10_143022_screenshot.png  ← attached files

Cron job reads index.json, processes new entries, marks them as processed.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import UploadFile

logger = logging.getLogger(__name__)
PARIS = __import__("zoneinfo").ZoneInfo("Europe/Paris")
ANALYSES_DIR = Path(__file__).parent.parent / "analyses"


def _feedback_dir(ticker: str) -> Path:
    """Get/create the feedback directory for a ticker."""
    d = ANALYSES_DIR / f"feedback_{ticker}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index_path(ticker: str) -> Path:
    return _feedback_dir(ticker) / "index.json"


def _read_index(ticker: str) -> List[Dict[str, Any]]:
    """Read the feedback index, or return empty list."""
    path = _index_path(ticker)
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _write_index(ticker: str, entries: List[Dict[str, Any]]) -> None:
    with open(_index_path(ticker), "w") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


async def save_feedback(
    ticker: str,
    text: str,
    files: List[UploadFile],
) -> Dict[str, Any]:
    """Save feedback text + uploaded files. Returns {ticker, id, files_saved}."""
    now = datetime.now(PARIS)
    entry_id = now.strftime("%Y-%m-%d_%H%M%S")
    fb_dir = _feedback_dir(ticker)

    # Save attached files
    files_saved = []
    for upload in (files or []):
        if not upload.filename:
            continue
        # Sanitize filename
        safe_name = f"{entry_id}_{upload.filename.replace(' ', '_')}"
        file_path = fb_dir / safe_name
        content = await upload.read()
        with open(file_path, "wb") as f:
            f.write(content)
        files_saved.append(safe_name)
        logger.info(f"[{ticker}] Feedback file saved: {safe_name} ({len(content)} bytes)")

    # Build entry
    entry = {
        "id": entry_id,
        "ticker": ticker,
        "submitted_at": now.isoformat(),
        "text": text.strip() if text else "",
        "files": files_saved,
        "processed": False,
        "processed_at": None,
        "notes": "",
    }

    # Append to index
    index = _read_index(ticker)
    index.append(entry)
    _write_index(ticker, index)

    logger.info(f"[{ticker}] Feedback saved: {entry_id} ({len(files_saved)} files, {len(text)} chars)")
    return {"ticker": ticker, "id": entry_id, "files_saved": len(files_saved)}


def list_feedback(ticker: str) -> Dict[str, Any]:
    """List all feedback for a ticker."""
    index = _read_index(ticker)
    return {
        "ticker": ticker,
        "total": len(index),
        "unprocessed": sum(1 for e in index if not e.get("processed")),
        "entries": index,
    }


def mark_processed(ticker: str, entry_id: str, notes: str = "") -> bool:
    """Mark a feedback entry as processed. Used by the cron job."""
    index = _read_index(ticker)
    for entry in index:
        if entry.get("id") == entry_id:
            entry["processed"] = True
            entry["processed_at"] = datetime.now(PARIS).isoformat()
            if notes:
                entry["notes"] = notes
            _write_index(ticker, index)
            logger.info(f"[{ticker}] Feedback {entry_id} marked as processed")
            return True
    return False


def get_unprocessed() -> List[Dict[str, Any]]:
    """Get all unprocessed feedback across all tickers. Used by the cron job."""
    unprocessed = []
    if not ANALYSES_DIR.exists():
        return unprocessed
    for d in ANALYSES_DIR.iterdir():
        if d.is_dir() and d.name.startswith("feedback_"):
            ticker = d.name.replace("feedback_", "")
            index = _read_index(ticker)
            for entry in index:
                if not entry.get("processed"):
                    entry["_ticker"] = ticker
                    unprocessed.append(entry)
    unprocessed.sort(key=lambda e: e.get("submitted_at", ""))
    return unprocessed
