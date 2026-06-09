"""FastAPI application for Stock Analysis Pipeline."""
import os
import resource

# Raise file descriptor limit BEFORE any connections are opened (P0 fix 2026-05-30).
# Default soft limit is 1024. Running 2+ parallel analyses with Codex PTYs and
# http_client pools was exhausting FDs → "Too many open files" cascade.
try:
    _soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (max(_soft, 4096), _hard))
    _new_soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
    if _new_soft >= 4096:
        print(f"[main] ulimit NOFILE raised: {_soft} → {_new_soft}")
except Exception:
    pass

# ── Load .env BEFORE anything else ──
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
# ── Clean proxy env vars that break edgartools httpx transport ──
for _k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
    os.environ.pop(_k, None)

import uuid
import logging
from pathlib import Path
from typing import Any, List

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
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, RedirectResponse
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


def _record_pdf_client_failure(
    ticker: str,
    *,
    source: str,
    status: str,
    message: str,
    issues: list[str] | None = None,
    language: str = "en",
    quarter: str = "latest",
    directory: str = "",
) -> None:
    """Record a client-visible PDF failure and launch one proactive RCA task.

    A successful ticker analysis (HTTP 200) is not a client success if the PDF/ZIP
    cannot be opened or downloaded. This helper writes a failed event to the admin
    search log and triggers idempotent Kanban intake for root-cause analysis.
    """
    safe_issues = [str(issue) for issue in (issues or []) if str(issue).strip()]
    error_text = message
    if safe_issues:
        error_text = f"{message} | first_issue={safe_issues[0]}"
    try:
        log_search(
            ticker,
            "failed",
            0,
            error=f"{source}:{status}: {error_text}",
            user_agent="pdf-client-failure",
            client_ip="server",
        )
    except Exception:
        logger.exception("[%s] Failed to log PDF client failure", ticker)

    def _run_intake() -> None:
        try:
            from backend.feedback_pipeline import process_pdf_failure
            process_pdf_failure(
                ticker=ticker,
                source=source,
                status=status,
                message=message,
                issues=safe_issues,
                language=language,
                quarter=quarter,
                directory=directory,
            )
        except Exception:
            logger.exception("[%s] Failed to process proactive PDF failure intake", ticker)

    try:
        import threading
        threading.Thread(target=_run_intake, daemon=True).start()
    except Exception:
        logger.exception("[%s] Failed to start PDF failure intake thread", ticker)


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
from backend.logging_config import setup_logging, get_logger, log_context
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
_HEAVY_PATHS = {"/api/analyze", "/api/analyze/async", "/api/earnings/deep-dive", "/api/batch/analyze", "/api/chat/message"}
# Write/modify endpoints (moderate cost). /api/batch/upload is used by the UI
# debounce parser while typing, so it intentionally stays in the default tier.
_MODERATE_PATHS = {"/api/feedback", "/api/cache/financials", "/api/dossier", "/api/chat"}

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
# Protects admin and privileged write endpoints behind CED_CONTROL_KEY.
# The user-facing feedback form/history is public by design because the static
# production UI cannot safely embed an admin secret; it is instead rate-limited.
# Set CED_CONTROL_KEY in .env. Without it, protected endpoints return 403.
_API_KEY = os.getenv("CED_CONTROL_KEY", "")

async def _require_auth(request: Request):
    """FastAPI dependency: require CED_CONTROL_KEY for protected endpoints.

    Local loopback requests and in-process FastAPI TestClient bypass auth so
    local tooling/tests keep working. Remote browser headers (Origin/Referer)
    are never trusted for auth because they are client-controlled/spoofable.
    Accepts X-API-Key header (primary) or api_key query param (fallback for downloads).
    """
    host = request.client.host if request.client else ""
    if host in ("127.0.0.1", "::1", "localhost", "testclient"):
        return
    if not _API_KEY:
        raise HTTPException(status_code=403, detail="API key not configured (set CED_CONTROL_KEY)")
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
from backend.chat import router as chat_router
app.include_router(chat_router)

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


def _invalid_existing_tickers(tickers: List[str]) -> List[str]:
    """Return ticker-shaped symbols that are not confirmed by market lookup.

    Format validation alone is not enough: common typo/name inputs such as APPL
    look like valid tickers and previously reached the expensive analysis path,
    producing partial dossiers with no client-ready PDFs. The upload parser
    already marks those as invalid; direct /api/analyze and /api/analyze/async
    must enforce the same gate server-side.
    """
    return [t for t in tickers if not _ticker_exists(t)]


def _raise_unknown_tickers(invalid_tickers: List[str]) -> None:
    if not invalid_tickers:
        return
    raise HTTPException(
        status_code=422,
        detail={
            "error": "Ticker not found",
            "invalid": invalid_tickers,
            "message": (
                "Ticker format is valid but the symbol was not found on Yahoo Finance. "
                "Please select a confirmed ticker (for Apple use AAPL, not APPL/Apple)."
            ),
        },
    )


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


@app.post("/api/batch/upload")
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


@app.post("/api/batch/analyze")
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
async def dossier_download(ticker: str, lang: str = "en", quarter: str | None = None):
    """Download an already-generated dossier as ZIP.

    This endpoint is intentionally read-only: it never triggers a ticker analysis,
    quarter regeneration, LLM generation, or on-disk PDF conversion. Generation is
    handled by explicit POST/async routes; download only serves verified artifacts.
    """
    ticker = ticker.strip().upper()
    dossier_language = _normalize_dossier_language(lang)

    # Pre-check: non-existent tickers that have no local analysis are noise,
    # not real pipeline failures. Return 404 without recording a proactive
    # Kanban intake task. This prevents random/bot ticker queries from
    # flooding the Kanban board with tasks for tickers that never existed.
    if not _find_analysis_dirs(ticker) and not _ticker_exists(ticker):
        logger.info(
            "[%s] Dossier download refused — ticker not found and no local analysis; skipped intake (noise gate) | lang=%s | quarter=%s",
            ticker,
            dossier_language,
            quarter or "latest",
        )
        raise HTTPException(
            status_code=404,
            detail=f"No pre-generated dossier ready for {ticker}",
        )

    if quarter and quarter != "latest":
        _record_pdf_client_failure(
            ticker,
            source="dossier_download",
            status="quarter_missing",
            message=f"No pre-generated dossier found for {ticker} quarter={quarter}",
            language=dossier_language,
            quarter=quarter,
        )
        raise HTTPException(
            status_code=404,
            detail=f"No pre-generated dossier found for {ticker} quarter={quarter}",
        )

    from backend.async_dossier import get_dossier_status

    status = get_dossier_status(ticker)
    logger.info(
        "[%s] Dossier download request | lang=%s | quarter=%s | ready=%s | download_enabled=%s | phase=%s | stage=%s | directory=%s | issues=%s",
        ticker,
        dossier_language,
        quarter or "latest",
        status.get("ready"),
        status.get("download_enabled"),
        status.get("phase"),
        status.get("stage"),
        status.get("directory"),
        len(status.get("verification_issues") or []),
    )
    if not status.get("ready"):
        logger.info(
            "[%s] Dossier download refused — no verified dossier ready | phase=%s | stage=%s | error=%s | issues=%s",
            ticker,
            status.get("phase"),
            status.get("stage"),
            status.get("error"),
            status.get("verification_issues"),
        )
        _record_pdf_client_failure(
            ticker,
            source="dossier_download",
            status="not_ready",
            message=f"No verified dossier ready for {ticker}",
            issues=status.get("verification_issues") or ([status.get("error")] if status.get("error") else []),
            language=dossier_language,
            quarter=quarter or "latest",
            directory=str(status.get("directory") or ""),
        )
        raise HTTPException(status_code=404, detail=f"No verified dossier ready for {ticker}")

    matches = _find_analysis_dirs(ticker)
    if not matches:
        _record_pdf_client_failure(
            ticker,
            source="dossier_download",
            status="analysis_missing",
            message=f"No analysis found for {ticker}",
            language=dossier_language,
            quarter=quarter or "latest",
        )
        raise HTTPException(status_code=404, detail=f"No analysis found for {ticker}")

    if not status.get("download_enabled", status.get("ready", False)):
        logger.warning(
            "[%s] Dossier download blocked by verification gate | deep_dive_validated=%s | issues=%s | directory=%s",
            ticker,
            status.get("deep_dive_validated"),
            status.get("verification_issues", []),
            status.get("directory"),
        )
        _record_pdf_client_failure(
            ticker,
            source="dossier_download",
            status="verification_blocked",
            message="Dossier generated but not verified; download is blocked.",
            issues=status.get("verification_issues", []),
            language=dossier_language,
            quarter=quarter or "latest",
            directory=str(status.get("directory") or ""),
        )
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Dossier generated but not verified; download is blocked.",
                "issues": status.get("verification_issues", []),
                "deep_dive_validated": status.get("deep_dive_validated"),
            },
        )

    status_dir = status.get("directory")
    source_dir = Path(status_dir) if status_dir else matches[0]
    if not source_dir.exists():
        source_dir = matches[0]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        included_dirs = set()
        for fpath in sorted(source_dir.rglob("*")):
            if not fpath.is_file():
                continue
            rel_parts = fpath.relative_to(source_dir).parts
            if rel_parts and rel_parts[0] in ("en", "jp") and rel_parts[0] != dossier_language:
                continue
            # Only PDF + XLSX + README.txt + transcript verbatim .txt in the deliverable ZIP.
            if fpath.suffix in (".json", ".csv", ".md"):
                continue
            if fpath.suffix == ".txt":
                if fpath.name == "README.txt":
                    pass
                elif "04_transcripts_and_management" in str(fpath) and "transcript_" in fpath.name:
                    pass
                else:
                    continue
            arcname = fpath.relative_to(source_dir)
            zf.write(fpath, arcname)
            included_dirs.add(str(arcname.parent))

        # Ensure all canonical folders are represented in the ZIP without mutating disk.
        folders = [
            "01_official_company_sources",
            "02_sec_or_regulatory_filings",
            "03_financial_data_sources",
            "04_transcripts_and_management",
            "05_market_and_context",
            "06_extracted_data",
            "07_final_report",
        ]
        for folder in folders:
            if folder not in included_dirs:
                zf.writestr(
                    f"{folder}/README.txt",
                    f"{folder}\n{'=' * len(folder)}\n\nDossier section — see full report for details.\n",
                )
        if (source_dir / dossier_language).is_dir():
            for folder in folders:
                lang_folder = f"{dossier_language}/{folder}"
                if lang_folder not in included_dirs:
                    zf.writestr(
                        f"{lang_folder}/README.txt",
                        f"{folder}\n{'=' * len(folder)}\n\nDossier section — see full report for details.\n",
                    )

    lang_suffix = f"_{dossier_language}" if dossier_language != "en" else ""
    buf.seek(0)
    zip_size = len(buf.getbuffer())
    logger.info(
        "[%s] Dossier download serving ZIP | source_dir=%s | lang=%s | size_bytes=%s",
        ticker,
        source_dir,
        dossier_language,
        zip_size,
    )
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


@app.post("/api/analyze")
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
    _raise_unknown_tickers(_invalid_existing_tickers(normalized_tickers))

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
    for ticker_err, error_msg in batch["errors"].items():
        log_search(ticker_err, "failed", duration_ms, error=error_msg, user_agent=ua, client_ip=client_ip)
    
    return JSONResponse({
        "status": "completed" if not batch["errors"] else "partial",
        "results": results_list,
        "errors": errors_list,
    })


@app.post("/api/analyze/async")
async def analyze_async(request: TickerRequest, lang: str = "en", force_refresh: bool = False, fastapi_request: Request = None):
    """Submit tickers for async analysis. Returns job ID immediately, poll /api/analyze/job/{id}.
    Use ?force_refresh=true to bypass cache."""
    tickers = request.tickers
    logger.info(f"Async analyze request: {tickers} [lang={lang}, force_refresh={force_refresh}]")

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
    _raise_unknown_tickers(_invalid_existing_tickers(normalized_tickers))

    from backend.job_store import create_job, update_job
    job_id = create_job(normalized_tickers, lang)

    # Run analysis in background thread
    do_deep_dive = request.deep_dive  # capture for closure

    def _run():
        def _progress(message: str):
            update_job(job_id, status="processing", progress=message)

        try:
            _progress("Starting analysis...")
            batch = run_analysis_parallel(
                normalized_tickers,
                output_base=str(ANALYSES_DIR),
                language=lang,
                force_refresh=force_refresh,
                progress_callback=_progress,
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

            # ── Deep-dive status (if requested) ──
            # run_analysis_parallel() already generates and validates the deep-dive dossier.
            # Do NOT call generate_deep_dive() again here: that duplicates expensive work,
            # can hang the async job in "processing", and leaves the browser stuck at 42%.
            deep_dive_pdfs = {}
            if do_deep_dive:
                for ticker_name in batch["results"]:
                    try:
                        matches = _find_analysis_dirs(ticker_name)
                        if not matches:
                            deep_dive_pdfs[ticker_name] = {"error": "analysis directory not found"}
                            continue
                        analysis_dir = matches[0]
                        if lang == "jp":
                            markdown_path = analysis_dir / "jp" / "07_final_report" / "earnings_deep_dive.md"
                            pdf_path = analysis_dir / "jp" / "07_final_report" / "earnings_deep_dive.pdf"
                        else:
                            markdown_path = analysis_dir / "07_final_report" / "earnings_deep_dive.md"
                            pdf_path = analysis_dir / "07_final_report" / "earnings_deep_dive.pdf"
                        if pdf_path.exists():
                            deep_dive_pdfs[ticker_name] = {
                                "markdown": str(markdown_path) if markdown_path.exists() else None,
                                "pdf": str(pdf_path),
                            }
                            logger.info(f"[{job_id}] Deep-dive PDF already available for {ticker_name}")
                        else:
                            deep_dive_pdfs[ticker_name] = {"error": f"missing PDF: {pdf_path}"}
                    except Exception as dd_err:
                        logger.warning(f"[{job_id}] Deep-dive status lookup failed for {ticker_name}: {dd_err}")
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
    with log_context(ticker=ticker):
        logger.info(
            "PDF endpoint request | lang=%s | quarter=%s | audience_mode=%s",
            lang,
            quarter,
            audience_mode,
        )

    # Pre-check: non-existent tickers that have no local analysis are noise,
    # not real pipeline failures. Return 404 without recording a proactive
    # Kanban intake task. (Mirrors dossier_download noise gate at line 1147.)
    if not _find_analysis_dirs(ticker) and not _ticker_exists(ticker):
        logger.info(
            "[%s] PDF endpoint refused — ticker not found and no local analysis; skipped intake (noise gate) | lang=%s | quarter=%s",
            ticker,
            lang,
            quarter,
        )
        raise HTTPException(
            status_code=404,
            detail=f"No analysis found for {ticker}",
        )

    matches = _find_analysis_dirs(ticker)
    if not matches:
        logger.warning("[%s] PDF endpoint: no analysis directory found", ticker)
        _record_pdf_client_failure(
            ticker,
            source="report_pdf",
            status="analysis_missing",
            message=f"No analysis found for {ticker}",
            language=lang,
            quarter=quarter,
        )
        raise HTTPException(status_code=404, detail=f"No analysis found for {ticker}")

    # If the newest dossier is currently generating or terminally blocked, do
    # not serve a stale older PDF. That hides exactly the failure the user needs
    # to see and prevents a failed download from becoming an actionable state.
    wants_jp = lang in ("jp", "ja")
    newest_dir = matches[0]
    newest_deep_dive = (
        newest_dir / "jp" / "07_final_report" / "earnings_deep_dive.pdf"
        if wants_jp
        else newest_dir / "07_final_report" / "earnings_deep_dive.pdf"
    )
    if not newest_deep_dive.exists():
        from backend.async_dossier import get_dossier_status, DossierPhase
        newest_phase = get_dossier_status(ticker).get("phase")
        if newest_phase in (DossierPhase.PDF_GENERATING, DossierPhase.PDF_VALIDATING):
            return JSONResponse(
                status_code=202,
                content={
                    "status": "generating",
                    "ticker": ticker,
                    "message": "Latest deep-dive PDF generation is in progress. Poll this endpoint until ready.",
                    "retry_after_seconds": 10,
                },
                headers={"Retry-After": "10"},
            )
        if newest_phase in (DossierPhase.PDF_BLOCKED, DossierPhase.FAILED):
            terminal_issues = [f"terminal phase: {newest_phase}"]
            terminal_validation_path = newest_deep_dive.parent / "deep_dive_validation.json"
            if terminal_validation_path.exists():
                try:
                    terminal_validation = json.loads(terminal_validation_path.read_text(encoding="utf-8"))
                    raw_issues = terminal_validation.get("issues") or terminal_validation.get("errors") or []
                    terminal_issues = raw_issues if isinstance(raw_issues, list) else [str(raw_issues)]
                except Exception:
                    logger.exception(
                        "[%s] PDF endpoint: failed to read terminal validation file | validation_path=%s",
                        ticker,
                        terminal_validation_path,
                    )
            logger.error(
                "[%s] PDF endpoint: latest dossier has terminal phase; refusing stale PDF | phase=%s | latest_dir=%s",
                ticker,
                newest_phase,
                newest_dir,
            )
            _record_pdf_client_failure(
                ticker,
                source="report_pdf",
                status="pdf_blocked",
                message=f"Latest PDF generation for {ticker} failed terminally (phase={newest_phase}). Refusing to serve stale PDF.",
                issues=terminal_issues,
                language=lang,
                quarter=quarter,
                directory=str(newest_dir),
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "status": "pdf_blocked",
                    "retryable": False,
                    "message": f"Latest PDF generation for {ticker} failed terminally (phase={newest_phase}). Refusing to serve stale PDF.",
                    "phase": newest_phase,
                    "directory": str(newest_dir),
                    "issues": terminal_issues,
                },
            )
        newest_markdown = newest_deep_dive.with_suffix(".md")
        newest_meta = newest_deep_dive.parent / "earnings_deep_dive_meta.json"
        if newest_markdown.exists() or newest_meta.exists():
            logger.error(
                "[%s] PDF endpoint: latest dossier has deep-dive artifacts but no PDF; refusing stale PDF | latest_dir=%s | markdown=%s | meta=%s",
                ticker,
                newest_dir,
                newest_markdown.exists(),
                newest_meta.exists(),
            )
            _record_pdf_client_failure(
                ticker,
                source="report_pdf",
                status="pdf_missing_latest",
                message=f"Latest analysis for {ticker} produced deep-dive artifacts but no PDF. Refusing to serve stale PDF.",
                issues=[f"markdown_exists={newest_markdown.exists()}", f"meta_exists={newest_meta.exists()}"],
                language=lang,
                quarter=quarter,
                directory=str(newest_dir),
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "status": "pdf_missing_latest",
                    "retryable": False,
                    "message": f"Latest analysis for {ticker} produced deep-dive artifacts but no PDF. Refusing to serve stale PDF.",
                    "directory": str(newest_dir),
                },
            )

    # Language-specific path. Prefer the newest dossier that already has the
    # requested PDF instead of blindly using matches[0]. A newer partial dossier
    # can exist after a restart/failed async generation and would otherwise make
    # this endpoint return an endless 202 even though a client-ready PDF exists
    # in the previous completed dossier.
    wants_jp = lang in ("jp", "ja")
    analysis_dir = matches[0]
    deep_dive = None
    report_pdf = None

    # Prefer a dossier with a real validated deep-dive PDF. Do NOT select a
    # newer partial dossier just because report.pdf exists: report.pdf is the
    # lightweight analysis report, not the client-facing earnings deep dive. That
    # regression made AVGO/Broadcom ignore the completed 2026-06-04 dossier and
    # repeatedly launch async generation on a newer failed/partial 2026-06-07
    # dossier, leaving the direct PDF endpoint stuck at 202/422.
    for candidate in matches:
        candidate_deep_dive = (
            candidate / "jp" / "07_final_report" / "earnings_deep_dive.pdf"
            if wants_jp
            else candidate / "07_final_report" / "earnings_deep_dive.pdf"
        )
        if candidate_deep_dive.exists():
            analysis_dir = candidate
            deep_dive = candidate_deep_dive
            report_pdf = candidate / "07_final_report" / "report.pdf"
            break

    if deep_dive is None:
        deep_dive = (
            analysis_dir / "jp" / "07_final_report" / "earnings_deep_dive.pdf"
            if wants_jp
            else analysis_dir / "07_final_report" / "earnings_deep_dive.pdf"
        )
        report_pdf = analysis_dir / "07_final_report" / "report.pdf"

    logger.info(
        "[%s] PDF endpoint resolved paths | analysis_dir=%s | deep_dive=%s | deep_dive_exists=%s | report_pdf=%s | report_exists=%s | matches=%s",
        ticker,
        analysis_dir,
        deep_dive,
        deep_dive.exists() if deep_dive else None,
        report_pdf,
        report_pdf.exists() if report_pdf else None,
        len(matches),
    )

    # Validator-blocked dossiers are terminal until the underlying content issue
    # is fixed. Do not keep retrying PDF generation: that creates an infinite
    # 202/poll loop and hides the real data-contract error from the UI.
    validation_path = deep_dive.parent / "deep_dive_validation.json"
    if not deep_dive.exists() and validation_path.exists():
        try:
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception(
                "[%s] PDF endpoint: failed to read validation file | validation_path=%s",
                ticker,
                validation_path,
            )
            validation = {}
        if validation.get("passed") is False:
            issues = validation.get("issues") or validation.get("errors") or []
            if not isinstance(issues, list):
                issues = [str(issues)]
            from backend.async_dossier import set_dossier_phase, DossierPhase
            logger.error(
                "[%s] PDF endpoint blocked by validation file | validation_path=%s | issue_count=%s | first_issue=%s",
                ticker,
                validation_path,
                len(issues),
                issues[0] if issues else "-",
            )
            set_dossier_phase(
                ticker,
                DossierPhase.PDF_BLOCKED,
                error="Deep-dive validation failed",
                validation_path=str(validation_path),
                pdf_path=str(deep_dive),
                directory=str(analysis_dir),
            )
            _record_pdf_client_failure(
                ticker,
                source="report_pdf",
                status="pdf_blocked",
                message=f"PDF build blocked — data contract violation for {ticker}",
                issues=issues,
                language=lang,
                quarter=quarter,
                directory=str(analysis_dir),
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "status": "pdf_blocked",
                    "retryable": False,
                    "message": f"PDF build blocked — data contract violation for {ticker}",
                    "issues": issues,
                },
            )

    # Prefer deep-dive PDF; if it doesn't exist, launch async generation
    # and return 202 Accepted so the client can poll (no 2-min timeout)
    if not deep_dive.exists():
        # ── Idempotency guard: don't re-spawn if a generator is already
        # in flight, and refuse to respawn after a terminal failure.
        # Fixes t_fda2f272 root cause (sa-pipeline 2026-06-01):
        #   /api/dossier/{ticker}/status uses validated-dir selection, while
        #   this endpoint used to use newest-dir. Newest often lacks JP PDF,
        #   so each poll spawned a new background thread (+3 uvicorn threads
        #   per 3 polls). Now we check the dossier phase and short-circuit
        #   when already generating, or return 422 on terminal failure.
        from backend.async_dossier import get_dossier_status, DossierPhase
        current_phase = get_dossier_status(ticker).get("phase")
        logger.info(
            "[%s] PDF generation decision | current_phase=%s | deep_dive=%s | validation_path=%s | analysis_dir=%s",
            ticker,
            current_phase,
            deep_dive,
            validation_path,
            analysis_dir,
        )
        if current_phase in (DossierPhase.PDF_GENERATING, DossierPhase.PDF_VALIDATING):
            return JSONResponse(
                status_code=202,
                content={
                    "status": "generating",
                    "ticker": ticker,
                    "message": "Deep-dive PDF generation already in progress. Poll this endpoint until ready.",
                    "retry_after_seconds": 10,
                },
                headers={"Retry-After": "10"},
            )
        if current_phase in (DossierPhase.PDF_BLOCKED, DossierPhase.FAILED):
            logger.error(
                "[%s] PDF generation refused after terminal phase | phase=%s | deep_dive=%s | validation_path=%s",
                ticker,
                current_phase,
                deep_dive,
                validation_path,
            )
            _record_pdf_client_failure(
                ticker,
                source="report_pdf",
                status="pdf_blocked",
                message=f"PDF generation for {ticker} previously failed terminally (phase={current_phase}). Refusing to respawn.",
                issues=[f"terminal phase: {current_phase}"],
                language=lang,
                quarter=quarter,
                directory=str(analysis_dir),
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "status": "pdf_blocked",
                    "retryable": False,
                    "message": f"PDF generation for {ticker} previously failed terminally (phase={current_phase}). Refusing to respawn.",
                    "phase": current_phase,
                },
            )

        import asyncio

        async def _generate_deep_dive_async(ticker: str, lang: str, dd_path: Path):
            """Background deep-dive generation — runs in thread to not block."""
            from backend.async_dossier import set_dossier_phase, DossierPhase
            from backend.earnings_deep_dive.errors import ValidationError
            set_dossier_phase(
                ticker,
                DossierPhase.PDF_GENERATING,
                directory=str(dd_path.parent.parent),
                pdf_path=str(dd_path),
            )
            logger.info(
                "[%s/%s] Background deep-dive PDF generation started | output_pdf=%s | quarter=%s | audience_mode=%s",
                ticker,
                lang,
                dd_path,
                quarter,
                audience_mode,
            )
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
                    logger.error(
                        "[%s/%s] PDF generation failed before validation | reason=yahoo_data_unavailable | output_pdf=%s",
                        ticker,
                        lang,
                        dd_path,
                    )
                    set_dossier_phase(
                        ticker,
                        DossierPhase.FAILED,
                        error="Yahoo data unavailable for PDF generation",
                        pdf_path=str(dd_path),
                        directory=str(dd_path.parent.parent),
                    )
                    _record_pdf_client_failure(
                        ticker,
                        source="pdf_generation",
                        status="data_unavailable",
                        message="Yahoo data unavailable for PDF generation",
                        language=lang,
                        quarter=quarter,
                        directory=str(dd_path.parent.parent),
                    )
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
                    from backend.company_overview import get_company_overview
                    company_overview = await get_company_overview(ticker, language=lang)
                    logger.info(f"[{ticker}/{lang}] Company overview generated for deep-dive PDF")
                except Exception as e:
                    logger.warning(
                        "[%s/%s] Company overview skipped during PDF generation: %s",
                        ticker,
                        lang,
                        e,
                        exc_info=True,
                    )
                
                # Find analysis directory for output_dir (required by schema)
                # dd_path is .../07_final_report/earnings_deep_dive.pdf, parent.parent = analysis_dir
                output_dir = str(dd_path.parent.parent)
                dd_req = DeepDiveRequest(ticker=ticker, quarter=quarter, language=lang,
                                         output_dir=output_dir, metrics=metrics,
                                         audience_mode=audience_mode)
                dd_response = generate_deep_dive(dd_req)
                
                # ── Pre-render validation (BLOCKING — hard data contract gate) ──
                validation_log_path = dd_path.parent / "deep_dive_validation.json"
                set_dossier_phase(
                    ticker,
                    DossierPhase.PDF_VALIDATING,
                    validation_path=str(validation_log_path),
                    pdf_path=str(dd_path),
                    directory=str(dd_path.parent.parent),
                )
                from backend.earnings_deep_dive.pre_render_validator import (
                    validate_pre_render,
                    annotate_sections_with_warnings,
                    format_validation_error,
                )
                sections = getattr(dd_response, 'sections', None)
                pre_val = validate_pre_render(
                    ticker=ticker,
                    quarter=dd_req.quarter,
                    metrics=metrics,
                    section_analysis=sections,
                )
                if pre_val.errors:
                    error_msg = format_validation_error(pre_val, ticker)
                    logger.error(
                        "[%s/%s] Pre-render validation BLOCKED PDF | errors=%s | warnings=%s | validation_path=%s | first_error=%s",
                        ticker,
                        lang,
                        pre_val.error_count,
                        pre_val.warning_count,
                        validation_log_path,
                        pre_val.errors[0].detail if pre_val.errors else "-",
                    )
                    logger.error(error_msg)
                    raise ValidationError(
                        ticker=ticker,
                        errors=pre_val.errors,
                        message=error_msg,
                    )
                elif pre_val.warnings:
                    logger.warning(
                        "[%s/%s] Pre-render validation warnings | warnings=%s | errors=0 | validation_path=%s | first_warning=%s",
                        ticker,
                        lang,
                        pre_val.warning_count,
                        validation_log_path,
                        pre_val.warnings[0].detail if pre_val.warnings else "-",
                    )
                    sections = annotate_sections_with_warnings(
                        sections or {}, pre_val,
                    )
                else:
                    logger.info(
                        "[%s/%s] Pre-render validation passed cleanly | validation_path=%s",
                        ticker,
                        lang,
                        validation_log_path,
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
                set_dossier_phase(
                    ticker,
                    DossierPhase.COMPLETE,
                    pdf_path=str(dd_path),
                    directory=str(dd_path.parent.parent),
                )
                logger.info(
                    "[%s/%s] Background deep-dive PDF generation complete | output_pdf=%s | size_bytes=%s",
                    ticker,
                    lang,
                    dd_path,
                    dd_path.stat().st_size if dd_path.exists() else None,
                )
            except ValidationError as ve:
                set_dossier_phase(
                    ticker,
                    DossierPhase.PDF_BLOCKED,
                    error=str(ve),
                    pdf_path=str(dd_path),
                    directory=str(dd_path.parent.parent),
                    validation_path=str(dd_path.parent / "deep_dive_validation.json"),
                )
                _record_pdf_client_failure(
                    ticker,
                    source="pdf_generation",
                    status="pdf_blocked",
                    message="PDF build blocked by pre-render validator",
                    issues=[getattr(error, "detail", str(error)) for error in (ve.errors or [])],
                    language=lang,
                    quarter=quarter,
                    directory=str(dd_path.parent.parent),
                )
                logger.error(
                    "[%s/%s] PDF build blocked by pre-render validator | errors=%s | output_pdf=%s | validation_path=%s | error=%s",
                    ticker,
                    lang,
                    len(ve.errors or []),
                    dd_path,
                    dd_path.parent / "deep_dive_validation.json",
                    ve,
                    exc_info=True,
                )
                return
            except Exception as e:
                set_dossier_phase(
                    ticker,
                    DossierPhase.FAILED,
                    error=str(e),
                    pdf_path=str(dd_path),
                    directory=str(dd_path.parent.parent),
                )
                _record_pdf_client_failure(
                    ticker,
                    source="pdf_generation",
                    status="generation_failed",
                    message=str(e),
                    language=lang,
                    quarter=quarter,
                    directory=str(dd_path.parent.parent),
                )
                logger.exception(
                    "[%s/%s] Background deep-dive PDF generation FAILED | output_pdf=%s | error=%s",
                    ticker,
                    lang,
                    dd_path,
                    e,
                )
                import traceback
                print(traceback.format_exc(), file=sys.stderr)
        
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
    
    if deep_dive is None:
        raise HTTPException(status_code=404, detail=f"No deep-dive PDF path resolved for {ticker}")
    pdf_path = deep_dive if deep_dive.exists() else report_pdf
    if pdf_path is None or not pdf_path.exists():
        logger.error(
            "[%s] PDF endpoint could not find final PDF | deep_dive=%s | report_pdf=%s | analysis_dir=%s",
            ticker,
            deep_dive,
            report_pdf,
            analysis_dir,
        )
        _record_pdf_client_failure(
            ticker,
            source="report_pdf",
            status="pdf_not_found",
            message=f"No PDF found for {ticker}",
            issues=[f"deep_dive={deep_dive}", f"report_pdf={report_pdf}"],
            language=lang,
            quarter=quarter,
            directory=str(analysis_dir),
        )
        raise HTTPException(status_code=404, detail=f"No PDF found for {ticker}")

    # Generate ticker-aware filename for browser save dialog: MSFT_deep_dive.pdf
    pdf_filename = f"{ticker}_deep_dive.pdf"
    logger.info(
        "[%s] PDF endpoint serving file | pdf_path=%s | filename=%s | size_bytes=%s",
        ticker,
        pdf_path,
        pdf_filename,
        pdf_path.stat().st_size,
    )
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


def _recent_searches_payload(limit: int = 50, offset: int = 0, status: str = "all") -> dict:
    """Build the read-only recent search payload used by admin and public UI routes."""
    from backend.search_db import read_recent_sqlite, _ensure_db, DB_PATH
    import sqlite3

    results = read_recent_sqlite(limit=max(1, min(limit, 200)), offset=max(0, offset), status_filter=status)
    # Get total count for pagination
    _ensure_db()
    conn = sqlite3.connect(str(DB_PATH))
    total = conn.execute("SELECT COUNT(*) as n FROM searches").fetchone()[0]
    conn.close()
    return {"total": total, "searches": results}


def _search_stats_payload() -> dict:
    """Build read-only aggregate search statistics for dashboard display."""
    from backend.search_db import get_stats

    return get_stats()


@app.get("/api/recent-searches")
async def public_recent_searches(limit: int = 50, offset: int = 0, status: str = "all"):
    """Public read-only recent search events for the static production dashboard.

    The static frontend cannot carry an admin API key. This route exposes only
    already-visible operational search metadata; privileged admin routes remain
    protected under `/api/admin/*`.
    """
    return JSONResponse(_recent_searches_payload(limit=limit, offset=offset, status=status))


@app.get("/api/admin/recent-searches", dependencies=[Depends(_require_auth)])
async def recent_searches(limit: int = 50, offset: int = 0, status: str = "all"):
    """Get recent search events for near-real-time monitoring.
    
    Query params:
    - limit: max number of events (default 50, max 200)
    - offset: pagination offset (default 0)
    - status: "all", "completed", or "failed" (default "all")
    
    Returns {total: int, searches: [{timestamp, ticker, status, duration_ms, cache_hit, user_agent}]}
    """
    return JSONResponse(_recent_searches_payload(limit=limit, offset=offset, status=status))


@app.get("/api/search-stats")
async def public_search_stats():
    """Public read-only aggregate search statistics for the static dashboard."""
    return JSONResponse(_search_stats_payload())


@app.get("/api/admin/search-stats", dependencies=[Depends(_require_auth)])
async def search_stats():
    """Get aggregate search statistics for the admin dashboard.
    
    Returns {total, success_rate, avg_duration_ms, top_tickers, recent_errors, last_24h}
    """
    return JSONResponse(_search_stats_payload())


# ── Seeking Alpha Admin Probe ─────────────────────────────────────────
@app.get("/api/admin/seeking-alpha/probe", dependencies=[Depends(_require_auth)])
async def seeking_alpha_probe(ticker: str = "NVDA"):
    """Test Seeking Alpha connectivity with stored cookies.
    
    Returns probe result: {ok, authenticated, reachable, ticker, url, reason, cookie_count, ...}
    Protected under /api/admin/* — requires CED_CONTROL_KEY.
    """
    from backend.seeking_alpha_access import probe_access_async as _probe
    result = await _probe(ticker=ticker)
    return JSONResponse(_sanitize_json(result))


@app.get("/api/admin/seeking-alpha/status", dependencies=[Depends(_require_auth)])
async def seeking_alpha_status():
    """Get Seeking Alpha cookie storage status (no network probe).
    
    Returns: {configured, cookie_count, cookie_diagnostics, updated_at, ...}
    """
    from backend.seeking_alpha_access import get_access_status as _status
    return JSONResponse(_sanitize_json(_status()))


# ── Nami Feedback System ──────────────────────────────────────────────
@app.post("/api/feedback")
async def submit_feedback(
    ticker: str = Form(""),
    category: str = Form("general"),
    text: str = Form(""),
    files: list[UploadFile] = FastAPIFile(default=[]),
):
    """Submit feedback from the user-facing feedback page.

    This endpoint is intentionally public: the static production UI cannot carry
    CED_CONTROL_KEY, and the page must let Nami/Ced submit feedback without an
    admin secret. Abuse is limited by the `/api/feedback` moderate rate limit;
    admin review stays protected through `/api/admin/feedback`.
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

    # Detect .har files before save_feedback consumes them
    har_files: list[tuple[str, str]] = []  # (original_name, safe_basename)
    for upload in (files or []):
        if not upload.filename:
            continue
        if upload.filename.lower().endswith(".har"):
            # Reconstruct the safe basename (same logic as _sanitize_upload_filename)
            safe_basename = re.sub(
                r"[^A-Za-z0-9._-]+", "_",
                Path(upload.filename).stem,
            ).strip("._-") or "attachment"
            safe_basename = f"{safe_basename}.har"
            har_files.append((upload.filename, safe_basename))

    try:
        result = await save_feedback(normalized_ticker or None, text, files, category=normalized_category)
    except ValueError as e:
        scope = normalized_ticker or "GENERAL"
        logger.warning(f"Feedback validation failed for {scope}: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        scope = normalized_ticker or "GENERAL"
        logger.error(f"Feedback save failed for {scope}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e

    # ── HAR auto-processing: extract Seeking Alpha cookies ────────────
    cookie_status = None
    if har_files:
        from backend.seeking_alpha_access import import_har_cookies
        from backend.feedback_store import get_feedback_file_path

        for _orig_name, safe_basename in har_files:
            saved_name = f"{result['id']}_{safe_basename}"
            try:
                har_path = get_feedback_file_path(result["bucket"], saved_name)
                cookie_status = import_har_cookies(har_path)
                logger.info(
                    "HAR imported from feedback %s: %d SA cookies, quality=%s",
                    result["id"],
                    cookie_status.get("cookie_count", 0),
                    cookie_status.get("cookie_diagnostics", {}).get("quality", "?"),
                )
            except ValueError as e:
                logger.warning("HAR import failed for %s (%s): %s", saved_name, _orig_name, e)
                cookie_status = {"error": str(e), "file": _orig_name}
            except Exception as e:
                logger.error("HAR import unexpected error for %s: %s", saved_name, e)
                cookie_status = {"error": f"unexpected: {e}", "file": _orig_name}

    response_data: dict[str, Any] = {"status": "ok", **result}
    if cookie_status:
        response_data["cookie_import"] = cookie_status
    return JSONResponse(response_data)


@app.get("/api/feedback")
async def list_all_feedback():
    """List feedback entries for the user-facing feedback page.

    Public by design so the production static UI can show submission status
    without embedding an admin API key. The privileged admin view remains on
    `/api/admin/feedback` and stays protected by `_require_auth`.
    """
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
    return FileResponse(
        file_path,
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )



def _company_overview_pdf_quality_failure(file_path: Path) -> str | None:
    """Return a client-readiness failure reason for a company overview PDF."""
    if not file_path.exists():
        return "missing"
    try:
        size = file_path.stat().st_size
    except OSError as exc:
        return f"stat_failed: {exc}"
    if size < 8_000:
        return f"too_small:{size}"
    try:
        with file_path.open("rb") as handle:
            if handle.read(4) != b"%PDF":
                return "not_pdf"
    except OSError as exc:
        return f"read_failed: {exc}"
    try:
        import importlib
        fitz = importlib.import_module("fitz")  # PyMuPDF
        with fitz.open(str(file_path)) as doc:
            pages = doc.page_count
        if pages < 3 or pages > 12:
            return f"page_count:{pages}"
    except Exception as exc:
        logger.warning(f"Company overview PDF quality probe skipped for {file_path}: {exc}")
    return None

@app.get("/api/company-overview/{ticker}/download")
async def download_company_overview(ticker: str, format: str = "auto"):
    """Download the best available client-ready company overview artifact."""
    ticker = ticker.strip().upper()
    selected_format = (format or "auto").strip().lower()
    if selected_format not in {"auto", "pdf", "md", "json"}:
        raise HTTPException(status_code=400, detail="Invalid format. Use auto, pdf, md, or json")

    analysis_dirs = _find_analysis_dirs(ticker)
    if not analysis_dirs:
        raise HTTPException(status_code=404, detail=f"No analysis found for {ticker}")

    order = ["pdf", "md", "json"] if selected_format == "auto" else [selected_format]
    rejected_pdfs: list[dict[str, str]] = []

    for analysis_dir in analysis_dirs:
        source_dir = analysis_dir / "01_official_company_sources"
        # Only the investor_profile naming is considered client-ready. Legacy
        # company_profile_{ticker}.pdf files are thin fallback artifacts and
        # must not be served as Company Overview PDFs to clients.
        pdf_candidates = sorted(
            source_dir.glob(f"{ticker}_company_overview_investor_profile_*.pdf"),
            reverse=True,
        )

        ready_pdf = None
        for pdf_candidate in pdf_candidates:
            failure = _company_overview_pdf_quality_failure(pdf_candidate)
            if failure is None:
                ready_pdf = pdf_candidate
                break
            rejected_pdfs.append({"path": str(pdf_candidate), "reason": failure})

        candidates = {
            "pdf": ready_pdf,
            "md": source_dir / f"company_profile_{ticker}.md",
            "json": source_dir / f"company_overview_{ticker}.json",
        }

        for kind in order:
            file_path = candidates[kind]
            if file_path and file_path.exists():
                media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
                # PDF → inline (open in new tab); MD/JSON → attachment (download)
                disposition = "inline" if media_type == "application/pdf" else "attachment"
                return FileResponse(
                    file_path,
                    media_type=media_type,
                    filename=file_path.name,
                    content_disposition_type=disposition,
                )

    if selected_format == "pdf" and rejected_pdfs:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "company_overview_pdf_blocked",
                "retryable": True,
                "message": f"No client-ready Company Overview PDF found for {ticker}",
                "rejected_pdfs": rejected_pdfs[:5],
            },
        )

    raise HTTPException(status_code=404, detail=f"No company overview artifact found for {ticker}")


@app.get("/api/admin/seeking-alpha/access")
async def get_seeking_alpha_access_status():
    """Return Seeking Alpha cookie status without exposing the cookie value.

    Public by design for the feedback page: Nami can confirm whether cookies are
    configured, while the endpoint never returns the stored Cookie header.
    """
    from backend.seeking_alpha_access import get_access_status

    return JSONResponse(get_access_status())


@app.post("/api/admin/seeking-alpha/access")
async def save_seeking_alpha_access(payload: SeekingAlphaAccessUpdateRequest):
    """Store Seeking Alpha cookies submitted from the feedback page.

    The Cookie header is write-only for the UI: it is saved server-side and never
    returned by status endpoints. Clearing stored cookies remains admin-protected.
    """
    from backend.seeking_alpha_access import save_access

    try:
        return JSONResponse(save_access(payload.cookie_header, payload.user_agent))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/admin/seeking-alpha/access", dependencies=[Depends(_require_auth)])
async def clear_seeking_alpha_access():
    from backend.seeking_alpha_access import clear_access

    return JSONResponse(clear_access())


@app.post("/api/admin/seeking-alpha/access/har")
async def upload_seeking_alpha_har(file: UploadFile = FastAPIFile(...)):
    """Upload a browser HAR export (.har) to import Seeking Alpha cookies.

    Accepts a Chrome/Edge/Firefox HAR JSON file, extracts cookies from all
    requests to ``*.seekingalpha.com``, and persists them server-side in
    Netscape-compatible format so Playwright can use them with per-cookie
    domain/path for PerimeterX bypass.

    Public by design for the feedback page (no auth required) — the endpoint
    never returns the stored cookies.
    Max file size: 100 MB.
    """
    from backend.seeking_alpha_access import import_har_cookies
    from backend.seeking_alpha_access import STATE_DIR, _now_iso

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".har", ".json"}:
        raise HTTPException(status_code=400, detail="Only .har files are accepted for cookie import")

    # Write uploaded file to a temporary location
    tmp_dir = STATE_DIR / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"sa_har_upload_{_now_iso().replace(':', '-')}_{file.filename}"
    try:
        contents = await file.read()
        if len(contents) > 100 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="HAR file too large (max 100 MB)")
        tmp_path.write_bytes(contents)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to write HAR upload: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to process upload") from exc

    try:
        result = import_har_cookies(tmp_path)
        return JSONResponse(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("HAR import failed: %s", exc)
        raise HTTPException(status_code=500, detail="HAR cookie extraction failed") from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


@app.post("/api/admin/seeking-alpha/test")
async def test_seeking_alpha_access(payload: SeekingAlphaProbeRequest | None = None):
    """Probe stored Seeking Alpha cookies without exposing the cookie value.

    Public by design for the feedback page: after Nami submits cookies, the UI
    must be able to confirm pending → verified/failed without embedding an
    admin API key. The endpoint only accepts a ticker and returns probe status;
    it never returns the stored Cookie header.
    """
    from backend.seeking_alpha_access import probe_access_async

    ticker = payload.ticker if payload else "NVDA"
    return JSONResponse(await probe_access_async(ticker))


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


@app.post("/api/cache/overview/{ticker}/flush", dependencies=[Depends(_require_auth)])
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

@app.get("/feedback", include_in_schema=False)
async def redirect_feedback_hash_route():
    return RedirectResponse(url="/#feedback")


@app.get("/admin", include_in_schema=False)
async def redirect_admin_hash_route():
    return RedirectResponse(url="/#admin")


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


@app.on_event("startup")
async def _startup_chat_pdf_ingestion():
    """Ingest existing analysis PDFs into the chat retrieval system on startup."""
    try:
        from backend.chat_store import initialize as _init_chat
        _init_chat()
        from backend.chat_retrieval import ingest_analyses_pdfs
        count = ingest_analyses_pdfs()
        if count > 0:
            logger.info("Chat: ingested %d PDFs for retrieval", count)
        else:
            logger.info("Chat: no PDFs to ingest (analyses/ may be empty)")
    except Exception as e:
        logger.warning("Chat PDF ingestion failed (non-fatal): %s", e)
