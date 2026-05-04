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

from fastapi import FastAPI, HTTPException, UploadFile, File as FastAPIFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.models import TickerRequest, AnalysisResult
from backend.orchestrator import run_analysis_sequential

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

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

TICKER_RE = re.compile(r'^[A-Z]{1,5}(?:\.[A-Z]{2})?$')  # AAPL or MC.PA
ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{10}$')  # US0378331005

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


def _parse_tickers_from_text(text: str) -> List[dict]:
    """Parse text into list of {value, type, normalized} items."""
    items = []
    seen = set()

    # Split by newlines, commas, semicolons, spaces
    tokens = re.split(r'[\n,;\s]+', text.strip())

    for token in tokens:
        token = token.strip().upper()
        if not token:
            continue
        if token in seen:
            continue

        if ISIN_RE.match(token):
            ticker = ISIN_TO_TICKER.get(token, token)
            items.append({
                "value": token,
                "type": "ISIN",
                "normalized": ticker,
            })
            seen.add(token)
        elif TICKER_RE.match(token):
            items.append({
                "value": token,
                "type": "TICKER",
                "normalized": token,
            })
            seen.add(token)
        else:
            # Try as raw ticker anyway (might be exotic)
            if 1 <= len(token) <= 10 and token.replace('.', '').isalpha():
                items.append({
                    "value": token,
                    "type": "TICKER",
                    "normalized": token,
                })
                seen.add(token)

    return items


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


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "stock-analysis-pipeline"}


@app.post("/api/analyze")
async def analyze(request: TickerRequest):
    """Submit tickers for analysis. Runs sequentially, returns results immediately."""
    tickers = request.tickers
    logger.info(f"Analyze request: {tickers}")

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
