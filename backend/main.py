"""FastAPI application for Stock Analysis Pipeline."""
import os
import uuid
import logging
from pathlib import Path
from typing import List

import io
import json
import zipfile
import re
import hashlib
import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, UploadFile, File as FastAPIFile, Header, Form, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
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

from backend.models import TickerRequest, AnalysisResult
from backend.orchestrator import run_analysis_sequential
from backend.earnings_deep_dive import DeepDiveRequest, DeepDiveResponse, generate_deep_dive
from backend.sources_collector import list_available_quarters, get_yahoo_data_for_quarter

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

app = FastAPI(title="Stock Analysis Pipeline", version="1.0.0")

# ── Rate limiting middleware (P0 audit 2026-05-05) ──
# In-memory token bucket with auto-cleanup: 30 req/min analyze, 120 req/min others
_rate_limits = {}  # IP → (window_start, count)
_RATE_WINDOW = 60  # seconds
_RATE_LIMIT_ANALYZE = 30  # expensive endpoint — 30/min
_RATE_LIMIT_DEFAULT = 120  # cheap endpoints — 120/min
_RATE_MAX_ENTRIES = 5000  # Prune oldest entries when exceeded

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    from time import time as _time
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path
    # Skip rate limiting for health and debug endpoints
    if path in ("/api/health",) or path.startswith("/api/debug/"):
        return await call_next(request)
    limit = _RATE_LIMIT_ANALYZE if path == "/api/analyze" else _RATE_LIMIT_DEFAULT
    now = _time()
    
    # Periodic cleanup: if dict grows too large, evict expired entries
    if len(_rate_limits) > _RATE_MAX_ENTRIES:
        expired = [ip for ip, (ts, _) in _rate_limits.items() if now - ts >= _RATE_WINDOW]
        for ip in expired:
            del _rate_limits[ip]
    
    entry = _rate_limits.get(client_ip)
    if entry and now - entry[0] < _RATE_WINDOW:
        if entry[1] >= limit:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded ({limit} req/{_RATE_WINDOW}s). Retry shortly."},
            )
        entry[1] += 1
    else:
        _rate_limits[client_ip] = [now, 1]
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ANALYSES_DIR = Path(__file__).parent.parent / "analyses"

# In-memory batch job store (survives between requests, lost on server restart)
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
    except Exception:
        pass  # Best-effort

def _load_batch_job(job_id: str) -> dict | None:
    """Try to load a batch job from disk (survives restart)."""
    try:
        job_path = BATCH_DIR / f"{job_id}.json"
        if job_path.exists():
            with open(job_path) as f:
                return json.load(f)
    except Exception:
        pass
    return None

TICKER_RE = re.compile(r'^[A-Z]{1,5}(?:\.[A-Z]{1,2})?$')  # AAPL, MC.PA, BRK.B
ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{10}$')  # US0378331005

# Lazy import yfinance for ticker validation
_yf_available = None


def _ticker_dir_key(ticker: str) -> str:
    """Return the ticker key used in analysis directory names."""
    return ticker.strip().upper().replace(".", "_")


def _find_analysis_dirs(ticker: str) -> list[Path]:
    """Find analysis directories for a ticker, case-insensitively."""
    return sorted(ANALYSES_DIR.glob(f"*_{_ticker_dir_key(ticker)}_*"), reverse=True)


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
        except Exception:
            pass

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
    except Exception:
        pass
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
    except Exception:
        pass
    return None

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
            for ticker in j["tickers"]:
                try:
                    logger.info(f"[{j['job_id']}] Analyzing {ticker}...")
                    result = run_analysis_sequential([ticker], output_base=str(ANALYSES_DIR))
                    if ticker in result["results"]:
                        j["results"][ticker] = result["results"][ticker]
                    elif ticker in result.get("errors", {}):
                        j["errors"][ticker] = result["errors"][ticker]
                    else:
                        j["errors"][ticker] = "Unknown error"
                    j["completed"] += 1
                except Exception as e:
                    logger.error(f"[{j['job_id']}] {ticker}: {e}")
                    j["errors"][ticker] = str(e)
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


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "stock-analysis-pipeline", "commit": "83f33d0"}


@app.get("/api/debug/yf-cache/{ticker}")
async def debug_yf_cache(ticker: str):
    """Debug: show yfinance cache status for a ticker.
    Only available in development mode. Set ENVIRONMENT=development to enable."""
    if os.getenv("ENVIRONMENT", "production") != "development":
        raise HTTPException(status_code=403, detail="Debug endpoints disabled in production")
    from backend.sources_collector import _cache_get_yf, _cache_get, _cache_path_yf, _cache_path
    import glob
    
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


@app.get("/api/debug/sources")
async def debug_sources():
    """Return which API sources are configured (masked keys).
    Only available in development mode. Set ENVIRONMENT=development to enable."""
    if os.getenv("ENVIRONMENT", "production") != "development":
        raise HTTPException(status_code=403, detail="Debug endpoints disabled in production")

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


@app.post("/api/earnings/deep-dive", response_model=DeepDiveResponse)
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
                price=q_data.get("price"),
                currency=q_data.get("currency", "USD"),
                sector=q_data.get("sector"),
            )
            request.metrics = _deep_dive_metrics(dummy, q_data)
    try:
        return generate_deep_dive(request)
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
async def dossier_download(ticker: str, lang: str = "en"):
    """Download the complete dossier as ZIP. Generates files synchronously if not ready.
    Converts MD/TXT → PDF on-the-fly. ZIP contains ONLY PDF + XLSX + README.txt.
    Use ?lang=ja for Japanese translated dossier."""
    ticker = ticker.strip().upper()
    from backend.async_dossier import get_dossier_status
    status = get_dossier_status(ticker)
    
    # If dossier not ready, generate it synchronously
    if not status.get("ready"):
        logger.info(f"[{ticker}] Dossier not ready — generating synchronously... [lang={lang}]")
        try:
            from backend.pipeline import analyze_ticker
            result = analyze_ticker(ticker, output_base=str(ANALYSES_DIR))
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
    
    # Translate dossier content if non-English language requested
    # NEVER mutate originals — work on a temp copy (Codex P0 audit 2026-05-05)
    import tempfile, shutil
    work_dir = None
    if lang != "en":
        logger.info(f"[{ticker}] Translating dossier to {lang} (temp copy)...")
        try:
            from backend.translator import translate_text
            work_dir = Path(tempfile.mkdtemp(prefix=f"dossier_{ticker}_"))
            # Copy original dir to temp
            shutil.copytree(analysis_dir, work_dir, dirs_exist_ok=True)
            for fpath in sorted(work_dir.rglob("*.txt")):
                try:
                    translated = translate_text(fpath.read_text(encoding="utf-8"), lang)
                    fpath.write_text(translated, encoding="utf-8")
                except Exception:
                    pass
            for fpath in sorted(work_dir.rglob("*.md")):
                if fpath.name != "README.md":
                    try:
                        translated = translate_text(fpath.read_text(encoding="utf-8"), lang)
                        fpath.write_text(translated, encoding="utf-8")
                    except Exception:
                        pass
            logger.info(f"[{ticker}] Dossier translation complete (temp copy)")
        except Exception as e:
            logger.warning(f"[{ticker}] Translation error (continuing with original): {e}")
            work_dir = None  # fall back to original
    
    # Use the translated temp dir if available, otherwise original
    source_dir = work_dir if work_dir else analysis_dir
    
    # Pre-convert MD/TXT files to PDF on-the-fly 
    try:
        from backend.pdf_generator import md_to_pdf
        for fpath in sorted(source_dir.rglob("*.md")):
            if fpath.name == "README.md":
                continue
            pdf_path = fpath.with_suffix(".pdf")
            if not pdf_path.exists():
                try:
                    md_to_pdf(str(fpath), str(pdf_path), title=f"{ticker} — {fpath.stem.replace('_', ' ').title()}")
                    logger.info(f"[{ticker}] Converted {fpath.name} → PDF")
                except Exception as e:
                    logger.warning(f"[{ticker}] MD→PDF failed for {fpath.name}: {e}")
        for fpath in sorted(source_dir.rglob("*.txt")):
            if fpath.name == "README.txt":
                continue
            pdf_path = fpath.with_suffix(".pdf")
            if not pdf_path.exists():
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
                # Only PDF + XLSX + README.txt in the deliverable ZIP
                if fpath.suffix in ('.json', '.csv', '.md'):
                    continue
                if fpath.suffix == '.txt' and fpath.name != 'README.txt':
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
        for language in ("en", "jp"):
            if (source_dir / language).is_dir():
                for folder in ["01_official_company_sources", "02_sec_or_regulatory_filings",
                               "03_financial_data_sources", "04_transcripts_and_management",
                               "05_market_and_context", "06_extracted_data", "07_final_report"]:
                    lang_folder = f"{language}/{folder}"
                    if lang_folder not in included_dirs:
                        zf.writestr(f"{lang_folder}/README.txt",
                                   f"{folder}\n{'='*len(folder)}\n\nDossier section — see full report for details.\n")
    
    lang_suffix = f"_{lang}" if lang != "en" else ""
    buf.seek(0)
    
    # Clean up temp dir if translation created one
    if work_dir:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
            logger.debug(f"[{ticker}] Temp translation dir cleaned up")
        except Exception:
            pass
    
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={ticker}_dossier{lang_suffix}.zip"},
    )


@app.post("/api/dossier/{ticker}/upload")
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
async def analyze(request: TickerRequest, lang: str = "en"):
    """Submit tickers for analysis. Runs sequentially, returns results immediately.
    Use ?lang=ja for Japanese labels."""
    tickers = request.tickers
    logger.info(f"Analyze request: {tickers} [lang={lang}]")
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
        batch = await _asyncio.to_thread(run_analysis_sequential, normalized_tickers, output_base=str(ANALYSES_DIR))
    except Exception as e:
        logger.exception("Batch analysis failed")
        raise HTTPException(status_code=500, detail=str(e))

    from backend.i18n import translate

    results_list = []
    errors_list = list(batch["errors"].values())

    for ticker, result in batch["results"].items():
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
    return JSONResponse({
        "status": "completed" if not batch["errors"] else "partial",
        "results": results_list,
        "errors": errors_list,
    })


@app.get("/api/report/{ticker}/pdf")
async def get_report_pdf(ticker: str):
    """Generate and retrieve PDF report for a ticker."""
    ticker = ticker.strip().upper()
    matches = _find_analysis_dirs(ticker)
    if not matches:
        raise HTTPException(status_code=404, detail=f"No analysis found for {ticker}")

    # Check if PDF already exists
    pdf_path = matches[0] / "07_final_report" / "report.pdf"
    if not pdf_path.exists():
        # Generate PDF from existing analysis
        from backend.pdf_generator import generate_pdf
        # Re-run analysis to get result object
        # For now, serve the markdown report
        raise HTTPException(status_code=503, detail="PDF generation requires re-analysis. Use /api/analyze first.")

    return FileResponse(pdf_path, media_type="application/pdf")


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


@app.post("/api/cache/financials/{ticker}")
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


@app.get("/api/analyses")
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
