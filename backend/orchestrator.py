"""Orchestrator — dispatches analysis to sub-agents and aggregates results."""
import os
import logging
from typing import List, Dict, Any

from backend.models import AnalysisResult
from backend.pipeline import analyze_ticker

logger = logging.getLogger(__name__)


def run_analysis_batch(tickers: List[str], output_base: str = "analyses") -> Dict[str, Any]:
    """
    Run analysis for multiple tickers sequentially (for now).
    In production: delegate_task per ticker.

    Returns {ticker: AnalysisResult} dict.
    """
    results: Dict[str, AnalysisResult] = {}
    errors: Dict[str, str] = {}

    for ticker in tickers:
        try:
            logger.info(f"Analyzing {ticker}...")
            result = analyze_ticker(ticker, output_base=output_base)
            results[ticker] = result
            logger.info(f"{ticker}: {result.decision} ({result.scoring.total}/40)")
        except Exception as e:
            logger.error(f"{ticker}: {e}")
            errors[ticker] = str(e)

    return {"results": results, "errors": errors}


# In-memory job store (for FastAPI polling)
_jobs: Dict[str, Dict[str, Any]] = {}


def create_job(job_id: str, tickers: List[str]) -> None:
    """Register a new analysis job."""
    _jobs[job_id] = {
        "job_id": job_id,
        "tickers": tickers,
        "status": "processing",
        "results": {},
        "errors": {},
    }


def get_job(job_id: str) -> Dict[str, Any]:
    """Get job status."""
    return _jobs.get(job_id, {"job_id": job_id, "status": "not_found", "results": {}, "errors": {}})


def set_job_completed(job_id: str, results: Dict, errors: Dict) -> None:
    """Mark a job as completed with results."""
    if job_id in _jobs:
        j = _jobs[job_id]
        j["status"] = "completed" if not errors else ("partial" if results else "failed")
        j["results"] = {t: r.model_dump() if hasattr(r, 'model_dump') else r
                         for t, r in results.items()}
        j["errors"] = errors
