#!/usr/bin/env python3
"""
Backup Render data → local PC (lapced).
Runs as cron every 30 min. Pulls:
  1. GET /api/analyses → list of all analyzed tickers
  2. For any NEW ticker not in local backup: download ZIP + extract
  3. Save analysis list as JSON for history

Secrets via .env at project root (DOSSIER_UPLOAD_SECRET for auth).
"""
import os
import sys
import json
import time
import shutil
import zipfile
import urllib.request
from pathlib import Path
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────
RENDER_URL = os.getenv("RENDER_URL", "https://stock-analysis-api-tdtj.onrender.com")
SECRET = os.getenv("DOSSIER_UPLOAD_SECRET", "")
PROJECT_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = PROJECT_DIR / "backups"
ANALYSES_DIR = PROJECT_DIR / "analyses"
HISTORY_FILE = BACKUP_DIR / "analysis_history.json"
LOG_FILE = BACKUP_DIR / "backup.log"

os.makedirs(BACKUP_DIR, exist_ok=True)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def api_get(path: str) -> dict:
    """Call Render API, return JSON or {} on failure."""
    url = f"{RENDER_URL}{path}"
    headers = {"X-Upload-Secret": SECRET} if SECRET else {}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log(f"API error {path}: {e}")
        return {}


def load_history() -> dict:
    """Load {ticker: {date, files}} from local history."""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {}


def save_history(history: dict) -> None:
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, sort_keys=True)


def download_zip(ticker: str) -> Path | None:
    """Download dossier ZIP for a ticker, return local path or None."""
    url = f"{RENDER_URL}/api/dossier/{ticker}/download"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            tmp = BACKUP_DIR / f"{ticker}_tmp.zip"
            with open(tmp, "wb") as f:
                shutil.copyfileobj(resp, f)
            return tmp
    except Exception as e:
        log(f"Download {ticker} failed: {e}")
        return None


def extract_zip(zip_path: Path, ticker: str) -> bool:
    """Extract ZIP into analyses/ directory. Returns True on success."""
    try:
        dest = ANALYSES_DIR / ticker
        if dest.exists():
            shutil.rmtree(dest)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(dest)
        zip_path.unlink()
        log(f"Extracted {ticker} → {dest} ({len(list(dest.rglob('*')))} files)")
        return True
    except Exception as e:
        log(f"Extract {ticker} failed: {e}")
        return False


def main():
    log("━━━ Backup Render → Lapced ━━━")

    # 1. Get analysis list from Render
    data = api_get("/api/analyses")
    remote_analyses = data.get("analyses", [])
    if not remote_analyses:
        log("No analyses on Render (empty or unreachable)")
        # Still save empty history to keep file fresh
        save_history(load_history())
        return

    log(f"Render has {len(remote_analyses)} analyses")

    # 2. Load local history
    history = load_history()
    new_count = 0
    skip_count = 0

    for analysis in remote_analyses:
        ticker = analysis.get("ticker", "?")
        date_str = analysis.get("date", "")
        files = analysis.get("files", 0)

        # Check if already backed up (by ticker+date — re-analysis same day = overwrite)
        key = f"{ticker}_{date_str}"
        if key in history and history[key].get("files", 0) >= files:
            skip_count += 1
            continue

        # 3. Download ZIP
        log(f"⬇  Downloading {ticker} ({date_str}, {files} files)...")
        zip_path = download_zip(ticker)
        if not zip_path:
            continue

        # 4. Extract locally
        if extract_zip(zip_path, ticker):
            history[key] = {
                "ticker": ticker,
                "date": date_str,
                "company_name": analysis.get("company_name", ""),
                "files": files,
                "backed_up_at": datetime.now().isoformat(),
            }
            new_count += 1

    # 5. Save updated history
    save_history(history)
    log(f"Done — {new_count} new, {skip_count} skipped, {len(history)} total in history")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == "__main__":
    main()
