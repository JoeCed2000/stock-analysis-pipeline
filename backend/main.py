"""FastAPI application for Stock Analysis Pipeline."""
import os
import uuid
import logging
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.models import TickerRequest, AnalysisResult
from backend.orchestrator import (
    run_analysis_batch, create_job, get_job, set_job_completed
)

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


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "stock-analysis-pipeline"}


@app.post("/api/analyze")
async def analyze(request: TickerRequest):
    """Submit tickers for analysis. Runs sequentially, returns results immediately."""
    tickers = request.tickers
    logger.info(f"Analyze request: {tickers}")

    try:
        batch = run_analysis_batch(tickers, output_base=str(ANALYSES_DIR))
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
        results_list.append(r)

    return JSONResponse({
        "status": "completed" if not batch["errors"] else "partial",
        "results": results_list,
        "errors": errors_list,
    })


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
