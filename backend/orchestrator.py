"""Orchestrator - runs analysis sequentially or in parallel."""
import concurrent.futures
import logging
from typing import Any, Dict, List

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
            logger.info(f"{ticker}: {result.decision} | {_format_scoring_breakdown(result.scoring)}")
        except concurrent.futures.TimeoutError:
            logger.error(f"{ticker}: TIMEOUT after {PER_TICKER_TIMEOUT}s")
            errors[ticker] = f"Analysis timed out after {PER_TICKER_TIMEOUT}s"
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
) -> Dict[str, Any]:
    """Run multiple ticker analyses concurrently with per-ticker timeout."""
    results: Dict[str, AnalysisResult] = {}
    errors: Dict[str, str] = {}
    if not tickers:
        return {"results": results, "errors": errors}

    worker_count = max_workers or min(len(tickers), 4)
    worker_count = max(1, min(worker_count, len(tickers)))
    logger.info(f"Analyzing {len(tickers)} tickers in parallel (workers={worker_count}, lang={language}, force_refresh={force_refresh})")

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(analyze_ticker_fast, ticker, output_base, language, force_refresh): ticker
            for ticker in tickers
        }
        pending = set(futures)
        while pending:
            done, pending = concurrent.futures.wait(
                pending,
                timeout=PER_TICKER_TIMEOUT,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            if not done:
                for future in list(pending):
                    ticker = futures[future]
                    future.cancel()
                    logger.error(f"{ticker}: TIMEOUT after {PER_TICKER_TIMEOUT}s")
                    errors[ticker] = f"Analysis timed out after {PER_TICKER_TIMEOUT}s"
                    pending.remove(future)
                break

            for future in done:
                ticker = futures[future]
                try:
                    result = future.result()
                    results[ticker] = result
                    logger.info(f"{ticker}: {result.decision} | {_format_scoring_breakdown(result.scoring)}")
                except Exception as e:
                    logger.error(f"{ticker}: {e}")
                    errors[ticker] = str(e)

    return {"results": results, "errors": errors}
