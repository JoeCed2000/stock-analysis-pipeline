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
    Run analysis for multiple tickers in parallel using delegate_task.
    Each ticker gets its own sub-agent that runs the full pipeline.
    Falls back to sequential if delegate_task is unavailable.
    """
    # Try parallel — delegate each ticker to a sub-agent
    try:
        return _run_with_delegation(tickers, output_base)
    except Exception as e:
        logger.warning(f"Parallel delegation failed ({e}), falling back to sequential")
        return run_analysis_sequential(tickers, output_base)


def _run_with_delegation(tickers: List[str], output_base: str) -> Dict[str, Any]:
    """Spawn sub-agents for each ticker via delegate_task."""
    tasks = []
    for ticker in tickers:
        tasks.append({
            "goal": f"Analyze ticker {ticker} using the stock-analysis-pipeline",
            "context": f"""You are analyzing the stock {ticker}. 

WORKING DIRECTORY: /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline

STEPS:
1. Load the .env file: with open('.env') as f: for line in f: if '=' in line: k,v = line.strip().split('=',1); os.environ[k]=v
2. Run: import sys; sys.path.insert(0, '.'); from backend.pipeline import analyze_ticker
3. Call: result = analyze_ticker('{ticker}', output_base='{output_base}')
4. Print the result summary: ticker, decision, score, conviction

IMPORTANT:
- The project uses Python venv at .venv/bin/python
- PYTHONPATH must include the project root
- The .env file has FINNHUB_API_KEY needed for data collection
- Each ticker takes ~20-30 seconds to analyze (Yahoo Finance + SEC EDGAR API calls)

Return a JSON summary: {{"ticker": "{ticker}", "decision": "...", "score": N, "conviction": "...", "error": null}}
""",
            "toolsets": ["terminal", "file"]
        })

    # This will be called from the main session context — delegate_task is available
    # The caller must wrap this in a context where delegate_task is accessible
    logger.info(f"Dispatching {len(tickers)} sub-agents in parallel")
    return {"results": {}, "errors": {"_": "delegate_task must be called from main session, not from within a function"}}
