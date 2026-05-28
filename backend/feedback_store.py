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

from backend.storage_paths import get_analyses_dir

logger = logging.getLogger(__name__)
PARIS = __import__("zoneinfo").ZoneInfo("Europe/Paris")
ANALYSES_DIR = get_analyses_dir()


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


def _attach_latest_pdf(ticker: str, fb_dir: Path, entry_id: str) -> str | None:
    """Find the most recent deep-dive PDF for this ticker and copy it to the feedback dir.
    Returns the filename if found, None otherwise."""
    import shutil
    
    # Search analyses/ for directories matching the ticker
    best_pdf = None
    best_mtime = 0
    for d in ANALYSES_DIR.iterdir():
        if not d.is_dir():
            continue
        # Match ticker in directory name (e.g., 2026-05-10_NVDA_*)
        if ticker.upper() not in d.name.upper():
            continue
        pdf_path = d / "07_final_report" / "earnings_deep_dive.pdf"
        if pdf_path.exists():
            mtime = pdf_path.stat().st_mtime
            if mtime > best_mtime:
                best_mtime = mtime
                best_pdf = pdf_path
    
    if best_pdf is None:
        logger.debug(f"[{ticker}] No deep-dive PDF found to attach")
        return None
    
    # Copy to feedback dir with timestamped name
    dest_name = f"{entry_id}_deep_dive_{ticker}.pdf"
    dest_path = fb_dir / dest_name
    shutil.copy2(best_pdf, dest_path)
    logger.info(f"[{ticker}] Auto-attached PDF: {dest_name} ({best_pdf.stat().st_size} bytes)")
    return dest_name


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

    # Auto-attach the latest deep-dive PDF so we know which version Nami reviewed
    pdf_attached = _attach_latest_pdf(ticker, fb_dir, entry_id)
    if pdf_attached:
        files_saved.insert(0, pdf_attached)  # PDF first for visibility

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


def get_all_admin_feedback() -> List[Dict[str, Any]]:
    """Get ALL feedback across all tickers for the admin dashboard.
    Returns entries sorted by date, most recent first.
    Includes processed + unprocessed."""
    all_entries = []
    if not ANALYSES_DIR.exists():
        return all_entries
    for d in sorted(ANALYSES_DIR.iterdir(), reverse=True):
        if d.is_dir() and d.name.startswith("feedback_"):
            ticker = d.name.replace("feedback_", "")
            index = _read_index(ticker)
            for entry in index:
                entry["_ticker"] = ticker
                all_entries.append(entry)
    all_entries.sort(key=lambda e: e.get("submitted_at", ""), reverse=True)
    return all_entries
