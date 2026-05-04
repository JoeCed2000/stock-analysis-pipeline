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
from datetime import datetime

from fastapi import FastAPI, HTTPException, UploadFile, File as FastAPIFile, Header, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.models import TickerRequest, AnalysisResult
from backend.orchestrator import run_analysis_sequential

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
                os.environ.setdefault(k.strip(), v.strip())

app = FastAPI(title="Stock Analysis Pipeline", version="1.0.0")

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

TICKER_RE = re.compile(r'^[A-Z]{1,5}(?:\.[A-Z]{1,2})?$')  # AAPL, MC.PA, BRK.B
ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{10}$')  # US0378331005

# Lazy import yfinance for ticker validation
_yf_available = None

def _get_yf():
    global _yf_available
    if _yf_available is None:
        try:
            import yfinance as yf
            _yf_available = yf
        except ImportError:
            _yf_available = False
    return _yf_available


def _ticker_exists(ticker: str) -> bool:
    """Check if ticker exists on Yahoo Finance.
    Returns True if ticker exists OR if we can't validate (rate-limited).
    Returns False ONLY if yfinance explicitly returns empty/error for a ticker
    that should have data — but this is rare; almost always returns True on Render.
    """
    yf = _get_yf()
    if not yf:
        return True  # Can't validate — don't block
    try:
        info = yf.Ticker(ticker).info
        # Count non-None fields as a proxy for data richness
        meaningful = sum(1 for v in info.values() if v is not None)
        if meaningful <= 3:
            # Too sparse to validate — likely rate-limited. Allow the ticker.
            return True
        # Has rich data — check for actual company name
        has_name = bool(info.get('shortName') or info.get('longName'))
        return has_name
    except Exception:
        return True  # Can't validate — don't block

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
                if ticker:
                    items.append({
                        "value": token, "type": "ISIN",
                        "normalized": ticker, "status": "valid",
                    })
                else:
                    items.append({
                        "value": token, "type": "ISIN",
                        "normalized": token, "status": "valid",
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

    logger.info(f"Batch job {job_id}: {len(request.tickers)} tickers queued")

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
        raise HTTPException(status_code=404, detail="Job not found")

    # If pending, process now
    if job["status"] == "pending":
        job["status"] = "processing"
        for ticker in job["tickers"]:
            try:
                logger.info(f"[{job_id}] Analyzing {ticker}...")
                result = run_analysis_sequential([ticker], output_base=str(ANALYSES_DIR))
                if ticker in result["results"]:
                    job["results"][ticker] = result["results"][ticker]
                elif ticker in result.get("errors", {}):
                    job["errors"][ticker] = result["errors"][ticker]
                else:
                    job["errors"][ticker] = "Unknown error"
                job["completed"] += 1
            except Exception as e:
                logger.error(f"[{job_id}] {ticker}: {e}")
                job["errors"][ticker] = str(e)
                job["completed"] += 1

        job["status"] = "completed" if not job["errors"] else "partial"

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
    ticker_clean = ticker.replace(".", "_")
    matches = sorted(ANALYSES_DIR.glob(f"*_{ticker_clean}_*"), reverse=True)
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
    return {"status": "ok", "service": "stock-analysis-pipeline"}


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


@app.get("/api/dossier/{ticker}/status")
async def dossier_status(ticker: str):
    """Check if the full dossier (PDF, Excel, 10-K) is ready for a ticker.
    Returns {ready: bool, files: [...], stage: str}."""
    from backend.async_dossier import get_dossier_status
    status = get_dossier_status(ticker)
    return JSONResponse(status)


@app.get("/api/dossier/{ticker}/download")
async def dossier_download(ticker: str):
    """Download the complete dossier as ZIP. Generates files synchronously if not ready.
    Converts MD/TXT → PDF on-the-fly. ZIP contains ONLY PDF + XLSX + README.txt."""
    from backend.async_dossier import get_dossier_status
    status = get_dossier_status(ticker)
    
    # If dossier not ready, generate it synchronously
    if not status.get("ready"):
        logger.info(f"[{ticker}] Dossier not ready — generating synchronously...")
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
    
    ticker_clean = ticker.replace(".", "_")
    matches = sorted(ANALYSES_DIR.glob(f"*_{ticker_clean}_*"), reverse=True)
    if not matches:
        raise HTTPException(status_code=404, detail=f"No analysis found for {ticker}")
    
    analysis_dir = matches[0]
    
    # Pre-convert MD/TXT files to PDF on-the-fly 
    try:
        from backend.pdf_generator import md_to_pdf
        for fpath in sorted(analysis_dir.rglob("*.md")):
            if fpath.name == "README.md":
                continue
            pdf_path = fpath.with_suffix(".pdf")
            if not pdf_path.exists():
                try:
                    md_to_pdf(str(fpath), str(pdf_path), title=f"{ticker} — {fpath.stem.replace('_', ' ').title()}")
                    logger.info(f"[{ticker}] Converted {fpath.name} → PDF")
                except Exception as e:
                    logger.warning(f"[{ticker}] MD→PDF failed for {fpath.name}: {e}")
        for fpath in sorted(analysis_dir.rglob("*.txt")):
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
        for fpath in sorted(analysis_dir.rglob("*")):
            if fpath.is_file():
                # Only PDF + XLSX + README.txt in the deliverable ZIP
                if fpath.suffix in ('.json', '.csv', '.md'):
                    continue
                if fpath.suffix == '.txt' and fpath.name != 'README.txt':
                    continue
                arcname = fpath.relative_to(analysis_dir)
                zf.write(fpath, arcname)
                included_dirs.add(str(arcname.parent))
        
        # Ensure ALL 7 directories are represented
        for folder in ["01_official_company_sources", "02_sec_or_regulatory_filings",
                       "03_financial_data_sources", "04_transcripts_and_management",
                       "05_market_and_context", "06_extracted_data", "07_final_report"]:
            if folder not in included_dirs:
                zf.writestr(f"{folder}/README.txt",
                           f"{folder}\n{'='*len(folder)}\n\nDossier section — see full report for details.\n")
    
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={ticker}_dossier.zip"},
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
    
    # Find or create analysis directory
    ticker_clean = ticker.replace(".", "_").upper()
    matches = sorted(ANALYSES_DIR.glob(f"*_{ticker_clean}_*"), reverse=True)
    if not matches:
        # No analysis exists — create a minimal directory
        date_str = datetime.now().strftime("%Y-%m-%d")
        analysis_dir = ANALYSES_DIR / f"{date_str}_{ticker_clean}_UPLOADED"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        for s in ALLOWED_SECTIONS:
            (analysis_dir / s).mkdir(parents=True, exist_ok=True)
    else:
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
async def analyze(request: TickerRequest):
    """Submit tickers for analysis. Runs sequentially, returns results immediately."""
    tickers = request.tickers
    logger.info(f"Analyze request: {tickers}")

    # Validate all tickers before processing
    invalid_tickers = [t for t in tickers if not TICKER_RE.match(t.upper().strip())]
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
        batch = run_analysis_sequential(tickers, output_base=str(ANALYSES_DIR))
    except Exception as e:
        logger.exception("Batch analysis failed")
        raise HTTPException(status_code=500, detail=str(e))

    results_list = []
    errors_list = list(batch["errors"].values())

    for ticker, result in batch["results"].items():
        r = result.model_dump()
        r.pop("financials", None)
        r.pop("management_tone", None)
        r.pop("segments", None)
        r.pop("valuation", None)
        # Include computed total (Pydantic doesn't serialize @property)
        if "scoring" in r and isinstance(r["scoring"], dict):
            r["scoring"]["total"] = result.scoring.total
        results_list.append(r)

    return JSONResponse({
        "status": "completed" if not batch["errors"] else "partial",
        "results": results_list,
        "errors": errors_list,
    })


@app.get("/api/report/{ticker}/pdf")
async def get_report_pdf(ticker: str):
    """Generate and retrieve PDF report for a ticker."""
    ticker_clean = ticker.replace(".", "_")
    matches = sorted(ANALYSES_DIR.glob(f"*_{ticker_clean}_*"), reverse=True)
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
    ticker_clean = ticker.replace(".", "_")
    matches = sorted(ANALYSES_DIR.glob(f"*_{ticker_clean}_*"), reverse=True)
    if not matches:
        raise HTTPException(status_code=404, detail=f"No analysis found for {ticker}")

    report_path = matches[0] / "07_final_report" / "report.md"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found for {ticker}")

    return FileResponse(report_path, media_type="text/markdown")


@app.get("/api/sources/{ticker}")
async def get_sources(ticker: str):
    """Retrieve the sources manifest for a ticker."""
    ticker_clean = ticker.replace(".", "_")
    matches = sorted(ANALYSES_DIR.glob(f"*_{ticker_clean}_*"), reverse=True)
    if not matches:
        raise HTTPException(status_code=404, detail=f"No analysis found for {ticker}")

    manifest_path = matches[0] / "06_extracted_data" / "sources_manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Manifest not found for {ticker}")

    return FileResponse(manifest_path, media_type="application/json")


@app.get("/api/traceability/{ticker}")
async def get_traceability(ticker: str):
    """Retrieve the claim traceability matrix for a ticker."""
    ticker_clean = ticker.replace(".", "_")
    matches = sorted(ANALYSES_DIR.glob(f"*_{ticker_clean}_*"), reverse=True)
    if not matches:
        raise HTTPException(status_code=404, detail=f"No analysis found for {ticker}")

    csv_path = matches[0] / "06_extracted_data" / "claim_traceability_matrix.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"Traceability matrix not found for {ticker}")

    return FileResponse(csv_path, media_type="text/csv")


@app.get("/api/analyses")
async def list_analyses():
    """List all completed analyses."""
    analyses = []
    if ANALYSES_DIR.exists():
        for d in sorted(ANALYSES_DIR.iterdir(), reverse=True):
            if d.is_dir():
                report = d / "07_final_report" / "report.md"
                analyses.append({
                    "directory": d.name,
                    "has_report": report.exists(),
                })
    return {"analyses": analyses}
