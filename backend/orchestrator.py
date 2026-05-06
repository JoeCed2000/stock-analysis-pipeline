"""Orchestrator — runs analysis sequentially or in parallel."""
import logging
import concurrent.futures
from typing import Dict, Any, List
from backend.pipeline import analyze_ticker_fast, AnalysisResult

logger = logging.getLogger(__name__)

PER_TICKER_TIMEOUT = 300  # seconds — 2 Kimi calls + stock data + dossier generation = up to 280s


def run_analysis_sequential(tickers: List[str], output_base: str = "analyses") -> Dict[str, Any]:
    """Run analysis for multiple tickers sequentially with per-ticker timeout."""
    results: Dict[str, AnalysisResult] = {}
    errors: Dict[str, str] = {}

    for ticker in tickers:
        try:
            logger.info(f"Analyzing {ticker} (fast, timeout={PER_TICKER_TIMEOUT}s)...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(analyze_ticker_fast, ticker, output_base)
                result = future.result(timeout=PER_TICKER_TIMEOUT)
            results[ticker] = result
            logger.info(f"{ticker}: {result.decision} ({result.scoring.total}/40)")
        except concurrent.futures.TimeoutError:
            logger.error(f"{ticker}: TIMEOUT after {PER_TICKER_TIMEOUT}s")
            errors[ticker] = f"Analysis timed out after {PER_TICKER_TIMEOUT}s"
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
