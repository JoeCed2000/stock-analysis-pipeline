"""
Feedback Store — persists text + files to analyses/feedback_<BUCKET>/.

Buckets:
- feedback_<TICKER>   → feedback linked to a specific ticker
- feedback_GENERAL    → product / UX / generic feedback not tied to a ticker

Each bucket stores:
    index.json                        ← list of all feedback entries
    2026-05-10_143022_screenshot.png  ← attached files

Cron jobs read index.json, process new entries, and mark them as processed.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from backend.storage_paths import get_analyses_dir

logger = logging.getLogger(__name__)
PARIS = __import__("zoneinfo").ZoneInfo("Europe/Paris")
ANALYSES_DIR = get_analyses_dir()
GENERAL_FEEDBACK_BUCKET = "GENERAL"


def _normalize_feedback_bucket(ticker: str | None) -> str:
    normalized = (ticker or "").strip().upper()
    return normalized or GENERAL_FEEDBACK_BUCKET


def _feedback_dir(bucket: str) -> Path:
    """Get/create the feedback directory for a bucket."""
    d = ANALYSES_DIR / f"feedback_{bucket}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index_path(bucket: str) -> Path:
    return _feedback_dir(bucket) / "index.json"


def _read_index(bucket: str) -> list[dict[str, Any]]:
    """Read the feedback index, or return empty list."""
    path = _index_path(bucket)
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _write_index(bucket: str, entries: list[dict[str, Any]]) -> None:
    with open(_index_path(bucket), "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def _attach_latest_pdf(ticker: str, fb_dir: Path, entry_id: str) -> str | None:
    """Find the most recent deep-dive PDF for this ticker and copy it to the feedback dir.
    Returns the filename if found, None otherwise."""
    import shutil

    best_pdf = None
    best_mtime = 0.0
    for d in ANALYSES_DIR.iterdir():
        if not d.is_dir():
            continue
        if ticker.upper() not in d.name.upper():
            continue
        pdf_path = d / "07_final_report" / "earnings_deep_dive.pdf"
        if pdf_path.exists():
            mtime = pdf_path.stat().st_mtime
            if mtime > best_mtime:
                best_mtime = mtime
                best_pdf = pdf_path

    if best_pdf is None:
        logger.debug("[%s] No deep-dive PDF found to attach", ticker)
        return None

    dest_name = f"{entry_id}_deep_dive_{ticker}.pdf"
    dest_path = fb_dir / dest_name
    shutil.copy2(best_pdf, dest_path)
    logger.info("[%s] Auto-attached PDF: %s (%s bytes)", ticker, dest_name, best_pdf.stat().st_size)
    return dest_name


def _decorate_entry(entry: dict[str, Any], bucket: str) -> dict[str, Any]:
    decorated = dict(entry)
    ticker = decorated.get("ticker") or (None if bucket == GENERAL_FEEDBACK_BUCKET else bucket)
    decorated["ticker"] = ticker
    decorated["_ticker"] = bucket
    decorated["is_general"] = ticker is None
    decorated["status"] = "taken_into_account" if decorated.get("processed") else "pending"
    return decorated


async def save_feedback(
    ticker: str | None,
    text: str,
    files: list[UploadFile],
) -> dict[str, Any]:
    """Save feedback text + uploaded files.

    When ticker is omitted, feedback is stored in the GENERAL bucket so the user can
    submit product feedback independently of any analysis card.
    """
    now = datetime.now(PARIS)
    entry_id = now.strftime("%Y-%m-%d_%H%M%S")
    bucket = _normalize_feedback_bucket(ticker)
    fb_dir = _feedback_dir(bucket)
    log_label = ticker or GENERAL_FEEDBACK_BUCKET

    files_saved: list[str] = []
    for upload in (files or []):
        if not upload.filename:
            continue
        safe_name = f"{entry_id}_{upload.filename.replace(' ', '_')}"
        file_path = fb_dir / safe_name
        content = await upload.read()
        with open(file_path, "wb") as f:
            f.write(content)
        files_saved.append(safe_name)
        logger.info("[%s] Feedback file saved: %s (%s bytes)", log_label, safe_name, len(content))

    if ticker:
        pdf_attached = _attach_latest_pdf(ticker, fb_dir, entry_id)
        if pdf_attached:
            files_saved.insert(0, pdf_attached)

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

    index = _read_index(bucket)
    index.append(entry)
    _write_index(bucket, index)

    logger.info("[%s] Feedback saved: %s (%s files, %s chars)", log_label, entry_id, len(files_saved), len(text or ""))
    return {
        "ticker": ticker,
        "bucket": bucket,
        "id": entry_id,
        "files_saved": len(files_saved),
    }


def list_feedback(ticker: str | None) -> dict[str, Any]:
    """List feedback for a specific ticker bucket or GENERAL bucket."""
    bucket = _normalize_feedback_bucket(ticker)
    entries = [_decorate_entry(entry, bucket) for entry in _read_index(bucket)]
    return {
        "ticker": None if bucket == GENERAL_FEEDBACK_BUCKET else bucket,
        "bucket": bucket,
        "total": len(entries),
        "unprocessed": sum(1 for e in entries if not e.get("processed")),
        "entries": entries,
    }


def list_all_feedback() -> list[dict[str, Any]]:
    """Get all feedback across all buckets, newest first."""
    all_entries: list[dict[str, Any]] = []
    if not ANALYSES_DIR.exists():
        return all_entries
    for d in sorted(ANALYSES_DIR.iterdir(), reverse=True):
        if d.is_dir() and d.name.startswith("feedback_"):
            bucket = d.name.replace("feedback_", "")
            index = _read_index(bucket)
            for entry in index:
                all_entries.append(_decorate_entry(entry, bucket))
    all_entries.sort(key=lambda e: e.get("submitted_at", ""), reverse=True)
    return all_entries


def mark_processed(ticker: str, entry_id: str, notes: str = "") -> bool:
    """Mark a feedback entry as processed. Used by cron jobs."""
    bucket = _normalize_feedback_bucket(ticker)
    index = _read_index(bucket)
    for entry in index:
        if entry.get("id") == entry_id:
            entry["processed"] = True
            entry["processed_at"] = datetime.now(PARIS).isoformat()
            if notes:
                entry["notes"] = notes
            _write_index(bucket, index)
            logger.info("[%s] Feedback %s marked as processed", bucket, entry_id)
            return True
    return False


def get_unprocessed() -> list[dict[str, Any]]:
    """Get all unprocessed feedback across all buckets. Used by cron jobs."""
    unprocessed = [entry for entry in list_all_feedback() if not entry.get("processed")]
    unprocessed.sort(key=lambda e: e.get("submitted_at", ""))
    return unprocessed


def get_all_admin_feedback() -> list[dict[str, Any]]:
    """Backward-compatible admin listing across all buckets."""
    return list_all_feedback()
