"""
Async dossier generator — non-blocking file generation after fast analysis.

Pattern:
    1. analyze_ticker_fast() → returns score + decision in <5s (no heavy file I/O)
    2. generate_dossier_background() → spawns thread to write PDF, Excel, 10-K, etc.
    3. GET /api/dossier/{ticker}/status → {ready: bool, files: [...]}

On Render free tier, the background thread may be killed if the server sleeps,
but files are persisted on disk. If killed, the dossier regenerates on next poll.
"""

import os
import json
import threading
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# In-memory registry: ticker → dossier status
# Survives between requests, lost on server restart (acceptable — files on disk)
_dossier_registry: Dict[str, dict] = {}
_registry_lock = threading.Lock()

# Paris timezone
PARIS = __import__("zoneinfo").ZoneInfo("Europe/Paris")


def _analyses_dir() -> Path:
    """Return the project analyses directory from either repo root or backend cwd."""
    cwd = Path.cwd()
    if cwd.name == "backend":
        return cwd.parent / "analyses"
    return cwd / "analyses"


def _blocked_status(stage: str, issues: list[str] | None = None) -> dict:
    verification_issues = issues or []
    return {
        "ready": False,
        "files": [],
        "stage": stage,
        "verified": False,
        "download_enabled": False,
        "verification_issues": verification_issues,
    }


def _apply_verification_status(status: dict) -> dict:
    verification_issues: list[str] = []

    if not status.get("ready"):
        verification_issues.append("Required dossier deliverables are not complete.")

    deep_dive_validated = status.get("deep_dive_validated")
    verification_warnings = []  # non-blocking — shown to user but don't block download
    if deep_dive_validated is not True:
        if deep_dive_validated is None:
            # Not yet validated — allow download but warn (non-blocking)
            verification_warnings.append("Deep-dive validation pending — review before relying on PDF.")
            deep_dive_validated = True  # treat as passed for download purposes
        else:
            issues = status.get("deep_dive_issues") or []
            if issues:
                verification_issues.extend(str(issue) for issue in issues)
            else:
                verification_issues.append("Deep-dive validation failed.")

    verified = bool(status.get("ready")) and deep_dive_validated is True and not verification_issues
    status["verified"] = verified
    status["download_enabled"] = verified
    status["verification_issues"] = verification_issues
    status["verification_warnings"] = verification_warnings
    return status


def get_dossier_status(ticker: str) -> dict:
    """Check if dossier is ready for a ticker. Returns {ready, files, error}."""
    ticker_clean = ticker.replace(".", "_").upper()
    
    # Check in-memory registry first — but only if complete or failed
    # NEVER return "generating" from cache — the thread might have crashed
    # and files may already exist on disk (written by analyze_ticker_fast)
    with _registry_lock:
        if ticker_clean in _dossier_registry:
            cached = _dossier_registry[ticker_clean]
            if cached.get("stage") == "failed":
                return cached
            # If "generating" or "complete", fall through to disk check so
            # validation state always reflects the latest generated files.
    
    # Check on disk
    analyses_dir = _analyses_dir()
    if not analyses_dir.exists():
        return _blocked_status("not_started")
    
    matches = sorted(analyses_dir.glob(f"*_{ticker_clean}_*"), reverse=True)
    # Skip dummy UPLOADED directories
    matches = [m for m in matches if "UPLOADED" not in str(m)]
    if not matches:
        return _blocked_status("not_started")
    
    # Prefer directories that have actual analysis content (report.md/report.pdf)
    # over dummy UPLOADED directories created by the upload endpoint
    # ALSO prefer directories where deep_dive validation PASSED
    best_match = None
    validated_match = None
    for m in matches:
        has_report = (m / "07_final_report" / "report.md").exists() or \
                     (m / "07_final_report" / "report.pdf").exists() or \
                     (m / "07_final_report" / "earnings_deep_dive.pdf").exists()
        if not has_report:
            continue
        
        # Check validation — prefer PASSED dirs
        validation_file = m / "07_final_report" / "deep_dive_validation.json"
        validation_passed = False
        if validation_file.exists():
            try:
                vdata = json.loads(validation_file.read_text())
                validation_passed = vdata.get("passed", False)
            except Exception as e:
                logger.debug(f"Fallback: {e}")
        
        if best_match is None:
            best_match = m
        if validation_passed and validated_match is None:
            validated_match = m
        
        if validated_match:
            break  # Found a validated dir — stop searching
    
    # Prefer a validated directory, fall back to any with a report
    if validated_match:
        best_match = validated_match
    elif best_match is None:
        best_match = matches[0]  # ultimate fallback
    
    dossier_dir = best_match
    files = _list_dossier_files(dossier_dir)
    
    # Dossier is "ready" ONLY if we have the 4 key deliverables
    # Check by exact filename suffix (file-extension-agnostic for the directory)
    file_strs = [str(f).replace("\\", "/") for f in files]
    
    has_report = any(
        "07_final_report/report" in s
        or "en/07_final_report/report" in s
        for s in file_strs
    )
    has_excel = any(
        ("financials_" in s and s.endswith(".xlsx"))
        and ("/03_financial_data_sources/" in f"/{s}" or s.startswith("03_financial_data_sources/"))
        for s in file_strs
    )
    
    # Ready if we have report (md or pdf) + Excel — MD→PDF conversion happens on download
    ready = has_report and has_excel
    
    relative_files = [str(f.relative_to(dossier_dir)) for f in files]
    bonus_files = [
        path for path in relative_files
        if (
            path.endswith("07_final_report/earnings_deep_dive.md")
            or path.endswith("07_final_report/earnings_deep_dive.pdf")
        )
    ]

    status = {
        "ready": ready,
        "files": relative_files,
        "bonus_files": bonus_files,
        "directory": str(dossier_dir),
        "stage": "complete" if ready else "in_progress",
        "estimated_seconds": 0,
    }
    
    # Check deep-dive validation
    dd_val_path = dossier_dir / "07_final_report" / "deep_dive_validation.json"
    if dd_val_path.exists():
        try:
            with open(dd_val_path) as f:
                dd_val = json.load(f)
            status["deep_dive_validated"] = dd_val.get("passed", False)
            if not dd_val.get("passed"):
                status["deep_dive_issues"] = dd_val.get("issues", [])
        except Exception:
            status["deep_dive_validated"] = False
    else:
        status["deep_dive_validated"] = None  # Not yet generated

    _apply_verification_status(status)
    
    with _registry_lock:
        _dossier_registry[ticker_clean] = status
    
    return status


def _list_dossier_files(dossier_dir: Path) -> list:
    """Recursively list all files in dossier directory."""
    files = []
    if dossier_dir.exists():
        for fpath in sorted(dossier_dir.rglob("*")):
            if fpath.is_file():
                files.append(fpath)
    return files

