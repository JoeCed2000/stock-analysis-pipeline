#!/usr/bin/env python3
"""
Local dossier filler — runs on lapced (unfiltered network access).

Checks Render for incomplete dossiers, generates missing files locally
(SEC EDGAR 10-K, transcripts, etc.), and uploads them to Render.

Usage:
    python3 fill_dossiers.py [--once] [--ticker NVDA]

Requires:
    - DOSSIER_UPLOAD_SECRET in .env (matching Render's env var)
    - Access to SEC EDGAR, Finnhub, etc. from lapced
"""

import os
import sys
import json
import time
import logging
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── Config ──
RENDER_BASE = os.getenv("RENDER_API_URL", "https://stock-analysis-api-tdtj.onrender.com")
PROJECT_DIR = Path("/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline")

def get_upload_secret():
    """Read DOSSIER_UPLOAD_SECRET — called after .env is loaded in main()."""
    return os.getenv("DOSSIER_UPLOAD_SECRET", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("fill_dossiers")


def check_dossier(ticker: str) -> dict:
    """Check dossier status on Render."""
    resp = requests.get(f"{RENDER_BASE}/api/dossier/{ticker}/status", timeout=120)
    resp.raise_for_status()
    return resp.json()


def upload_file(ticker: str, section: str, filepath: Path):
    """Upload a file to Render's dossier endpoint."""
    secret = get_upload_secret()
    if not secret:
        logger.error("DOSSIER_UPLOAD_SECRET not set — cannot upload")
        return False
    
    with open(filepath, "rb") as f:
        resp = requests.post(
            f"{RENDER_BASE}/api/dossier/{ticker}/upload",
            data={"section": section},
            files={"file": (filepath.name, f, "application/octet-stream")},
            headers={"X-Upload-Secret": secret},
            timeout=30,
        )
    
    if resp.status_code == 200:
        logger.info(f"  ✅ Uploaded {filepath.name} → {section}")
        return True
    else:
        logger.warning(f"  ❌ Upload failed: {resp.status_code} — {resp.text[:200]}")
        return False


def generate_10k_pdf(ticker: str, output_dir: Path) -> Optional[Path]:
    """Download 10-K from SEC EDGAR and convert to PDF locally."""
    try:
        # Import project modules
        sys.path.insert(0, str(PROJECT_DIR))
        from backend.sources_collector import extract_10k_sections
        from backend.tenk_pdf import convert_10k_to_pdf
        
        sec_data = extract_10k_sections(ticker, output_dir=str(output_dir))
        tenk_local = sec_data.get("local_path", "")
        
        if tenk_local and os.path.exists(tenk_local):
            pdf_path = convert_10k_to_pdf(tenk_local, str(output_dir), ticker)
            if pdf_path and os.path.exists(pdf_path):
                return Path(pdf_path)
        
        logger.warning(f"No 10-K found for {ticker}")
        return None
    except Exception as e:
        logger.error(f"10-K generation failed: {e}")
        return None


def sync_yfinance_financials(ticker: str) -> bool:
    """Fetch yfinance data locally and push to Render cache.
    
    yfinance is often blocked on Render's shared IP but works from lapced.
    This pre-fetches deep financial data (revenue, net income, FCF) and
    pushes it to Render's file cache so the backend can merge it with Finnhub.
    """
    try:
        sys.path.insert(0, str(PROJECT_DIR))
        from backend.sources_collector import get_yahoo_data
        
        logger.info(f"  Fetching yfinance data for {ticker}...")
        yf_data = get_yahoo_data(ticker)
        
        if not yf_data:
            logger.warning(f"  yfinance returned no data for {ticker}")
            return False
        
        # Push to Render cache endpoint
        secret = get_upload_secret()
        resp = requests.post(
            f"{RENDER_BASE}/api/cache/financials/{ticker}",
            json=yf_data,
            headers={"X-Upload-Secret": secret},
            timeout=30,
        )
        if resp.status_code == 200:
            fin = yf_data.get("financials", {})
            rev = fin.get("revenue_annual")
            ni = fin.get("net_income")
            logger.info(f"  ✅ YF cached for {ticker} — Revenue: {rev}, Net Income: {ni}")
            return True
        else:
            logger.warning(f"  ❌ Cache upload failed: {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"  YF sync failed: {e}")
        return False


def generate_transcripts(ticker: str, output_dir: Path) -> Optional[Path]:
    """Generate earnings news/transcripts from Finnhub."""
    try:
        sys.path.insert(0, str(PROJECT_DIR))
        
        # Try Finnhub news
        finnhub_key = os.getenv("FINNHUB_API_KEY", "")
        if not finnhub_key:
            logger.warning("FINNHUB_API_KEY not set")
            return None
        
        from backend.sources_collector import get_finnhub_data
        
        fh_data = get_finnhub_data(ticker)
        news = fh_data.get("news", [])
        
        if news:
            tx_dir = output_dir / "04_transcripts_and_management"
            tx_dir.mkdir(parents=True, exist_ok=True)
            out_path = tx_dir / f"earnings_news_{ticker}.txt"
            
            with open(out_path, "w") as f:
                f.write(f"Earnings News — {ticker}\n")
                f.write(f"Generated: {datetime.now().isoformat()}\n")
                f.write(f"Source: Finnhub\n\n")
                for i, article in enumerate(news[:10]):
                    f.write(f"--- Article {i+1} ---\n")
                    f.write(f"Headline: {article.get('headline', 'N/A')}\n")
                    f.write(f"Source: {article.get('source', 'N/A')}\n")
                    f.write(f"Summary: {article.get('summary', 'N/A')}\n\n")
            
            return out_path
        
        return None
    except Exception as e:
        logger.error(f"Transcript generation failed: {e}")
        return None


def fill_dossier(ticker: str) -> bool:
    """Fill missing files for a single ticker dossier."""
    logger.info(f"Processing {ticker}...")
    
    # Check current status
    try:
        status = check_dossier(ticker)
        logger.info(f"  Status: {status.get('stage')} — {len(status.get('files', []))} files")
    except Exception as e:
        logger.error(f"  Cannot check status: {e}")
        return False
    
    # Create temp working directory
    tmp_dir = Path(f"/tmp/dossier_fill_{ticker}")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    
    any_uploaded = False
    
    # ── 0. YFinance financials (pre-fetch, works locally) ──
    logger.info(f"  Step 0: YFinance financials...")
    try:
        sync_yfinance_financials(ticker)
    except Exception as e:
        logger.warning(f"  YF step failed: {e}")
    
    # ── 1. 10-K PDF ──
    logger.info(f"  Step 1: 10-K PDF...")
    try:
        tenk_pdf = generate_10k_pdf(ticker, tmp_dir)
        if tenk_pdf:
            if upload_file(ticker, "02_sec_or_regulatory_filings", tenk_pdf):
                any_uploaded = True
    except Exception as e:
        logger.warning(f"  10-K step failed: {e}")
    
    # ── 2. Transcripts / News ──
    logger.info(f"  Step 2: Transcripts...")
    try:
        tx_file = generate_transcripts(ticker, tmp_dir)
        if tx_file:
            if upload_file(ticker, "04_transcripts_and_management", tx_file):
                any_uploaded = True
    except Exception as e:
        logger.warning(f"  Transcript step failed: {e}")
    
    # Cleanup
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)
    
    return any_uploaded


def get_recent_tickers() -> list:
    """Get list of recently analyzed tickers from Render."""
    resp = requests.get(f"{RENDER_BASE}/api/analyses", timeout=120)
    resp.raise_for_status()
    data = resp.json()
    
    tickers = []
    for analysis in data.get("analyses", []):
        # Extract ticker from directory name: 2026-05-04_NVDA_NVIDIA_Corp
        name = analysis.get("directory", "")
        parts = name.split("_")
        if len(parts) >= 2:
            ticker = parts[1]
            tickers.append(ticker)
    
    return list(set(tickers))  # dedup, doesn't preserve order


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fill incomplete Render dossiers")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--ticker", type=str, help="Process specific ticker only")
    parser.add_argument("--interval", type=int, default=1800, help="Poll interval in seconds (default: 1800 = 30 min)")
    args = parser.parse_args()
    
    # Load .env
    env_path = PROJECT_DIR / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()  # force override (setdefault ignores existing env vars)
    
    if not get_upload_secret():
        logger.error("DOSSIER_UPLOAD_SECRET must be set in .env")
        sys.exit(1)
    
    # Single ticker mode
    if args.ticker:
        fill_dossier(args.ticker.upper())
        return
    
    # Polling loop
    logger.info(f"Starting dossier filler — polling every {args.interval}s")
    while True:
        try:
            tickers = get_recent_tickers()
            logger.info(f"Found {len(tickers)} recent tickers: {tickers}")
            
            for ticker in tickers:
                try:
                    fill_dossier(ticker)
                except Exception as e:
                    logger.error(f"Error processing {ticker}: {e}")
            
        except Exception as e:
            logger.error(f"Poll error: {e}")
        
        if args.once:
            break
        
        logger.info(f"Sleeping {args.interval}s...")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
