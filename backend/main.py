"""FastAPI application for Stock Analysis Pipeline."""
import os
# ── Load .env BEFORE anything else ──
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
# ── Clean proxy env vars that break edgartools httpx transport ──
for _k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
    os.environ.pop(_k, None)

import uuid
import logging
from pathlib import Path
from typing import List

import io
import json
import sys
import zipfile
import re
import hashlib
import mimetypes
import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, UploadFile, File as FastAPIFile, Header, Form, Request, Body, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import math

def _sanitize_json(obj):
    """Recursively replace NaN/inf with None for JSON compliance."""
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_json(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj


def _normalize_dossier_language(lang: str) -> str:
    """Normalize public language codes used by ZIP/PDF generation."""
    clean = (lang or "en").strip().lower()
    return "jp" if clean == "jp" else "en"


def _translation_language(lang: str) -> str:
    return lang


def _should_convert_dossier_text_to_pdf(fpath: Path, *, refresh_pdf: bool) -> bool:
    """Return whether a text artifact should be converted with the generic PDF renderer."""
    if fpath.name == "README.md" or fpath.name == "README.txt":
        return False
    if fpath.suffix not in {".md", ".txt"}:
        return False
    pdf_path = fpath.with_suffix(".pdf")
    if fpath.name == "earnings_deep_dive.md" and pdf_path.exists():
        return False
    return refresh_pdf or not pdf_path.exists()

from backend.models import TickerRequest, AnalysisResult, HealthResponse, ValuationV2Response
from backend.orchestrator import run_analysis_parallel
from backend.earnings_deep_dive.schemas import DeepDiveRequest, DeepDiveResponse
from backend.sources_collector import list_available_quarters, get_yahoo_data, get_yahoo_data_for_quarter
from backend.search_logger import log_search
from backend.storage_paths import get_analyses_dir
from backend.routes.valuation_context import router as valuation_context_router
from backend.routes.peer_benchmark import router as peer_benchmark_router

# Setup logging with our custom configuration
from backend.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

# Load .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

app = FastAPI(title="Stock Analysis Pipeline", version="1.0.0", root_path="/stock-analysis")

# ── Rate limiting middleware (P0 audit 2026-05-05) ──
# In-memory token buckets with auto-cleanup.
# Keys are (IP, tier), not IP alone: page loads/static assets must not consume
# the stricter write/analysis quota used by API actions.
_rate_limits = {}  # (IP, tier) → (window_start, count)
_RATE_WINDOW = 60  # seconds
_RATE_LIMIT_HEAVY = 10   # LLM/expensive endpoints — 10/min
_RATE_LIMIT_MODERATE = 30  # DB/write endpoints — 30/min
_RATE_LIMIT_DEFAULT = 120  # read-only + lightweight parse endpoints — 120/min
_RATE_MAX_ENTRIES = 5000  # Prune oldest entries when exceeded

# Expensive endpoints (LLM calls, batch processing, PDF generation)
_HEAVY_PATHS = {"/api/analyze", "/api/analyze/async", "/api/earnings/deep-dive", "/api/batch/analyze"}
# Write/modify endpoints (moderate cost). /api/batch/upload is used by the UI
# debounce parser while typing, so it intentionally stays in the default tier.
_MODERATE_PATHS = {"/api/feedback", "/api/cache/financials", "/api/dossier"}

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    from time import time as _time
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path
    # Skip rate limiting for health endpoint and in-process FastAPI TestClient.
    # TestClient uses a synthetic host ("testclient") and runs many endpoint
    # assertions in one process; production traffic can never originate from it.
    if path == "/api/health" or client_ip == "testclient":
        return await call_next(request)
    # Determine rate limit tier based on path cost
    if path in _HEAVY_PATHS:
        limit = _RATE_LIMIT_HEAVY
        tier = "heavy"
    elif any(path.startswith(p) for p in _MODERATE_PATHS):
        limit = _RATE_LIMIT_MODERATE
        tier = "moderate"
    else:
        limit = _RATE_LIMIT_DEFAULT
        tier = "default"
    now = _time()
    rate_key = (client_ip, tier)
    
    # Periodic cleanup: if dict grows too large, evict expired entries
    if len(_rate_limits) > _RATE_MAX_ENTRIES:
        expired = [key for key, (ts, _) in _rate_limits.items() if now - ts >= _RATE_WINDOW]
        for key in expired:
            del _rate_limits[key]
    
    entry = _rate_limits.get(rate_key)
    if entry and now - entry[0] < _RATE_WINDOW:
        if entry[1] >= limit:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded ({limit} req/{_RATE_WINDOW}s). Retry shortly."},
            )
        entry[1] += 1
    else:
        _rate_limits[rate_key] = [now, 1]
    return await call_next(request)

# ── API Auth gate —─────────────────────────────────────────────────
# Protects write + admin endpoints behind CED_CONTROL_KEY env var.
# Set CED_CONTROL_KEY in .env. Without it, protected endpoints return 403.
# Matching spec: SEC-002 (X-API-Key write endpoints), BR-008 (auth obligatoire).
_API_KEY = os.getenv("CED_CONTROL_KEY", "")

async def _require_auth(request: Request):
    """FastAPI dependency: reject if CED_CONTROL_KEY is not set or doesn't match.
    Local requests (127.0.0.1, localhost) bypass auth automatically.
    Accepts X-API-Key header (primary) or api_key query param (fallback for downloads)."""
    if not _API_KEY:
        raise HTTPException(status_code=403, detail="API key not configured (set CED_CONTROL_KEY)")
    # Bypass auth for local requests and in-process FastAPI TestClient.
    # TestClient uses a synthetic host ("testclient") and cannot send browser
    # referer/origin headers; production network clients cannot spoof this host.
    host = request.client.host if request.client else ""
    if host in ("127.0.0.1", "::1", "localhost", "testclient"):
        return
    # Bypass auth for same-origin browser requests (frontend served by this server)
    referer = request.headers.get("referer", "")
    origin = request.headers.get("origin", "")
    allowed_origins = ("sa.cedlabusa.net", "www.cedlabusa.net", "localhost:5173", "127.0.0.1:5173", "localhost:8780")
    if any(o in referer or o in origin for o in allowed_origins):
        return
    provided = request.headers.get("X-API-Key", "") or request.query_params.get("api_key", "")
    if provided != _API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://127.0.0.1:5173",
        "https://sa.cedlabusa.net",  # production tunnel
        "https://www.cedlabusa.net",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(valuation_context_router)
app.include_router(peer_benchmark_router)

ANALYSES_DIR = get_analyses_dir()
logger.info("Canonical analyses dir: %s", ANALYSES_DIR)

# Batch job store — persisted to batches/ on disk for restart resilience
_batch_jobs: dict = {}
BATCH_DIR = Path(__file__).parent.parent / "batches"
BATCH_DIR.mkdir(exist_ok=True)

def _save_batch_job(job: dict):
    """Persist batch job to disk for Render restart resilience."""
    try:
        job_path = BATCH_DIR / f"{job['job_id']}.json"
        # Serialize AnalysisResult objects to dict
        safe_job = {}
        for k, v in job.items():
            if k == "results":
                safe_job[k] = {}
                for ticker, r in v.items():
                    safe_job[k][ticker] = r.model_dump() if hasattr(r, "model_dump") else r
            else:
                safe_job[k] = v
        with open(job_path, "w") as f:
            json.dump(safe_job, f, default=str)
    except Exception as e:
        logger.debug(f"Fallback: {e}")  # Best-effort

def _load_batch_job(job_id: str) -> dict | None:
    """Try to load a batch job from disk (survives restart)."""
    try:
        job_path = BATCH_DIR / f"{job_id}.json"
        if job_path.exists():
            with open(job_path) as f:
                return json.load(f)
    except Exception as e:
        logger.debug(f"Fallback: {e}")
    return None

TICKER_RE = re.compile(r'^[A-Z]{1,5}(?:\.[A-Z]{1,2})?$')  # AAPL, MC.PA, BRK.B
ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{10}$')  # US0378331005

# Lazy import yfinance for ticker validation
_yf_available = None


def _ticker_dir_key(ticker: str) -> str:
    """Return the ticker key used in analysis directory names."""
    return ticker.strip().upper().replace(".", "_")


def _find_analysis_dirs(ticker: str) -> list[Path]:
    """Find analysis directories for a ticker, case-insensitively.
    Returns newest first. The PDF endpoint handles async generation if needed."""
    key = _ticker_dir_key(ticker)
    # Primary: glob pattern like *_NVDA_* (legacy)
    dirs = sorted(ANALYSES_DIR.glob(f"*_{key}_*"), reverse=True)
    # Fallback: exact ticker name directory (e.g., "NVDA")
    exact = ANALYSES_DIR / key
    if exact.is_dir() and exact not in dirs:
        dirs.append(exact)
    # Fallback: any dir ending with ticker (e.g., "NVDA_NVIDIA", "NVDA_2026Q2")
    for d in sorted(ANALYSES_DIR.glob(f"{key}*"), reverse=True):
        if d.is_dir() and d not in dirs:
            dirs.append(d)
    return dirs


def _ticker_from_analysis_dir(entry: Path) -> str | None:
    """Infer ticker from generated dossier files, falling back to directory name."""
    for pattern in (
        "03_financial_data_sources/yahoo_snapshot_*.json",
        "03_financial_data_sources/financials_*.xlsx",
    ):
        for fpath in entry.glob(pattern):
            stem = fpath.stem
            if stem.startswith("yahoo_snapshot_"):
                return stem.removeprefix("yahoo_snapshot_")
            if stem.startswith("financials_"):
                return stem.removeprefix("financials_")

    manifest = entry / "06_extracted_data" / "sources_manifest.json"
    if manifest.exists():
        try:
            sources = json.loads(manifest.read_text())
            for source in sources if isinstance(sources, list) else []:
                url = source.get("url", "")
                match = re.search(r"/quote/([^/?]+)/?", url)
                if match:
                    return match.group(1)
        except Exception as e:
            logger.debug(f"Fallback: {e}")

    match = re.match(r"^(?:\d{4}-\d{2}-\d{2}|\d{8})_([A-Z0-9]+(?:_[A-Z0-9]+)?)_", entry.name)
    return match.group(1).replace("_", ".") if match else None

def _get_yf():
    global _yf_available
    if _yf_available is None:
        try:
            import yfinance as yf
            _yf_available = yf
        except ImportError:
            _yf_available = False
    return _yf_available


# Lightweight ticker existence cache (30min TTL)
_ticker_cache: dict = {}

def _ticker_exists(ticker: str) -> bool:
    """Check if ticker exists on Yahoo Finance via search API.
    Uses lightweight query1 endpoint (fast, ~200ms) with 30min cache.
    Falls back to True (optimistic) on network error — invalid tickers
    are caught during analysis when no data returns."""
    now = time.time()
    if ticker in _ticker_cache:
        cached_at, exists = _ticker_cache[ticker]
        if now - cached_at < 1800:  # 30 min TTL
            return exists
    
    try:
        from backend.http_client import http
        r = http.get(
            f"https://query1.finance.yahoo.com/v1/finance/search?q={ticker}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=3
        )
        if r.status_code == 200:
            quotes = r.json().get("quotes", [])
            for q in quotes:
                if q.get("symbol", "").upper() == ticker.upper():
                    _ticker_cache[ticker] = (now, True)
                    return True
            _ticker_cache[ticker] = (now, False)
            return False
    except Exception as e:
        logger.debug(f"Fallback: {e}")
    # On error, be optimistic — let analysis catch the invalid ticker
    return True


def _isin_to_ticker_lookup(isin: str) -> str | None:
    """Resolve an ISIN to a ticker symbol via Yahoo Finance search.
    Used as fallback when ISIN is not in ISIN_TO_TICKER mapping.
    Returns None if resolution fails."""
    try:
        from backend.http_client import http
        r = http.get(
            f"https://query1.finance.yahoo.com/v1/finance/search?q={isin}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        if r.status_code == 200:
            quotes = r.json().get("quotes", [])
            for q in quotes:
                if q.get("quoteType") == "EQUITY":
                    return q.get("symbol")
    except Exception as e:
        logger.debug(f"ISIN lookup failed: {e}")

# Common ISIN → ticker mapping (extensible)
ISIN_TO_TICKER = {
    "US0378331005": "AAPL",
    "US5949181045": "MSFT",
    "US67066G1040": "NVDA",
    "US02079K3059": "GOOGL",
    "US30303M1027": "META",
    "FR0000121014": "MC.PA",
    "NL0010273215": "ASML",
    "US88160R1014": "TSLA",
    "US0231351067": "AMZN",
    "US17275R1023": "CSCO",
    "US4592001014": "IBM",
    "US4781601046": "JNJ",
    "US0846707026": "BRK.B",
    "US46625H1005": "JPM",
    "US92826C8394": "V",
    "US4370761029": "HD",
    "US5324571083": "LLY",
    "US0970231058": "BA",
    "US00206R1023": "T",
    "US88579Y1010": "CRM",
    "US0080731088": "AVAV",
}


def _isin_checksum(isin: str) -> bool:
    """Validate ISIN checksum (ISO 6166)."""
    if not ISIN_RE.match(isin):
        return False
    # Convert letters to numbers: A=10, B=11, ..., Z=35
    digits = []
    for c in isin:
        if c.isdigit():
            digits.append(int(c))
        elif c.isalpha():
            n = ord(c) - 55  # A=10, B=11, ...
            digits.extend([n // 10, n % 10])
        else:
            return False
    # Double every second digit from the right
    for i in range(len(digits) - 2, -1, -2):
        d = digits[i] * 2
        if d > 9:
            d -= 9
        digits[i] = d
    return sum(digits) % 10 == 0


def _parse_tickers_from_text(text: str) -> List[dict]:
    """Parse text into list of {value, type, normalized, status, error} items.
    Invalid tokens are flagged with status='invalid' and an error message.
    """
    items = []
    seen = set()
    invalid_count = 0

    # Split by newlines, commas, semicolons, spaces
    tokens = re.split(r'[\n,;\s]+', text.strip())

    for token in tokens:
        token = token.strip().upper()
        if not token:
            continue
        if token in seen:
            continue

        # ISIN with checksum validation
        if ISIN_RE.match(token):
            if _isin_checksum(token):
                ticker = ISIN_TO_TICKER.get(token, None)
                if not ticker:
                    ticker = _isin_to_ticker_lookup(token)  # Yahoo Finance fallback
                if ticker:
                    items.append({
                        "value": token, "type": "ISIN",
                        "normalized": ticker, "status": "valid",
                    })
                else:
                    items.append({
                        "value": token, "type": "ISIN",
                        "normalized": token, "status": "valid",
                        "error": "ISIN valid but ticker not found — add to ISIN_TO_TICKER mapping",
                    })
            else:
                items.append({
                    "value": token, "type": "ISIN",
                    "normalized": token, "status": "invalid",
                    "error": "Invalid ISIN checksum",
                })
            seen.add(token)
        elif TICKER_RE.match(token):
            exists = _ticker_exists(token)
            items.append({
                "value": token, "type": "TICKER",
                "normalized": token,
                "status": "valid" if exists else "invalid",
                "error": None if exists else "Ticker not found on any exchange — verify the symbol",
            })
            seen.add(token)
        else:
            # Strict validation — only exact ticker format accepted
            # Tickers must be 1-5 uppercase letters (+ optional .X/.XX suffix)
            invalid_count += 1
            items.append({
                "value": token, "type": "UNKNOWN",
                "normalized": token, "status": "invalid",
                "error": _classify_error(token),
            })
            seen.add(token)

    return items


def _classify_error(token: str) -> str:
    """Classify why a token is invalid."""
    if len(token) < 2:
        return "Too short — minimum 2 characters"
    if len(token) > 10:
        return "Too long — maximum 10 characters"
    digits = sum(1 for c in token if c.isdigit())
    if digits > 0 and digits < len(token):
        return "Mixed letters/numbers — not a valid ticker or ISIN"
    if any(not c.isalnum() and c != '.' for c in token):
        return "Contains special characters"
    return "Not a recognized format"


@app.post("/api/batch/upload", dependencies=[Depends(_require_auth)])
async def batch_upload(file: UploadFile = FastAPIFile(None)):
    """Upload a text file containing tickers/ISINs. Returns parsed list."""
    if file is None:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await file.read()
    text = content.decode("utf-8", errors="ignore")
    items = _parse_tickers_from_text(text)

    return JSONResponse({
        "filename": file.filename,
        "total_found": len(items),
        "items": items,
    })


class BatchAnalyzeRequest(BaseModel):
    tickers: List[str] = Field(..., min_length=1, max_length=25)


class SeekingAlphaAccessUpdateRequest(BaseModel):
    cookie_header: str = Field(..., min_length=10)
    user_agent: str | None = Field(default=None, max_length=500)


class SeekingAlphaProbeRequest(BaseModel):
    ticker: str = Field(default="NVDA", min_length=1, max_length=10)


@app.post("/api/batch/analyze", dependencies=[Depends(_require_auth)])
async def batch_analyze(request: BatchAnalyzeRequest):
    """Submit tickers for batch analysis. Returns job_id for polling."""
    job_id = hashlib.sha256(
        f"{request.tickers}:{time.time()}".encode()
    ).hexdigest()[:16]

    _batch_jobs[job_id] = {
        "job_id": job_id,
        "tickers": request.tickers,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "results": {},
        "errors": {},
        "completed": 0,
        "total": len(request.tickers),
    }

    # Start analysis in background using uvicorn's background execution
    # For now, we'll process synchronously in the status endpoint
    # A proper implementation would use BackgroundTasks or a task queue

    _save_batch_job(_batch_jobs[job_id])
    logger.info(f"Batch job {job_id}: {request.tickers} — {len(request.tickers)} tickers queued")

    return JSONResponse({
        "job_id": job_id,
        "tickers": request.tickers,
        "status": "pending",
    })


@app.get("/api/batch/{job_id}/status")
async def batch_status(job_id: str):
    """Get batch job status. Triggers processing if pending."""
    job = _batch_jobs.get(job_id)
    if not job:
        job = _load_batch_job(job_id)  # Survives Render restart
        if job:
            _batch_jobs[job_id] = job
            logger.info(f"Batch job {job_id} restored from disk")
        else:
            raise HTTPException(status_code=404, detail="Job not found")

    # If pending, process now (in thread pool to avoid blocking event loop)
    if job["status"] == "pending":
        import asyncio as _asyncio
        
        def _process_batch(j):
            j["status"] = "processing"
            logger.info(f"[{j['job_id']}] Analyzing {len(j['tickers'])} tickers in parallel...")
            result = run_analysis_parallel(j["tickers"], output_base=str(ANALYSES_DIR))
            for ticker in j["tickers"]:
                if ticker in result["results"]:
                    j["results"][ticker] = result["results"][ticker]
                    log_search(ticker, "completed", 0.0, user_agent="batch")
                elif ticker in result.get("errors", {}):
                    j["errors"][ticker] = result["errors"][ticker]
                    log_search(ticker, "failed", 0.0, error=str(result["errors"][ticker]), user_agent="batch")
                else:
                    j["errors"][ticker] = "Unknown error"
                    log_search(ticker, "failed", 0.0, error="Unknown error", user_agent="batch")
                j["completed"] += 1
            j["status"] = "completed" if not j["errors"] else "partial"
            return j
        
        job = await _asyncio.to_thread(_process_batch, job)
        _save_batch_job(job)  # Persist to survive restart

    # Serialize results
    results_list = []
    for ticker, result in job["results"].items():
        r = result.model_dump() if hasattr(result, 'model_dump') else result
        r.pop("financials", None)
        r.pop("management_tone", None)
        r.pop("segments", None)
        r.pop("valuation", None)
        if "scoring" in r and isinstance(r["scoring"], dict):
            r["scoring"]["total"] = result.scoring.total if hasattr(result, 'scoring') else sum(r["scoring"].values())
        results_list.append(r)

    return JSONResponse({
        "job_id": job_id,
        "status": job["status"],
        "completed": job["completed"],
        "total": job["total"],
        "results": results_list,
        "errors": list(job["errors"].values()),
    })


@app.get("/api/batch/{job_id}/download")
async def batch_download(job_id: str):
    """Download all analysis documents as a ZIP file."""
    job = _batch_jobs.get(job_id)
    if not job:
        job = _load_batch_job(job_id)
        if job:
            _batch_jobs[job_id] = job
        else:
            raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] not in ("completed", "partial"):
        raise HTTPException(status_code=400, detail="Job not yet complete")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for ticker in job["tickers"]:
            if ticker not in job["results"]:
                zf.writestr(f"{ticker}/ERROR.txt", job["errors"].get(ticker, "No result"))
                continue

            # Find the analysis directory for this ticker
            ticker_clean = ticker.replace(".", "_")
            matches = sorted(ANALYSES_DIR.glob(f"*_{ticker_clean}_*"), reverse=True)
            if not matches:
                zf.writestr(f"{ticker}/NOT_FOUND.txt", "Analysis directory not found")
                continue

            analysis_dir = matches[0]
            for fpath in analysis_dir.rglob("*"):
                if fpath.is_file():
                    arcname = f"{ticker}/{fpath.relative_to(analysis_dir)}"
                    zf.write(fpath, arcname)

    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=analysis_{job_id}.zip"},
    )


@app.get("/api/analyze/{ticker}/download")
async def ticker_download(ticker: str):
    """Download all documents for a single ticker as a ZIP file."""
    ticker = ticker.strip().upper()
    matches = _find_analysis_dirs(ticker)
    if not matches:
        raise HTTPException(status_code=404, detail=f"No analysis found for {ticker}")

    analysis_dir = matches[0]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fpath in sorted(analysis_dir.rglob("*")):
            if fpath.is_file():
                # Skip raw JSON/CSV data files — keep MD/TXT (readable) + PDF + Excel
                if fpath.suffix in ('.json', '.csv'):
                    continue
                arcname = fpath.relative_to(analysis_dir)
                zf.write(fpath, arcname)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={ticker}_analysis.zip"},
    )


@app.get("/api/health", response_model=HealthResponse)
async def health():
    import subprocess
    try:
        commit = subprocess.check_output(
            ["git", "log", "-1", "--format=%h"],
            cwd=Path(__file__).parent.parent,
            text=True, timeout=5
        ).strip()
        version = subprocess.check_output(
            ["git", "describe", "--tags", "--always"],
            cwd=Path(__file__).parent.parent,
            text=True, timeout=5
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError, subprocess.TimeoutExpired):
        commit = "unknown"
        version = "unknown"
    return {
        "status": "ok",
        "service": "stock-analysis-pipeline",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": version,
        "commit": commit,
    }


@app.get("/api/version")
async def read_version():
    """Return version and commit metadata from the local git repository."""
    import subprocess
    try:
        commit = subprocess.check_output(
            ["git", "log", "-1", "--format=%h"],
            cwd=Path(__file__).parent.parent,
            text=True, timeout=5
        ).strip()
        version = subprocess.check_output(
            ["git", "describe", "--tags", "--always"],
            cwd=Path(__file__).parent.parent,
            text=True, timeout=5
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError, subprocess.TimeoutExpired):
        commit = "unknown"
        version = "unknown"
    return {
        "service": "stock-analysis-pipeline",
        "version": version,
        "commit": commit,
        "build_time": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
    }


# ═══════════ DEBUG ENDPOINTS — disabled in production ═══════════
# These leak internal data and MUST NOT be exposed on public tunnels.
# To re-enable locally: ENABLE_DEBUG=true in .env

@app.get("/api/debug/yf-cache/{ticker}", dependencies=[Depends(_require_auth)])
async def debug_yf_cache(ticker: str):
    """Debug: show yfinance cache status for a ticker."""
    if os.getenv("ENABLE_DEBUG") != "true":
        raise HTTPException(status_code=403, detail="Debug endpoints disabled")
    from backend.sources_collector import _cache_get_yf, _cache_get, _cache_path_yf, _cache_path
    
    result = {
        "ticker": ticker.upper(),
        "yf_cache_file": str(_cache_path_yf(ticker)),
        "yf_cache_exists": _cache_path_yf(ticker).exists(),
        "yf_cache_data": None,
        "main_cache_file": str(_cache_path(ticker)),
        "main_cache_exists": _cache_path(ticker).exists(),
        "main_cache_data_pe": None,
    }
    
    yf = _cache_get_yf(ticker)
    if yf:
        result["yf_cache_data"] = {
            "pe_current": yf.get("pe_current"),
            "pe_forward": yf.get("pe_forward"),
            "revenue_annual": yf.get("financials", {}).get("revenue_annual"),
            "net_income": yf.get("financials", {}).get("net_income"),
        }
    
    main = _cache_get(ticker)
    if main:
        result["main_cache_data_pe"] = main.get("pe_current")
        result["main_cache_fin_rev"] = main.get("financials", {}).get("revenue_annual")
    
    return result


@app.get("/api/debug/sources", dependencies=[Depends(_require_auth)])
async def debug_sources():
    """Return which API sources are configured (masked keys)."""
    if os.getenv("ENABLE_DEBUG") != "true":
        raise HTTPException(status_code=403, detail="Debug endpoints disabled")

    def mask(key: str) -> str:
        return key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
    
    fh_key = os.getenv("FINNHUB_API_KEY", "")
    td_key = os.getenv("TWELVEDATA_API_KEY", "")
    nv_key = os.getenv("NVIDIA_API_KEY", "")
    
    return {
        "finnhub": {
            "configured": bool(fh_key),
            "masked": mask(fh_key) if fh_key else None,
        },
        "twelvedata": {
            "configured": bool(td_key),
            "masked": mask(td_key) if td_key else None,
        },
        "nvidia": {
            "configured": bool(nv_key),
            "masked": mask(nv_key) if nv_key else None,
        },
    }


@app.get("/api/earnings/quarters/{ticker}")
async def earnings_quarters(ticker: str):
    """List available quarterly periods for deep-dive analysis.
    Returns {ticker, quarters: ['2026Q1', '2025Q4', ...], latest: '2026Q1'}"""
    ticker = ticker.strip().upper()
    quarters = list_available_quarters(ticker)
    return {
        "ticker": ticker,
        "quarters": quarters,
        "latest": quarters[0] if quarters else None,
        "count": len(quarters),
    }


@app.get("/api/metrics-history/{ticker}")
async def metrics_history(ticker: str):
    """Return quarterly financial time series for interactive charts.
    
    Returns [{quarter, date, revenue, net_income, ebitda, gross_profit, eps,
              operating_income, operating_cash_flow, capex, free_cash_flow,
              cash_and_equivalents, total_debt, diluted_shares}]
    sorted chronologically (newest first, compatible with existing frontend).
    Uses yfinance directly (local PC only — not for Render deployment).
    """
    ticker = ticker.strip().upper()
    try:
        import yfinance as yf
        import pandas as pd
        stock = yf.Ticker(ticker)
        fin = stock.quarterly_financials
        if fin is None or fin.empty:
            return {"ticker": ticker, "quarters": [], "error": "No financial data"}
        
        # Build quarter-indexed dict — start with ALL quarters from all sources
        # (yfinance income statement returns ~5Q; balance sheet and cash flow return ~7Q.
        #  Merge all to show the full available history to the user.)
        is_data = {}

        def _quarter_key(ts) -> str:
            """Convert pandas Timestamp/date to quarter label like 2025Q4."""
            if hasattr(ts, "year") and hasattr(ts, "month"):
                return f"{ts.year}Q{(ts.month - 1)//3 + 1}"
            d = pd.Timestamp(ts)
            return f"{d.year}Q{(d.month - 1)//3 + 1}"

        # Discover ALL quarter keys first (from all 3 sources)
        all_quarters = set()
        for col_date in fin.columns:
            all_quarters.add(_quarter_key(col_date))
        try:
            cf = getattr(stock, "quarterly_cashflow", None)
            if cf is not None and not cf.empty:
                for col_date in cf.columns:
                    all_quarters.add(_quarter_key(col_date))
        except Exception:
            cf = None
        try:
            bs = getattr(stock, "quarterly_balance_sheet", None)
            if bs is not None and not bs.empty:
                for col_date in bs.columns:
                    all_quarters.add(_quarter_key(col_date))
        except Exception:
            bs = None

        # Pre-populate all quarters (so BS/CF-only quarters appear with IS fields = None)
        for q in all_quarters:
            is_data[q] = {}

        # Income statement
        for col_date in fin.columns:
            quarter_label = _quarter_key(col_date)
            date_str = col_date.strftime("%Y-%m-%d")
            row = fin[col_date]
            is_data[quarter_label]["date"] = date_str
            is_data[quarter_label]["revenue"] = _safe_float(row.get("Total Revenue"))
            is_data[quarter_label]["net_income"] = _safe_float(row.get("Net Income"))
            is_data[quarter_label]["ebitda"] = _safe_float(row.get("EBITDA"))
            is_data[quarter_label]["gross_profit"] = _safe_float(row.get("Gross Profit"))
            is_data[quarter_label]["eps"] = _safe_float(row.get("Basic EPS"))
            is_data[quarter_label]["operating_income"] = _safe_float(row.get("Operating Income"))
            is_data[quarter_label]["diluted_shares"] = _safe_float(row.get("Diluted Average Shares"))
            is_data[quarter_label]["pretax_income"] = _safe_float(row.get("Pretax Income"))
            is_data[quarter_label]["tax_provision"] = _safe_float(row.get("Tax Provision"))

        # Cash flow statement
        try:
            if cf is not None and not cf.empty:
                for col_date in cf.columns:
                    quarter_label = _quarter_key(col_date)
                    row = cf[col_date]
                    # Keep the quarter date even when income statement data is missing.
                    is_data[quarter_label].setdefault("date", col_date.strftime("%Y-%m-%d"))
                    is_data[quarter_label]["operating_cash_flow"] = _safe_float(row.get("Operating Cash Flow"))
                    is_data[quarter_label]["capex"] = _safe_float(row.get("Capital Expenditure"))
                    # FCF: yfinance provides it pre-computed; fallback: OCF + Capex
                    # (yfinance capex is always negative, so OCF + Capex = OCF - |Capex|)
                    fcf = _safe_float(row.get("Free Cash Flow"))
                    if fcf is None:
                        ocf = is_data[quarter_label].get("operating_cash_flow")
                        cpx = is_data[quarter_label].get("capex")
                        fcf = (ocf + cpx) if (ocf is not None and cpx is not None) else None
                    is_data[quarter_label]["free_cash_flow"] = fcf
        except Exception:
            logger.debug(f"metrics-history[{ticker}]: cash flow fetch skipped")

        # Balance sheet
        try:
            if bs is not None and not bs.empty:
                for col_date in bs.columns:
                    quarter_label = _quarter_key(col_date)
                    row = bs[col_date]
                    # Keep the quarter date even when income statement data is missing.
                    is_data[quarter_label].setdefault("date", col_date.strftime("%Y-%m-%d"))
                    is_data[quarter_label]["cash_and_equivalents"] = _safe_float(row.get("Cash And Cash Equivalents"))
                    is_data[quarter_label]["total_debt"] = _safe_float(row.get("Total Debt"))
                    is_data[quarter_label]["total_assets"] = _safe_float(row.get("Total Assets"))
                    is_data[quarter_label]["stockholders_equity"] = _safe_float(row.get("Stockholders Equity"))
                    is_data[quarter_label]["invested_capital"] = _safe_float(row.get("Invested Capital"))
        except Exception:
            logger.debug(f"metrics-history[{ticker}]: balance sheet fetch skipped")

        # Build sorted list (newest → oldest) and drop quarters that are 100% empty.
        field_names = [
            "revenue", "net_income", "ebitda", "gross_profit", "eps",
            "operating_income", "operating_cash_flow", "capex", "free_cash_flow",
            "cash_and_equivalents", "total_debt", "diluted_shares",
            "pretax_income", "tax_provision",
            "total_assets", "stockholders_equity", "invested_capital",
        ]
        quarters = []
        dropped_empty_quarters = []
        for q in sorted(is_data.keys(), reverse=True):  # newest first (frontend expects this)
            entry = {"quarter": q, "date": is_data[q].get("date")}
            for f in field_names:
                entry[f] = is_data[q].get(f)

            # Drop fully-empty rows (all numeric fields missing) to avoid false N/A quarters.
            if not any(entry.get(f) is not None for f in field_names):
                dropped_empty_quarters.append(q)
                continue
            quarters.append(entry)

        payload = {
            "ticker": ticker,
            "currency": "USD",
            "source": "SEC filings / Yahoo Finance",
            "quarters": quarters,
            "count": len(quarters),
        }
        if dropped_empty_quarters:
            payload["dropped_empty_quarters"] = dropped_empty_quarters
            payload["dropped_count"] = len(dropped_empty_quarters)
        return payload
    except Exception as e:
        logger.warning(f"metrics-history[{ticker}]: {e}")
        return {"ticker": ticker, "quarters": [], "error": str(e)}


def _safe_float(val):
    """Convert pandas/numpy value to safe float or None."""
    if val is None:
        return None
    try:
        import pandas as pd
        if pd.isna(val):
            return None
    except Exception:
        pass
    try:
        f = float(val)
        return None if (f != f) else f  # NaN check
    except (ValueError, TypeError):
        return None


@app.post("/api/earnings/deep-dive", response_model=DeepDiveResponse, dependencies=[Depends(_require_auth)])
async def earnings_deep_dive(request: DeepDiveRequest):
    """Generate a standalone earnings call deep-dive.
    Use quarter param (e.g. '2025Q4') for historical analysis."""
    # If quarter specified and metrics not fully populated, fetch quarter-specific data
    if request.quarter != "latest quarter":
        q_data = get_yahoo_data_for_quarter(request.ticker, request.quarter)
        if q_data:
            from backend.pipeline import _deep_dive_metrics
            from backend.models import AnalysisResult
            dummy = AnalysisResult(
                ticker=request.ticker,
                company_name=q_data.get("company_name", request.ticker),
                retrieved_at=datetime.now(timezone.utc).isoformat(),
                price=q_data.get("price"),
                currency=q_data.get("currency", "USD"),
                sector=q_data.get("sector"),
            )
            request.metrics = _deep_dive_metrics(dummy, q_data)
    else:
        # Latest quarter — fetch fresh yfinance data with revenue_estimate etc.
        try:
            q_data = get_yahoo_data(request.ticker)
            if q_data:
                from backend.pipeline import _deep_dive_metrics
                from backend.models import AnalysisResult
                dummy = AnalysisResult(
                    ticker=request.ticker,
                    company_name=q_data.get("company_name", request.ticker),
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                    price=q_data.get("price"),
                    currency=q_data.get("currency", "USD"),
                    sector=q_data.get("sector"),
                )
                request.metrics = _deep_dive_metrics(dummy, q_data)
        except Exception:
            logger.warning(f"[{request.ticker}] Failed to enrich latest-quarter metrics")
    try:
        from backend.earnings_deep_dive.generator import generate_deep_dive

        response = generate_deep_dive(request)
        
        # Post-generation validation — write result so dossier download gate can check
        try:
            from backend.earnings_deep_dive.deep_dive_validator import validate_deep_dive
            md_path = response.markdown_path
            if md_path and os.path.exists(md_path):
                md_passed, issues = validate_deep_dive(md_path)
                validation = {"passed": md_passed, "issues": issues, "checked_at": datetime.now(timezone.utc).isoformat()}
                val_path = os.path.join(os.path.dirname(md_path), "deep_dive_validation.json")
                with open(val_path, "w") as f:
                    json.dump(validation, f, indent=2)
                logger.info(f"[{request.ticker}] Deep-dive validation: {'PASSED' if md_passed else 'FAILED'} ({len(issues)} issues)")
        except Exception as ve:
            logger.warning(f"[{request.ticker}] Deep-dive validation error: {ve}")
        
        return response
    except Exception as e:
        logger.error(f"[{request.ticker}] Earnings deep-dive generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Earnings deep-dive generation failed: {str(e)}")


@app.get("/api/dossier/{ticker}/status")
async def dossier_status(ticker: str):
    """Check if the full dossier (PDF, Excel, 10-K) is ready for a ticker.
    Returns {ready: bool, files: [...], stage: str}."""
    from backend.async_dossier import get_dossier_status
    status = get_dossier_status(ticker)
    return JSONResponse(status)


@app.get("/api/dossier/{ticker}/download")
async def dossier_download(ticker: str, lang: str = "en", quarter: str = None):
    """Download the complete dossier as ZIP. Generates files synchronously if not ready.
    Converts MD/TXT → PDF on-the-fly. ZIP contains ONLY PDF + XLSX + README.txt.
    Use ?lang=ja for Japanese translated dossier.
    Use ?quarter=2025Q4 for quarter-specific deep-dive (auto-generates)."""
    ticker = ticker.strip().upper()
    dossier_language = _normalize_dossier_language(lang)
    translation_language = _translation_language(dossier_language)
    from backend.async_dossier import get_dossier_status
    status = get_dossier_status(ticker)
    
    # If dossier not ready, generate it synchronously
    if not status.get("ready"):
        logger.info(f"[{ticker}] Dossier not ready — generating synchronously... [lang={lang}]")
        try:
            from backend.pipeline import analyze_ticker
            result = analyze_ticker(ticker, output_base=str(ANALYSES_DIR), language=dossier_language)
            logger.info(f"[{ticker}] Dossier generated — {result.decision} ({result.scoring.total}/40)")
        except Exception as e:
            logger.error(f"[{ticker}] Dossier generation failed: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"Dossier generation failed: {str(e)}"
            )
    
    matches = _find_analysis_dirs(ticker)
    if not matches:
        raise HTTPException(status_code=404, detail=f"No analysis found for {ticker}")
    
    analysis_dir = matches[0]
    
    # If quarter specified, regenerate deep-dive for that quarter
    if quarter and quarter != "latest":
        logger.info(f"[{ticker}] Regenerating deep-dive for quarter={quarter}...")
        from backend.async_dossier import set_dossier_phase, DossierPhase
        set_dossier_phase(ticker, DossierPhase.PDF_GENERATING)
        try:
            from backend.sources_collector import get_yahoo_data_for_quarter
            from backend.pipeline import _deep_dive_metrics
            from backend.models import AnalysisResult
            from backend.earnings_deep_dive.errors import ValidationError
            from datetime import datetime, timezone
            q_data = get_yahoo_data_for_quarter(ticker, quarter)
            if q_data:
                dummy = AnalysisResult(
                    ticker=ticker,
                    company_name=q_data.get("company_name", ticker),
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                    price=q_data.get("price"),
                    currency=q_data.get("currency", "USD"),
                    sector=q_data.get("sector"),
                )
                metrics = _deep_dive_metrics(dummy, q_data)
                
                # ── IR scraping (mirrors _add_earnings_deep_dive_if_transcript) ──
                from backend.pipeline import _investor_relations_url, _company_website, \
                    _extract_next_earnings_from_ir, _extract_audio_webcast_from_ir
                website = _company_website(q_data)
                investor_relations = _investor_relations_url(q_data)
                if investor_relations:
                    metrics = metrics.model_copy(update={"investor_relations_url": investor_relations})
                    next_earnings = _extract_next_earnings_from_ir(investor_relations, ticker)
                    if next_earnings:
                        metrics = metrics.model_copy(update={"next_earnings_date": next_earnings})
                        logger.info(f"[{ticker}] Next earnings date: {next_earnings}")
                    audio_url = _extract_audio_webcast_from_ir(investor_relations, ticker)
                    if audio_url:
                        metrics = metrics.model_copy(update={"earnings_audio_url": audio_url})
                        logger.info(f"[{ticker}] Earnings audio: {audio_url}")
                if website:
                    metrics = metrics.model_copy(update={"company_website": website})
                
                from backend.earnings_deep_dive.generator import generate_deep_dive

                response = generate_deep_dive(DeepDiveRequest(
                    ticker=ticker,
                    company=q_data.get("company_name", ticker),
                    quarter=quarter,
                    language=dossier_language,
                    output_dir=str(analysis_dir),
                    metrics=metrics,
                ))
                logger.info(f"[{ticker}] Deep-dive regenerated for {quarter}")
                
                # Strip echoed prompt questions from LLM output (mirrors pipeline.py)
                from backend.pipeline import _strip_prompt_leaks_from_sections
                response.sections = _strip_prompt_leaks_from_sections(response.sections)

                # ── Pre-render validation (BLOCKING — hard data contract gate) ──
                set_dossier_phase(ticker, DossierPhase.PDF_VALIDATING)
                from backend.earnings_deep_dive.pre_render_validator import (
                    validate_pre_render,
                    annotate_sections_with_warnings,
                    format_validation_error,
                )
                from backend.earnings_deep_dive.errors import ValidationError
                pre_val = validate_pre_render(
                    ticker=ticker,
                    quarter=quarter,
                    metrics=metrics,
                    section_analysis=response.sections,
                )
                if pre_val.errors:
                    error_msg = format_validation_error(pre_val, ticker)
                    logger.error(error_msg)
                    raise ValidationError(
                        ticker=ticker,
                        errors=pre_val.errors,
                        message=error_msg,
                    )
                elif pre_val.warnings:
                    logger.warning(
                        f"[{ticker}] Pre-render validation: {len(pre_val.warnings)} warning(s) "
                        f"— sections flagged with ⚠️"
                    )
                    response.sections = annotate_sections_with_warnings(
                        response.sections, pre_val,
                    )

                # Render PDF and validate (mirrors _add_earnings_deep_dive_if_transcript)
                from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
                from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf
                from backend.earnings_deep_dive.deep_dive_validator import validate_deep_dive, validate_render_model
                import json as _json
                
                pdf_path = os.path.join(str(analysis_dir), "07_final_report", "earnings_deep_dive.pdf")
                report_model = build_earnings_deep_dive_report(
                    ticker=ticker,
                    company=q_data.get("company_name", ticker),
                    quarter=quarter,
                    language=dossier_language,
                    metrics=metrics,
                    transcript_url=response.transcript_url or "",
                    section_analysis=response.sections,
                )
                render_earnings_deep_dive_pdf(report_model, pdf_path)
                
                # Validate
                md_passed, issues = validate_deep_dive(response.markdown_path)
                render_issues = validate_render_model(report_model)
                passed = md_passed and not render_issues
                val_result = {"passed": passed, "issues": issues + render_issues,
                              "checked_at": datetime.now(timezone.utc).isoformat()}
                val_path = os.path.join(str(analysis_dir), "07_final_report", "deep_dive_validation.json")
                with open(val_path, "w") as f:
                    _json.dump(val_result, f, indent=2)
                logger.info(f"[{ticker}] Deep-dive PDF rendered + validated (passed={passed})")
                set_dossier_phase(ticker, DossierPhase.COMPLETE)
        except ValidationError as ve:
            set_dossier_phase(ticker, DossierPhase.FAILED, error=str(ve))
            logger.error(f"[{ticker}] Data contract violation: {ve}")
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"PDF build blocked — data contract violation for {ticker}",
                    "errors": [{"check": e.check, "detail": e.detail} for e in (ve.errors or [])],
                }
            )
        except Exception as e:
            set_dossier_phase(ticker, DossierPhase.FAILED, error=str(e))
            logger.warning(f"[{ticker}] Deep-dive regeneration for {quarter} failed: {e}")

    status = get_dossier_status(ticker)
    if not status.get("download_enabled"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Dossier generated but not verified; download is blocked.",
                "issues": status.get("verification_issues", []),
                "deep_dive_validated": status.get("deep_dive_validated"),
            },
        )
    
    # Translate dossier content if non-English language requested
    # NEVER mutate originals — work on a temp copy (Codex P0 audit 2026-05-05)
    # NOTE: translation is deferred to async background to avoid Cloudflare tunnel timeouts
    work_dir = None
    if dossier_language != "en":
        logger.info(f"[{ticker}] Skipping synchronous translation to {dossier_language} (deferred to async)")
    # Translation disabled for now — was causing 100s+ delays and tunnel timeouts
    
    # Use the translated temp dir if available, otherwise original
    source_dir = work_dir if work_dir else analysis_dir
    
    # Pre-convert MD/TXT files to PDF on-the-fly 
    try:
        from backend.pdf_generator import md_to_pdf
        refresh_pdf = work_dir is not None
        for fpath in sorted(source_dir.rglob("*.md")):
            pdf_path = fpath.with_suffix(".pdf")
            if _should_convert_dossier_text_to_pdf(fpath, refresh_pdf=refresh_pdf):
                try:
                    md_to_pdf(str(fpath), str(pdf_path), title=f"{ticker} — {fpath.stem.replace('_', ' ').title()}")
                    logger.info(f"[{ticker}] Converted {fpath.name} → PDF")
                except Exception as e:
                    logger.warning(f"[{ticker}] MD→PDF failed for {fpath.name}: {e}")
        for fpath in sorted(source_dir.rglob("*.txt")):
            pdf_path = fpath.with_suffix(".pdf")
            if _should_convert_dossier_text_to_pdf(fpath, refresh_pdf=refresh_pdf):
                try:
                    md_to_pdf(str(fpath), str(pdf_path), title=f"{ticker} — {fpath.stem.replace('_', ' ').title()}")
                    logger.info(f"[{ticker}] Converted {fpath.name} → PDF")
                except Exception as e:
                    logger.warning(f"[{ticker}] TXT→PDF failed for {fpath.name}: {e}")
    except Exception as e:
        logger.warning(f"[{ticker}] On-the-fly PDF conversion error: {e}")
    
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        included_dirs = set()
        for fpath in sorted(source_dir.rglob("*")):
            if fpath.is_file():
                rel_parts = fpath.relative_to(source_dir).parts
                if rel_parts and rel_parts[0] in ("en", "jp") and rel_parts[0] != dossier_language:
                    continue
                # Only PDF + XLSX + README.txt + transcript verbatim .txt in the deliverable ZIP
                if fpath.suffix in ('.json', '.csv', '.md'):
                    continue
                if fpath.suffix == '.txt':
                    if fpath.name == 'README.txt':
                        pass  # always include
                    elif '04_transcripts_and_management' in str(fpath) and 'transcript_' in fpath.name:
                        pass  # verbatim transcript — always include
                    else:
                        continue
                arcname = fpath.relative_to(source_dir)
                zf.write(fpath, arcname)
                included_dirs.add(str(arcname.parent))
        
        
        # Ensure ALL 7 directories are represented
        for folder in ["01_official_company_sources", "02_sec_or_regulatory_filings",
                       "03_financial_data_sources", "04_transcripts_and_management",
                       "05_market_and_context", "06_extracted_data", "07_final_report"]:
            if folder not in included_dirs:
                zf.writestr(f"{folder}/README.txt",
                           f"{folder}\n{'='*len(folder)}\n\nDossier section — see full report for details.\n")
        for language in (dossier_language,):
            if (source_dir / language).is_dir():
                for folder in ["01_official_company_sources", "02_sec_or_regulatory_filings",
                               "03_financial_data_sources", "04_transcripts_and_management",
                               "05_market_and_context", "06_extracted_data", "07_final_report"]:
                    lang_folder = f"{language}/{folder}"
                    if lang_folder not in included_dirs:
                        zf.writestr(f"{lang_folder}/README.txt",
                                   f"{folder}\n{'='*len(folder)}\n\nDossier section — see full report for details.\n")
    
    lang_suffix = f"_{dossier_language}" if dossier_language != "en" else ""
    buf.seek(0)
    
    # Clean up temp dir if translation created one
    if work_dir:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
            logger.debug(f"[{ticker}] Temp translation dir cleaned up")
        except Exception as e:
            logger.debug(f"Fallback: {e}")
    
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={ticker}_dossier{lang_suffix}.zip"},
    )


@app.post("/api/dossier/{ticker}/upload", dependencies=[Depends(_require_auth)])
async def dossier_upload(
    ticker: str,
    section: str = Form(...),
    file: UploadFile = FastAPIFile(...),
    x_upload_secret: str = Header(None, alias="X-Upload-Secret"),
):
    """Upload a file to a dossier section. Used by local machine (lapced) to fill gaps.
    
    Authenticated via X-Upload-Secret header matching DOSSIER_UPLOAD_SECRET env var.
    """
    upload_secret = os.getenv("DOSSIER_UPLOAD_SECRET", "")
    if not upload_secret:
        raise HTTPException(status_code=501, detail="Upload endpoint not configured")
    if not x_upload_secret or x_upload_secret != upload_secret:
        raise HTTPException(status_code=403, detail="Invalid or missing upload secret")
    
    # Section validation
    ALLOWED_SECTIONS = {
        "01_official_company_sources", "02_sec_or_regulatory_filings",
        "03_financial_data_sources", "04_transcripts_and_management",
        "05_market_and_context", "06_extracted_data", "07_final_report",
    }
    if section not in ALLOWED_SECTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid section: {section}")
    
    # Sanitize filename
    safe_name = os.path.basename(file.filename)
    if not safe_name or safe_name.startswith('.'):
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Enforce max upload size (50 MB)
    MAX_UPLOAD_BYTES = 50 * 1024 * 1024
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024*1024)}MB limit")
    await file.seek(0)
    
    # Find analysis directory — only upload to existing analyses (never create dummy dirs)
    ticker_clean = ticker.replace(".", "_").upper()
    matches = sorted(ANALYSES_DIR.glob(f"*_{ticker_clean}_*"), reverse=True)
    if not matches:
        raise HTTPException(status_code=404, detail=f"No analysis found for {ticker}. Run an analysis first.")
    
    # Prefer real analysis dirs over dummy UPLOADED dirs
    analysis_dir = None
    for m in matches:
        has_report = (m / "07_final_report" / "report.md").exists() or \
                     (m / "07_final_report" / "report.pdf").exists()
        if has_report or "UPLOADED" not in str(m):
            analysis_dir = m
            break
    if not analysis_dir:
        analysis_dir = matches[0]
    
    # Save file
    target_dir = analysis_dir / section
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / safe_name
    
    content = await file.read()
    with open(target_path, "wb") as f:
        f.write(content)
    
    logger.info(f"[{ticker}] Uploaded {safe_name} → {section} ({len(content)} bytes)")
    
    return JSONResponse({
        "status": "uploaded",
        "section": section,
        "filename": safe_name,
        "size": len(content),
    })


@app.post("/api/analyze", dependencies=[Depends(_require_auth)])
async def analyze(request: TickerRequest, lang: str = "en", force_refresh: bool = False, fastapi_request: Request = None):
    """Submit tickers for analysis. Runs sequentially, returns results immediately.
    Use ?lang=ja for Japanese labels. Use ?force_refresh=true to bypass cache."""
    tickers = request.tickers
    logger.info(f"Analyze request: {tickers} [lang={lang}, force_refresh={force_refresh}]")
    t_start = time.time()

    # Normalize: resolve ISINs to tickers before validation
    normalized_tickers = []
    for t in tickers:
        t_upper = t.upper().strip()
        if ISIN_RE.match(t_upper) and _isin_checksum(t_upper):
            resolved = ISIN_TO_TICKER.get(t_upper) or _isin_to_ticker_lookup(t_upper)
            if resolved:
                logger.info(f"ISIN {t_upper} → {resolved}")
                normalized_tickers.append(resolved)
                continue
        normalized_tickers.append(t_upper)

    # Validate all tickers before processing
    invalid_tickers = [t for t in normalized_tickers if not TICKER_RE.match(t)]
    if invalid_tickers:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Invalid ticker format",
                "invalid": invalid_tickers,
                "message": f"Tickers must be 1-5 uppercase letters (e.g. AAPL, NVDA, BRK.B). Invalid: {', '.join(invalid_tickers)}"
            }
        )

    try:
        import asyncio as _asyncio
        from backend.async_dossier import set_dossier_phase, DossierPhase
        for t in normalized_tickers:
            set_dossier_phase(t, DossierPhase.SCORING)
        batch = await _asyncio.to_thread(run_analysis_parallel, normalized_tickers, output_base=str(ANALYSES_DIR), language=lang, force_refresh=force_refresh)
    except Exception as e:
        logger.exception("Batch analysis failed")
        raise HTTPException(status_code=500, detail=str(e))

    from backend.i18n import translate

    results_list = []
    errors_list = list(batch["errors"].values())

    for ticker, result in batch["results"].items():
        set_dossier_phase(ticker, DossierPhase.SCORED)
        r = result.model_dump()
        # Include financials summary for frontend display
        fin = r.get("financials", {})
        val = r.get("valuation", {})
        r["financial_summary"] = {
            "revenue_annual": fin.get("revenue_annual"),
            "net_income": fin.get("net_income"),
            "free_cash_flow": fin.get("free_cash_flow"),
            "gross_margin": fin.get("gross_margin"),
            "operating_margin": fin.get("operating_margin"),
            "pe_current": val.get("pe_current"),
            "pe_forward": val.get("pe_forward"),
        }
        r.pop("financials", None)  # keep only summary to reduce payload
        r.pop("management_tone", None)
        r.pop("segments", None)
        r.pop("valuation", None)  # PE ratios now in financial_summary
        # Include computed total (Pydantic doesn't serialize @property)
        if "scoring" in r and isinstance(r["scoring"], dict):
            r["scoring"]["total"] = result.scoring.total
        # Translate labels based on lang
        if lang != "en":
            if "decision" in r:
                r["decision"] = translate(r["decision"], lang)
            if "conviction" in r:
                r["conviction"] = translate(r["conviction"], lang)
        results_list.append(r)

    logger.info(f"Analyze complete: {len(results_list)} tickers, {len(errors_list)} errors [{time.time()-t_start:.1f}s, lang={lang}]")
    
    # Log each ticker search for near-real-time monitoring
    duration_ms = (time.time() - t_start) * 1000
    ua = fastapi_request.headers.get("user-agent", "") if fastapi_request else ""
    client_ip = fastapi_request.client.host if fastapi_request and fastapi_request.client else "unknown"
    for r_item in results_list:
        log_search(r_item["ticker"], "completed", duration_ms, user_agent=ua, client_ip=client_ip)
    for ticker_err in errors_list:
        log_search(ticker_err, "failed", duration_ms, error=ticker_err, user_agent=ua, client_ip=client_ip)
    
    return JSONResponse({
        "status": "completed" if not batch["errors"] else "partial",
        "results": results_list,
        "errors": errors_list,
    })


@app.post("/api/analyze/async", dependencies=[Depends(_require_auth)])
async def analyze_async(request: TickerRequest, lang: str = "en", fastapi_request: Request = None):
    """Submit tickers for async analysis. Returns job ID immediately, poll /api/analyze/job/{id}."""
    tickers = request.tickers
    logger.info(f"Async analyze request: {tickers} [lang={lang}]")

    # Normalize ISINs
    normalized_tickers = []
    for t in tickers:
        t_upper = t.upper().strip()
        if ISIN_RE.match(t_upper) and _isin_checksum(t_upper):
            resolved = ISIN_TO_TICKER.get(t_upper) or _isin_to_ticker_lookup(t_upper)
            if resolved:
                normalized_tickers.append(resolved)
                continue
        normalized_tickers.append(t_upper)

    invalid_tickers = [t for t in normalized_tickers if not TICKER_RE.match(t)]
    if invalid_tickers:
        raise HTTPException(status_code=422, detail={
            "error": "Invalid ticker format",
            "invalid": invalid_tickers,
        })

    from backend.job_store import create_job, update_job
    job_id = create_job(normalized_tickers, lang)

    # Run analysis in background thread
    do_deep_dive = request.deep_dive  # capture for closure

    def _run():
        try:
            update_job(job_id, status="processing", progress="Starting analysis...")
            import asyncio as _asyncio
            batch = _asyncio.new_event_loop().run_until_complete(
                _asyncio.to_thread(run_analysis_parallel, normalized_tickers, output_base=str(ANALYSES_DIR), language=lang)
            )
            results_list = []
            for ticker, result in batch["results"].items():
                r = result.model_dump()
                fin = r.get("financials", {})
                val = r.get("valuation", {})
                r["financial_summary"] = {
                    "revenue_annual": fin.get("revenue_annual"),
                    "net_income": fin.get("net_income"),
                    "free_cash_flow": fin.get("free_cash_flow"),
                    "gross_margin": fin.get("gross_margin"),
                    "operating_margin": fin.get("operating_margin"),
                    "pe_current": val.get("pe_current"),
                    "pe_forward": val.get("pe_forward"),
                }
                r.pop("financials", None)
                r.pop("management_tone", None)
                r.pop("segments", None)
                r.pop("valuation", None)
                if "scoring" in r and isinstance(r["scoring"], dict):
                    r["scoring"]["total"] = result.scoring.total
                results_list.append(r)

            errors_list = list(batch["errors"].values())

            # ── Deep-dive generation (if requested) ──
            deep_dive_pdfs = {}
            if do_deep_dive:
                update_job(job_id, status="processing", progress="Generating deep-dive PDFs...")
                from backend.earnings_deep_dive.generator import generate_deep_dive
                from backend.earnings_deep_dive.schemas import DeepDiveRequest
                from backend.sources_collector import get_yahoo_data_for_quarter
                from backend.pipeline import _deep_dive_metrics
                from backend.models import AnalysisResult
                from datetime import datetime, timezone
                import os as _os
                for ticker_name, result in batch["results"].items():
                    try:
                        matches = _find_analysis_dirs(ticker_name)
                        if not matches:
                            continue
                        out_dir = str(matches[0])
                        q_data = get_yahoo_data_for_quarter(ticker_name, "2026Q1")
                        if not q_data:
                            continue
                        dummy = AnalysisResult(
                            ticker=ticker_name,
                            company_name=q_data.get("company_name", ticker_name),
                            retrieved_at=datetime.now(timezone.utc).isoformat(),
                            price=q_data.get("price"),
                            currency=q_data.get("currency", "USD"),
                        )
                        metrics = _deep_dive_metrics(dummy, q_data)
                        dd_req = DeepDiveRequest(
                            ticker=ticker_name,
                            company=q_data.get("company_name", ticker_name),
                            quarter="2026Q1",
                            language=lang,
                            output_dir=out_dir,
                            metrics=metrics.model_dump(),
                        )
                        dd_resp = generate_deep_dive(dd_req)
                        if dd_resp and dd_resp.markdown_path:
                            deep_dive_pdfs[ticker_name] = {
                                "markdown": dd_resp.markdown_path,
                                "sections": len(dd_resp.sections),
                            }
                            logger.info(f"[{job_id}] Deep-dive PDF generated for {ticker_name}")
                    except Exception as dd_err:
                        logger.warning(f"[{job_id}] Deep-dive failed for {ticker_name}: {dd_err}")
                        deep_dive_pdfs[ticker_name] = {"error": str(dd_err)}

            # Log searches for admin dashboard
            ua = fastapi_request.headers.get("user-agent", "") if fastapi_request else ""
            client_ip = fastapi_request.client.host if fastapi_request and fastapi_request.client else ""
            for r_item in results_list:
                log_search(r_item["ticker"], "completed", 0, user_agent=ua, client_ip=client_ip)
            for ticker_err in batch.get("errors", {}):
                log_search(ticker_err, "failed", 0, error=str(batch["errors"][ticker_err]), user_agent=ua, client_ip=client_ip)
            
            update_job(job_id, status="done", progress="Complete",
                       result={"results": results_list, "errors": errors_list,
                               "deep_dive": deep_dive_pdfs if do_deep_dive else None})
        except Exception as e:
            logger.exception(f"Async job {job_id} failed")
            update_job(job_id, status="error", progress="Failed", error=str(e))

    import threading
    threading.Thread(target=_run, daemon=True).start()

    return JSONResponse({"job_id": job_id, "status": "pending"})


@app.get("/api/analyze/job/{job_id}")
async def get_job_status(job_id: str):
    """Poll for async analysis job status."""
    from backend.job_store import get_job
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse(job)


@app.head("/api/report/{ticker}/pdf")
@app.get("/api/report/{ticker}/pdf")
async def get_report_pdf(ticker: str, lang: str = "en", quarter: str = "latest", audience_mode: str = "nami_personal", background_tasks: BackgroundTasks = None):
    """Serve the earnings deep-dive PDF for a ticker in the requested language.
    Use ?lang=ja or ?lang=jp for Japanese, ?quarter=2026Q1 for specific quarter,
    ?audience_mode=client_report for client-ready output. Defaults to English, nami_personal."""
    ticker = ticker.strip().upper()
    matches = _find_analysis_dirs(ticker)
    if not matches:
        raise HTTPException(status_code=404, detail=f"No analysis found for {ticker}")

    # Language-specific path
    analysis_dir = matches[0]
    if lang == "jp":
        deep_dive = analysis_dir / "jp" / "07_final_report" / "earnings_deep_dive.pdf"
    else:
        deep_dive = analysis_dir / "07_final_report" / "earnings_deep_dive.pdf"
    report_pdf = analysis_dir / "07_final_report" / "report.pdf"

    # Prefer deep-dive PDF; if it doesn't exist, launch async generation
    # and return 202 Accepted so the client can poll (no 2-min timeout)
    if not deep_dive.exists():
        import asyncio
        
        async def _generate_deep_dive_async(ticker: str, lang: str, dd_path: Path):
            """Background deep-dive generation — runs in thread to not block."""
            from backend.async_dossier import set_dossier_phase, DossierPhase
            set_dossier_phase(ticker, DossierPhase.PDF_GENERATING)
            try:
                from backend.earnings_deep_dive.generator import generate_deep_dive
                from backend.earnings_deep_dive.schemas import DeepDiveRequest
                from backend.pipeline import _deep_dive_metrics
                from backend.sources_collector import get_yahoo_data
                from backend.models import AnalysisResult
                from datetime import datetime, timezone
                import os
                
                q_data = get_yahoo_data(ticker)
                if not q_data:
                    return
                dummy = AnalysisResult(
                    ticker=ticker,
                    company_name=q_data.get("company_name", ticker),
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                    price=q_data.get("price"),
                    currency=q_data.get("currency", "USD"),
                    sector=q_data.get("sector"),
                )
                metrics = _deep_dive_metrics(dummy, q_data)
                
                # ── IR scraping (mirrors _add_earnings_deep_dive_if_transcript) ──
                from backend.pipeline import _investor_relations_url, _company_website, \
                    _extract_next_earnings_from_ir, _extract_audio_webcast_from_ir
                website = _company_website(q_data)
                investor_relations = _investor_relations_url(q_data)
                if investor_relations:
                    metrics = metrics.model_copy(update={"investor_relations_url": investor_relations})
                    next_earnings = _extract_next_earnings_from_ir(investor_relations, ticker)
                    if next_earnings:
                        metrics = metrics.model_copy(update={"next_earnings_date": next_earnings})
                    audio_url = _extract_audio_webcast_from_ir(investor_relations, ticker)
                    if audio_url:
                        metrics = metrics.model_copy(update={"earnings_audio_url": audio_url})
                if website:
                    metrics = metrics.model_copy(update={"company_website": website})
                
                # ── Company Overview (wired into async PDF path) ──
                company_overview = None
                try:
                    import asyncio
                    from backend.company_overview import get_company_overview
                    company_overview = asyncio.run(get_company_overview(ticker, language=lang))
                    logger.info(f"[{ticker}/{lang}] Company overview generated for deep-dive PDF")
                except Exception as e:
                    logger.warning(f"[{ticker}/{lang}] Company overview skipped: {e}")
                
                # Find analysis directory for output_dir (required by schema)
                # dd_path is .../07_final_report/earnings_deep_dive.pdf, parent.parent = analysis_dir
                output_dir = str(dd_path.parent.parent)
                dd_req = DeepDiveRequest(ticker=ticker, quarter=quarter, language=lang,
                                         output_dir=output_dir, metrics=metrics,
                                         audience_mode=audience_mode)
                dd_response = generate_deep_dive(dd_req)
                
                # ── Pre-render validation (BLOCKING — hard data contract gate) ──
                set_dossier_phase(ticker, DossierPhase.PDF_VALIDATING)
                from backend.earnings_deep_dive.pre_render_validator import (
                    validate_pre_render,
                    annotate_sections_with_warnings,
                    format_validation_error,
                )
                from backend.earnings_deep_dive.errors import ValidationError
                sections = getattr(dd_response, 'sections', None)
                pre_val = validate_pre_render(
                    ticker=ticker,
                    quarter=dd_req.quarter,
                    metrics=metrics,
                    section_analysis=sections,
                )
                if pre_val.errors:
                    error_msg = format_validation_error(pre_val, ticker)
                    logger.error(error_msg)
                    raise ValidationError(
                        ticker=ticker,
                        errors=pre_val.errors,
                        message=error_msg,
                    )
                elif pre_val.warnings:
                    sections = annotate_sections_with_warnings(
                        sections or {}, pre_val,
                    )
                
                from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
                from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf
                report_model = build_earnings_deep_dive_report(
                    ticker=ticker,
                    company=dummy.company_name,
                    quarter=dd_req.quarter,
                    metrics=metrics,
                    transcript_url=getattr(dd_response, 'transcript_url', None),
                    language=lang,
                    section_analysis=sections,
                    company_overview=company_overview,
                    yf_info=q_data.get("_raw_info"),
                )
                os.makedirs(dd_path.parent, exist_ok=True)
                render_earnings_deep_dive_pdf(report_model, str(dd_path))
                set_dossier_phase(ticker, DossierPhase.COMPLETE)
            except ValidationError as ve:
                set_dossier_phase(ticker, DossierPhase.FAILED, error=str(ve))
                import logging
                logging.getLogger("uvicorn.error").error(
                    f"Data contract violation for {ticker}: {ve}"
                )
                # Return 422 immediately — don't launch async, data is bad
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": f"PDF build blocked — data contract violation for {ticker}",
                        "errors": [{"check": e.check, "detail": e.detail} for e in (ve.errors or [])],
                    }
                )
            except Exception as e:
                set_dossier_phase(ticker, DossierPhase.FAILED, error=str(e))
                import logging
                logging.getLogger("uvicorn.error").error(f"Deep-dive generation failed for {ticker}: {e}")
        
        # Launch async — use thread for reliability (BackgroundTasks can be flaky with --workers)
        import threading
        thread = threading.Thread(
            target=lambda: asyncio.run(_generate_deep_dive_async(ticker, lang, deep_dive)),
            daemon=True
        )
        thread.start()
        
        # Return 202 with polling info
        return JSONResponse(
            status_code=202,
            content={
                "status": "generating",
                "ticker": ticker,
                "message": "Deep-dive PDF generation started. Poll this endpoint until ready.",
                "retry_after_seconds": 10,
            },
            headers={"Retry-After": "10"},
        )
    
    pdf_path = deep_dive if deep_dive.exists() else report_pdf
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"No PDF found for {ticker}")

    # Generate ticker-aware filename for browser save dialog: MSFT_deep_dive.pdf
    pdf_filename = f"{ticker}_deep_dive.pdf"
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=None,
        headers={"Content-Disposition": f"inline; filename=\"{pdf_filename}\""}
    )


@app.head("/api/report/{ticker}")
@app.get("/api/report/{ticker}")
async def get_report(ticker: str):
    """Retrieve the full markdown report for a ticker."""
    # Find the latest analysis directory for this ticker
    ticker = ticker.strip().upper()
    matches = _find_analysis_dirs(ticker)
    if not matches:
        raise HTTPException(status_code=404, detail=f"No analysis found for {ticker}")

    report_path = matches[0] / "07_final_report" / "report.md"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found for {ticker}")

    return FileResponse(report_path, media_type="text/markdown")


@app.get("/api/sources/{ticker}")
async def get_sources(ticker: str):
    """Retrieve the sources manifest for a ticker."""
    ticker = ticker.strip().upper()
    matches = _find_analysis_dirs(ticker)
    if not matches:
        raise HTTPException(status_code=404, detail=f"No analysis found for {ticker}")

    manifest_path = matches[0] / "06_extracted_data" / "sources_manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Manifest not found for {ticker}")

    return FileResponse(manifest_path, media_type="application/json")


@app.get("/api/traceability/{ticker}")
async def get_traceability(ticker: str):
    """Retrieve the claim traceability matrix for a ticker."""
    ticker = ticker.strip().upper()
    matches = _find_analysis_dirs(ticker)
    if not matches:
        raise HTTPException(status_code=404, detail=f"No analysis found for {ticker}")

    csv_path = matches[0] / "06_extracted_data" / "claim_traceability_matrix.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"Traceability matrix not found for {ticker}")

    return FileResponse(csv_path, media_type="text/csv")


@app.get("/api/valuation/{ticker}", response_model=ValuationV2Response)
async def get_valuation(ticker: str):
    """V2.3 — Market valuation data with EUR conversion.

    Returns price, market cap, enterprise value, shares outstanding,
    cash, debt, and EUR equivalents computed from live/cached FX rates.
    """
    from backend.valuation import get_valuation as _get_valuation
    from backend.models import ValuationV2Response
    try:
        return _get_valuation(ticker)
    except Exception:
        import logging
        logger = logging.getLogger("valuation_endpoint")
        logger.exception("Valuation endpoint failed for %s", ticker)
        return ValuationV2Response(
            ticker=ticker.upper().strip(),
            status="unavailable",
        )


@app.post("/api/cache/financials/{ticker}", dependencies=[Depends(_require_auth)])
async def cache_financials(
    ticker: str,
    body: dict = Body(...),
    x_upload_secret: str = Header(None, alias="X-Upload-Secret"),
):
    """Upload yfinance financial data from local machine (lapced).
    
    The local cron fetches yfinance data (blocked on Render's shared IP)
    and pushes it to this endpoint. The backend then merges it with Finnhub.
    
    Authenticated via X-Upload-Secret matching DOSSIER_UPLOAD_SECRET.
    Body: JSON with the same structure as get_yahoo_data()'s output.
    """
    upload_secret = os.getenv("DOSSIER_UPLOAD_SECRET", "")
    if not upload_secret:
        raise HTTPException(status_code=501, detail="Upload endpoint not configured")
    if not x_upload_secret or x_upload_secret != upload_secret:
        raise HTTPException(status_code=403, detail="Invalid or missing upload secret")
    
    if not body or not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    # Sanitize NaN/inf values (yfinance can return numpy NaN for some fields)
    body = _sanitize_json(body)
    
    ticker_upper = ticker.upper()
    cache_dir = Path("backend/.cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Write yfinance-only cache (used as fallback during fresh get_stock_data calls)
    yf_path = cache_dir / f"{ticker_upper}_yf.json"
    entry = {"timestamp": datetime.now(timezone.utc).timestamp(), "data": body}
    with open(yf_path, "w") as f:
        json.dump(entry, f)
    
    # 2. If main stock data cache exists, enrich it immediately with yfinance data
    # This ensures PE/revenue show up even if the container restarts later
    main_path = cache_dir / f"{ticker_upper}.json"
    enriched = False
    if main_path.exists():
        try:
            with open(main_path) as f:
                main_entry = json.load(f)
            main_data = main_entry.get("data", main_entry)
            yf_fin = body.get("financials", {})
            main_fin = main_data.get("financials", {})
            
            for key in ["revenue_quarterly", "revenue_annual", "net_income",
                       "free_cash_flow", "net_debt"]:
                if main_fin.get(key) is None and yf_fin.get(key) is not None:
                    main_fin[key] = yf_fin[key]
                    enriched = True
            for key in ["pe_current", "pe_forward", "peg_ratio", "beta",
                       "52w_high", "52w_low"]:
                if main_data.get(key) is None and body.get(key) is not None:
                    main_data[key] = body[key]
                    enriched = True
            
            if enriched:
                main_entry["data"] = main_data
                main_entry["timestamp"] = datetime.now(timezone.utc).timestamp()
                with open(main_path, "w") as f:
                    json.dump(main_entry, f)
                logger.info(f"[{ticker}] Main cache enriched with yfinance data")
        except Exception as e:
            logger.warning(f"[{ticker}] Main cache enrichment failed: {e}")
    
    logger.info(f"[{ticker}] Financials cached ({len(json.dumps(body))} bytes)" +
                (", main cache enriched" if enriched else ""))
    return JSONResponse({"status": "cached", "ticker": ticker_upper,
                         "enriched": enriched})


@app.get("/api/analyses", dependencies=[Depends(_require_auth)])
async def list_analyses():
    """List all analyzed tickers with dates, names, and file counts.
    
    Scans the analyses/ directory for completed dossiers.
    Returns {analyses: [{ticker, company_name, date, files, directory}]} sorted newest first.
    """
    import re
    from pathlib import Path
    
    analyses = []
    if not ANALYSES_DIR.exists():
        return JSONResponse({"analyses": []})
    
    for entry in sorted(ANALYSES_DIR.iterdir(), reverse=True):
        if not entry.is_dir() or entry.name == "UPLOADED" or entry.name.startswith('.'):
            continue
        
        # Count real files (exclude README.txt placeholders)
        all_files = [f for f in entry.rglob("*") if f.is_file()]
        real_files = [f for f in all_files if f.name != "README.txt"]
        
        # Parse naming convention: YYYY-MM-DD_TICKER_NAME
        # Example: 2026-05-04_NVDA_NVIDIA_Corp
        name = entry.name
        ticker = _ticker_from_analysis_dir(entry) or "?"
        company_name = name
        date_str = ""
        has_report = (entry / "07_final_report" / "report.md").exists() or \
                     (entry / "07_final_report" / "report.pdf").exists()
        
        date_match = re.match(r"^(\d{4}-\d{2}-\d{2}|\d{8})_(.+)$", name)
        if date_match:
            raw_date, rest = date_match.groups()
            date_str = (
                f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
                if raw_date.isdigit()
                else raw_date
            )
            ticker_key = ticker.replace(".", "_") if ticker != "?" else ""
            if ticker_key and rest.startswith(f"{ticker_key}_"):
                company_name = rest[len(ticker_key) + 1:]
            else:
                company_name = rest.split("_", 1)[1] if "_" in rest else rest
        
        analyses.append({
            "ticker": ticker,
            "company_name": company_name.replace('_', ' ').strip() if company_name != name else "",
            "date": date_str,
            "files": len(real_files),
            "has_report": has_report,
            "directory": str(entry),
        })
    
    return JSONResponse({"analyses": analyses})


@app.get("/api/admin/recent-searches", dependencies=[Depends(_require_auth)])
async def recent_searches(limit: int = 50, offset: int = 0, status: str = "all"):
    """Get recent search events for near-real-time monitoring.
    
    Query params:
    - limit: max number of events (default 50, max 200)
    - offset: pagination offset (default 0)
    - status: "all", "completed", or "failed" (default "all")
    
    Returns {total: int, searches: [{timestamp, ticker, status, duration_ms, cache_hit, user_agent}]}
    """
    from backend.search_db import read_recent_sqlite, _ensure_db, DB_PATH
    import sqlite3
    results = read_recent_sqlite(limit=max(1, min(limit, 200)), offset=max(0, offset), status_filter=status)
    # Get total count for pagination
    _ensure_db()
    conn = sqlite3.connect(str(DB_PATH))
    total = conn.execute("SELECT COUNT(*) as n FROM searches").fetchone()[0]
    conn.close()
    return JSONResponse({"total": total, "searches": results})


@app.get("/api/admin/search-stats", dependencies=[Depends(_require_auth)])
async def search_stats():
    """Get aggregate search statistics for the admin dashboard.
    
    Returns {total, success_rate, avg_duration_ms, top_tickers, recent_errors, last_24h}
    """
    from backend.search_db import get_stats
    return JSONResponse(get_stats())


# ── Nami Feedback System ──────────────────────────────────────────────
@app.post("/api/feedback", dependencies=[Depends(_require_auth)])
async def submit_feedback(
    ticker: str = Form(""),
    category: str = Form("general"),
    text: str = Form(""),
    files: list[UploadFile] = FastAPIFile(default=[]),
):
    """Submit feedback for a ticker or as general product feedback.

    When ticker is omitted, feedback is stored in the GENERAL bucket so the user can
    submit comments independently from any analysis card.
    """
    from backend.feedback_store import save_feedback
    normalized_ticker = (ticker or "").strip().upper()
    normalized_category = (category or "general").strip().lower().replace(" ", "_")
    if not re.match(r"^[a-z0-9_-]{1,40}$", normalized_category):
        normalized_category = "general"
    if normalized_ticker and not TICKER_RE.match(normalized_ticker):
        raise HTTPException(status_code=422, detail=f"Invalid ticker: {normalized_ticker}")
    if not text.strip() and not files:
        raise HTTPException(status_code=422, detail="Feedback text or at least one attachment is required")
    
    try:
        result = await save_feedback(normalized_ticker or None, text, files, category=normalized_category)
        return JSONResponse({"status": "ok", **result})
    except Exception as e:
        scope = normalized_ticker or "GENERAL"
        logger.error(f"Feedback save failed for {scope}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/feedback", dependencies=[Depends(_require_auth)])
async def list_all_feedback():
    """List all feedback entries across general + per-ticker buckets for the user page."""
    from backend.feedback_store import list_all_feedback as list_all_fb
    entries = list_all_fb()
    return JSONResponse({
        "total": len(entries),
        "unprocessed": sum(1 for entry in entries if not entry.get("processed")),
        "entries": entries,
    })


@app.get("/api/feedback/{ticker}", dependencies=[Depends(_require_auth)])
async def list_ticker_feedback(ticker: str):
    """List all feedback entries for a ticker."""
    from backend.feedback_store import list_feedback as list_fb
    ticker = ticker.strip().upper()
    return JSONResponse(list_fb(ticker))


@app.get("/api/admin/feedback", dependencies=[Depends(_require_auth)])
async def admin_list_feedback():
    """List all feedback across all tickers for the admin dashboard."""
    from backend.feedback_store import get_all_admin_feedback
    return JSONResponse(get_all_admin_feedback())


@app.get("/api/feedback-file/{bucket}/{filename:path}")
async def download_feedback_file(bucket: str, filename: str):
    """Serve a feedback attachment from the canonical feedback bucket store.

    Public read endpoint by design so user-facing feedback links can open directly
    in a new browser tab without exposing API keys in the URL.
    """
    from backend.feedback_store import get_feedback_file_path

    try:
        file_path = get_feedback_file_path(bucket, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Feedback attachment not found") from exc

    media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    return FileResponse(file_path, media_type=media_type)


@app.get("/api/company-overview/{ticker}/download")
async def download_company_overview(ticker: str, format: str = "auto"):
    """Download the best available company overview artifact for a ticker."""
    ticker = ticker.strip().upper()
    selected_format = (format or "auto").strip().lower()
    if selected_format not in {"auto", "pdf", "md", "json"}:
        raise HTTPException(status_code=400, detail="Invalid format. Use auto, pdf, md, or json")

    analysis_dirs = _find_analysis_dirs(ticker)
    if not analysis_dirs:
        raise HTTPException(status_code=404, detail=f"No analysis found for {ticker}")

    order = ["pdf", "md", "json"] if selected_format == "auto" else [selected_format]

    for analysis_dir in analysis_dirs:
        source_dir = analysis_dir / "01_official_company_sources"
        # New naming: {ticker}_company_overview_investor_profile_{date}.pdf
        # Old naming: company_profile_{ticker}.pdf (backward compat)
        pdf_candidates = sorted(
            source_dir.glob(f"{ticker}_company_overview_investor_profile_*.pdf"),
            reverse=True
        )
        legacy_pdf = source_dir / f"company_profile_{ticker}.pdf"
        if not pdf_candidates and legacy_pdf.exists():
            pdf_candidates = [legacy_pdf]

        candidates = {
            "pdf": pdf_candidates[0] if pdf_candidates else source_dir / f"company_profile_{ticker}.pdf",
            "md": source_dir / f"company_profile_{ticker}.md",
            "json": source_dir / f"company_overview_{ticker}.json",
        }

        for kind in order:
            file_path = candidates[kind]
            if file_path.exists():
                media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
                return FileResponse(file_path, media_type=media_type, filename=file_path.name)

    raise HTTPException(status_code=404, detail=f"No company overview artifact found for {ticker}")


@app.get("/api/admin/seeking-alpha/access", dependencies=[Depends(_require_auth)])
async def get_seeking_alpha_access_status():
    from backend.seeking_alpha_access import get_access_status

    return JSONResponse(get_access_status())


@app.post("/api/admin/seeking-alpha/access", dependencies=[Depends(_require_auth)])
async def save_seeking_alpha_access(payload: SeekingAlphaAccessUpdateRequest):
    from backend.seeking_alpha_access import save_access

    try:
        return JSONResponse(save_access(payload.cookie_header, payload.user_agent))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/admin/seeking-alpha/access", dependencies=[Depends(_require_auth)])
async def clear_seeking_alpha_access():
    from backend.seeking_alpha_access import clear_access

    return JSONResponse(clear_access())


@app.post("/api/admin/seeking-alpha/test", dependencies=[Depends(_require_auth)])
async def test_seeking_alpha_access(payload: SeekingAlphaProbeRequest | None = None):
    from backend.seeking_alpha_access import probe_access

    ticker = payload.ticker if payload else "NVDA"
    return JSONResponse(probe_access(ticker))


# ── Cache transparency ──────────────────────────────────────────────────
# Exposes overview cache metadata + flush capability for the frontend.

@app.get("/api/cache/overview/{ticker}")
async def cache_info(ticker: str, lang: str = "en"):
    """Return cache metadata for a ticker's company overview.

    Shows: cached (bool), cached_at (ISO), age_days, ttl_days, expired.
    """
    from backend.company_overview import overview_cache_info
    ticker = ticker.strip().upper()
    return JSONResponse(overview_cache_info(ticker, lang))


@app.post("/api/cache/overview/{ticker}/flush")
async def cache_flush(ticker: str, lang: str = "en"):
    """Flush (delete) cached company overview for a ticker.

    Set lang=all to flush all languages. Returns what was deleted.
    """
    from backend.company_overview import overview_cache_flush
    ticker = ticker.strip().upper()
    language = None if lang == "all" else lang
    return JSONResponse(overview_cache_flush(ticker, language))


# ── Serve React SPA (after all API routes — mono-origin architecture) ──
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class _PrefixStripperMiddleware(BaseHTTPMiddleware):
    """Strip /stock-analysis prefix before routing so both API and static files work.
    
    Cloudflare tunnel forwards sa.cedlabusa.net/stock-analysis/... → localhost:8780 as-is.
    This middleware strips the prefix so FastAPI routes match /api/... and /assets/...
    """
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/stock-analysis"):
            new_path = path[len("/stock-analysis"):] or "/"
            request.scope["path"] = new_path
            request.scope["raw_path"] = new_path.encode()
            request.scope["root_path"] = request.scope.get("root_path", "") + "/stock-analysis"
        response = await call_next(request)
        return response

app.add_middleware(_PrefixStripperMiddleware)

_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"

if _frontend_dist.exists():
    from starlette.staticfiles import StaticFiles as _SF
    from starlette.types import Scope, Receive, Send
    
    class _CacheBustingStaticFiles(_SF):
        """StaticFiles that adds Cache-Control: no-cache to force CDN revalidation."""
        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            async def _send(message):
                if message.get("type") == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"cache-control", b"no-cache, must-revalidate"))
                    message["headers"] = headers
                await send(message)
            await super().__call__(scope, receive, _send)
    
    app.mount("/", _CacheBustingStaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
    logger.info("Frontend mounted from %s", str(_frontend_dist))
else:
    logger.warning("Frontend dist/ not found at %s — API-only mode", str(_frontend_dist))
