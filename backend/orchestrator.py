"""Orchestrator — dispatches analysis to sub-agents and aggregates results."""
import os
import uuid
import logging
from typing import List, Dict, Any

from backend.models import AnalysisResult
from backend.pipeline import analyze_ticker, analyze_ticker_fast

logger = logging.getLogger(__name__)


def run_analysis_sequential(tickers: List[str], output_base: str = "analyses") -> Dict[str, Any]:
    """Run analysis for multiple tickers sequentially."""
    results: Dict[str, AnalysisResult] = {}
    errors: Dict[str, str] = {}

    for ticker in tickers:
        try:
            logger.info(f"Analyzing {ticker} (fast)...")
            result = analyze_ticker_fast(ticker, output_base=output_base)
            results[ticker] = result
            logger.info(f"{ticker}: {result.decision} ({result.scoring.total}/40)")
        except Exception as e:
            logger.error(f"{ticker}: {e}")
            errors[ticker] = str(e)

    return {"results": results, "errors": errors}


def run_analysis_parallel(tickers: List[str], output_base: str = "analyses") -> Dict[str, Any]:
    """
    Placeholder for parallel analysis via delegate_task.
    Currently falls back to sequential — delegate_task is not available
    inside FastAPI worker processes.
    """
    logger.info(f"Parallel analysis requested for {len(tickers)} tickers — falling back to sequential")
    return run_analysis_sequential(tickers, output_base)
