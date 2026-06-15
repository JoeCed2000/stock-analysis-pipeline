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
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from backend.storage_paths import get_analyses_dir

logger = logging.getLogger(__name__)
PARIS = __import__("zoneinfo").ZoneInfo("Europe/Paris")
ANALYSES_DIR = get_analyses_dir()
GENERAL_FEEDBACK_BUCKET = "GENERAL"
MAX_FEEDBACK_UPLOAD_BYTES = 100 * 1024 * 1024  # Public endpoint: 100 MB upload cap.
ALLOWED_FEEDBACK_UPLOAD_SUFFIXES = {
    ".csv",
    ".har",
    ".jpeg",
    ".jpg",
    ".md",
    ".pdf",
    ".png",
    ".txt",
    ".webp",
}


def _normalize_feedback_bucket(ticker: str | None) -> str:
    normalized = (ticker or "").strip().upper()
    return normalized or GENERAL_FEEDBACK_BUCKET


def _known_feedback_tickers() -> set[str]:
    """Return ticker symbols that already have analyses or feedback buckets.

    This keeps ticker inference conservative: generic words like PDF/API are ignored
    unless they correspond to a known project analysis bucket.
    """
    tickers: set[str] = set()
    if not ANALYSES_DIR.exists():
        return tickers

    ticker_pattern = re.compile(r"(?:^|[_-])([A-Z]{1,6})(?=[_-])")
    for path in ANALYSES_DIR.iterdir():
        if not path.is_dir():
            continue
        name = path.name.upper()
        if name.startswith("FEEDBACK_"):
            bucket = name.removeprefix("FEEDBACK_")
            if bucket != GENERAL_FEEDBACK_BUCKET and re.fullmatch(r"[A-Z]{1,6}", bucket):
                tickers.add(bucket)
            continue
        for match in ticker_pattern.finditer(name):
            candidate = match.group(1)
            if candidate != GENERAL_FEEDBACK_BUCKET:
                tickers.add(candidate)
    return tickers


def _infer_ticker_from_feedback_text(text: str | None, filenames: list[str]) -> str | None:
    """Infer an omitted ticker from feedback content when it is unambiguous."""
    known = _known_feedback_tickers()
    if not known:
        return None

    haystack = "\n".join([text or "", *filenames]).upper()
    matches = sorted(
        ticker
        for ticker in known
        if re.search(rf"(?<![A-Z0-9]){re.escape(ticker)}(?![A-Z0-9])", haystack)
    )
    return matches[0] if len(matches) == 1 else None


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


def _sanitize_upload_filename(filename: str) -> str:
    """Return a safe basename for a public feedback attachment."""
    original_name = (filename or "").replace("\\", "/")
    basename = Path(original_name).name.strip()
    if not basename or basename in {".", ".."}:
        raise ValueError("Invalid feedback attachment filename")

    suffix = Path(basename).suffix.lower()
    if suffix not in ALLOWED_FEEDBACK_UPLOAD_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_FEEDBACK_UPLOAD_SUFFIXES))
        raise ValueError(f"Feedback attachment type not allowed: {suffix or '[none]'} (allowed: {allowed})")

    stem = Path(basename).stem
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "attachment"
    return f"{safe_stem}{suffix}"


def _validate_upload_content(filename: str, content: bytes) -> None:
    if len(content) > MAX_FEEDBACK_UPLOAD_BYTES:
        raise ValueError(
            f"Feedback attachment too large: {filename} "
            f"({len(content)} bytes > {MAX_FEEDBACK_UPLOAD_BYTES} bytes)"
        )


def _is_indexed_feedback_file(bucket: str, filename: str) -> bool:
    return any(filename in (entry.get("files") or []) for entry in _read_index(bucket))


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


# Lifecycle status values — canonical list
_LIFECYCLE_STATUSES = {
    "pending", "taken_into_account", "needs_clarification",
    "in_progress", "blocked", "corrected", "closed",
    "rejected", "not_reproducible",
}

# Mapping from orchestration lifecycle status → backward-compatible fix_status
_ORCHESTRATION_TO_FIX_STATUS: dict[str, str | None] = {
    "pending": "pending",
    "taken_into_account": "pending",
    "needs_clarification": "pending",
    "in_progress": "in_progress",
    "blocked": "in_progress",
    "corrected": "corrected",
    "closed": "corrected",
    "rejected": None,
    "not_reproducible": None,
}


def _get_orchestration_status(entry: dict[str, Any]) -> str | None:
    """Extract orchestration status from entry, or None if not set."""
    orch = entry.get("orchestration")
    if isinstance(orch, dict):
        return orch.get("status")
    return None


def _derive_fix_status_from_orchestration(orchestration_status: str) -> str | None:
    """Derive backward-compatible fix_status from a lifecycle status."""
    return _ORCHESTRATION_TO_FIX_STATUS.get(orchestration_status)


def _decorate_entry(entry: dict[str, Any], bucket: str) -> dict[str, Any]:
    decorated = dict(entry)
    ticker = decorated.get("ticker") or (None if bucket == GENERAL_FEEDBACK_BUCKET else bucket)
    decorated["ticker"] = ticker
    decorated["_ticker"] = bucket
    decorated["is_general"] = ticker is None
    decorated["category"] = decorated.get("category") or "general"

    lifecycle_status = _get_orchestration_status(entry)

    if lifecycle_status:
        # Lifecycle-driven decoration
        decorated["status"] = lifecycle_status
        decorated["processed"] = lifecycle_status != "pending"
        # Derive fix_status if not explicitly set
        if "fix_status" not in decorated or not decorated.get("fix_status"):
            derived = _derive_fix_status_from_orchestration(lifecycle_status)
            if derived is not None:
                decorated["fix_status"] = derived
    else:
        # Legacy decoration (no orchestration)
        decorated["status"] = "taken_into_account" if decorated.get("processed") else "pending"
        if decorated.get("processed") and not decorated.get("fix_status"):
            decorated["fix_status"] = "pending"

    return decorated


def get_feedback_file_path(bucket: str, filename: str) -> Path:
    """Resolve an indexed feedback attachment safely within its bucket directory."""
    normalized_bucket = _normalize_feedback_bucket(bucket)
    fb_dir = (ANALYSES_DIR / f"feedback_{normalized_bucket}").resolve()
    requested = Path(filename)

    if requested.is_absolute() or requested.name != filename or ".." in requested.parts:
        raise ValueError("Invalid feedback filename")
    if not _is_indexed_feedback_file(normalized_bucket, requested.name):
        raise FileNotFoundError(filename)

    file_path = (fb_dir / requested.name).resolve()
    if file_path.parent != fb_dir:
        raise ValueError("Invalid feedback filename")
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(filename)
    return file_path


async def save_feedback(
    ticker: str | None,
    text: str,
    files: list[UploadFile],
    category: str = "general",
) -> dict[str, Any]:
    """Save feedback text + uploaded files.

    When ticker is omitted, feedback is stored in the GENERAL bucket so the user can
    submit product feedback independently of any analysis card.
    """
    now = datetime.now(PARIS)
    entry_id = now.strftime("%Y-%m-%d_%H%M%S")
    normalized_category = (category or "general").strip().lower().replace(" ", "_")

    pending_files: list[tuple[str, bytes]] = []
    for upload in (files or []):
        if not upload.filename:
            continue
        safe_basename = _sanitize_upload_filename(upload.filename)
        content = await upload.read()
        _validate_upload_content(safe_basename, content)
        pending_files.append((f"{entry_id}_{safe_basename}", content))

    inferred_ticker = None
    if not (ticker or "").strip():
        inferred_ticker = _infer_ticker_from_feedback_text(text, [name for name, _ in pending_files])
        if inferred_ticker:
            ticker = inferred_ticker
            logger.info("[%s] Feedback ticker inferred from text/attachments", inferred_ticker)

    bucket = _normalize_feedback_bucket(ticker)
    fb_dir = _feedback_dir(bucket)
    log_label = ticker or GENERAL_FEEDBACK_BUCKET

    files_saved: list[str] = []
    for safe_name, content in pending_files:
        file_path = fb_dir / safe_name
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
        "category": normalized_category,
        "submitted_at": now.isoformat(),
        "text": text.strip() if text else "",
        "files": files_saved,
        "processed": False,
        "processed_at": None,
        "notes": "",
        "orchestration": {
            "status": "pending",
            "source": "feedback_page",
            "severity": "low",
        },
    }

    index = _read_index(bucket)
    index.append(entry)
    _write_index(bucket, index)

    logger.info("[%s] Feedback saved: %s (%s files, %s chars)", log_label, entry_id, len(files_saved), len(text or ""))
    return {
        "ticker": ticker,
        "category": normalized_category,
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

def mark_processed(ticker: str, entry_id: str, notes: str = "", fix_status: str = "pending", correction: str = "", orchestration_status: str | None = None) -> bool:
    """Mark a feedback entry as processed with fix tracking.
    
    fix_status: pending | in_progress | corrected
    correction: description of what was fixed
    orchestration_status: optional lifecycle status update (pending | taken_into_account | in_progress | blocked | corrected | closed | rejected | not_reproducible)
    """
    bucket = _normalize_feedback_bucket(ticker)
    index = _read_index(bucket)
    for entry in index:
        if entry.get("id") == entry_id:
            entry["processed"] = True
            entry["processed_at"] = datetime.now(PARIS).isoformat()
            if notes:
                entry["notes"] = notes
            if fix_status:
                entry["fix_status"] = fix_status
            if correction:
                entry["correction"] = correction
            if orchestration_status:
                if "orchestration" not in entry or not isinstance(entry.get("orchestration"), dict):
                    entry["orchestration"] = {}
                entry["orchestration"]["status"] = orchestration_status
            _write_index(bucket, index)
            logger.info("[%s] Feedback %s marked as processed (fix_status=%s)", bucket, entry_id, fix_status)
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
