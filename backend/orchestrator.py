"""Orchestrator - runs analysis sequentially or in parallel."""
import concurrent.futures
import logging
from typing import Any, Callable, Dict, List

from backend.pipeline import AnalysisResult, analyze_ticker_fast

logger = logging.getLogger(__name__)

PER_TICKER_TIMEOUT = 1200  # generous for deep-dive LLM phase


def _format_scoring_breakdown(scoring) -> str:
    """Format 6-category scoring breakdown for log output.
    Returns: "FH=8/10 G=7/10 V=6/8 M=4/5 Mo=3/4 S=2/3 = 30/40"
    """
    s = scoring
    cats = [
        ("FH", s.financial_health, 10),
        ("G", s.growth, 10),
        ("V", s.valuation, 8),
        ("M", s.management, 5),
        ("Mo", s.moat, 4),
        ("S", s.sentiment, 3),
    ]
    parts = [f"{label}={val}/{maxv}" for label, val, maxv in cats]
    return " ".join(parts) + f" = {s.total}/40"


def _await_future_with_progress(future: concurrent.futures.Future, ticker: str) -> AnalysisResult:
    """Wait for an analysis future without recording false failures.

    Python cannot cancel a running ThreadPoolExecutor worker. The previous
    implementation treated ``future.result(timeout=...)`` as a hard deadline,
    but the worker continued building PDFs and artifacts after the admin log had
    already recorded a failed timeout. This helper uses PER_TICKER_TIMEOUT as a
    progress-warning interval: if the analysis is still alive, log that fact and
    keep waiting for the real result or real exception.
    """
    warned = False
    while True:
        try:
            return future.result(timeout=PER_TICKER_TIMEOUT)
        except concurrent.futures.TimeoutError:
            if not warned:
                logger.warning(
                    "%s: still running after %ss; waiting for completion instead of marking failed",
                    ticker,
                    PER_TICKER_TIMEOUT,
                )
                warned = True
            else:
                logger.warning(
                    "%s: still running; analysis worker is alive and remains the source of truth",
                    ticker,
                )


def run_analysis_sequential(tickers: List[str], output_base: str = "analyses") -> Dict[str, Any]:
    """Run analysis for multiple tickers sequentially.

    PER_TICKER_TIMEOUT is a progress-warning interval, not a false failure
    deadline. A running analysis may legitimately exceed it while the PDF/LLM
    pipeline is still producing artifacts.
    """
    results: Dict[str, AnalysisResult] = {}
    errors: Dict[str, str] = {}

    for ticker in tickers:
        try:
            logger.info(f"Analyzing {ticker} (fast, progress_timeout={PER_TICKER_TIMEOUT}s)...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(analyze_ticker_fast, ticker, output_base)
                result = _await_future_with_progress(future, ticker)
            results[ticker] = result
            logger.info(f"{ticker}: {result.decision} | {_format_scoring_breakdown(result.scoring)}")
        except Exception as e:
            logger.error(f"{ticker}: {e}")
            errors[ticker] = str(e)

    return {"results": results, "errors": errors}


def run_analysis_parallel(
    tickers: List[str],
    output_base: str = "analyses",
    max_workers: int | None = None,
    language: str = "en",
    force_refresh: bool = False,
    progress_callback: Callable[[str], None] | None = None,
    background_deep_dive: bool = False,
) -> Dict[str, Any]:
    """Run multiple ticker analyses concurrently.

    PER_TICKER_TIMEOUT is treated as a progress-warning interval. A running
    ThreadPoolExecutor future cannot be safely killed, so recording a timeout as
    a final admin failure while the pipeline continues creates contradictory
    state: admin says failed, but PDFs/artifacts are later generated. Only real
    exceptions become errors.
    """
    results: Dict[str, AnalysisResult] = {}
    errors: Dict[str, str] = {}
    if not tickers:
        return {"results": results, "errors": errors}

    worker_count = max_workers or min(len(tickers), 4)
    worker_count = max(1, min(worker_count, len(tickers)))
    logger.info(f"Analyzing {len(tickers)} tickers in parallel (workers={worker_count}, lang={language}, force_refresh={force_refresh})")
    if progress_callback:
        progress_callback(f"Analyzing {len(tickers)} ticker(s) with {worker_count} worker(s)…")

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {}
        for ticker in tickers:
            if progress_callback:
                progress_callback(f"Analyzing {ticker}: financial data, SEC filings, scoring…")
            futures[
                executor.submit(
                    analyze_ticker_fast,
                    ticker,
                    output_base,
                    language,
                    force_refresh,
                    background_deep_dive=background_deep_dive,
                )
            ] = ticker
        pending = set(futures)
        warned: set[concurrent.futures.Future] = set()
        while pending:
            done, pending = concurrent.futures.wait(
                pending,
                timeout=PER_TICKER_TIMEOUT,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            if not done:
                for future in pending:
                    ticker = futures[future]
                    if future not in warned:
                        logger.warning(
                            "%s: still running after %ss; waiting for completion instead of marking failed",
                            ticker,
                            PER_TICKER_TIMEOUT,
                        )
                        warned.add(future)
                        if progress_callback:
                            progress_callback(f"{ticker}: still running after {PER_TICKER_TIMEOUT}s…")
                    else:
                        logger.warning(
                            "%s: still running; analysis worker is alive and remains the source of truth",
                            ticker,
                        )
                        if progress_callback:
                            progress_callback(f"{ticker}: still running; waiting for completion…")
                continue

            for future in done:
                ticker = futures[future]
                try:
                    result = future.result()
                    results[ticker] = result
                    logger.info(f"{ticker}: {result.decision} | {_format_scoring_breakdown(result.scoring)}")
                    if progress_callback:
                        progress_callback(f"{ticker}: analysis complete")
                except Exception as e:
                    logger.error(f"{ticker}: {e}")
                    errors[ticker] = str(e)

    return {"results": results, "errors": errors}
