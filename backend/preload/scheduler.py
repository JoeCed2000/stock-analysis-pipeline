"""
Preload scheduler — CLI entry point for batch data collection.

Usage:
    python3 -m backend.preload.scheduler --mode full
    python3 -m backend.preload.scheduler --mode full --tickers AAPL,MSFT,NVDA
    python3 -m backend.preload.scheduler --mode light
    python3 -m backend.preload.scheduler --mode transcripts-only
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List

# Ensure backend importable
_backend_root = Path(__file__).parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root.parent))

from backend.preload import registry, fetchers, store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("preload.scheduler")


def _collect_ticker_full(ticker: str, company: str) -> dict:
    """Collect ALL available data for one ticker — vrac mode."""
    status = {"ticker": ticker, "company": company, "ok": [], "fail": [], "skipped": []}
    t0 = time.time()
    
    # 1. Financials (yfinance — cheap, fast)
    logger.info(f"[{ticker}] Fetching financials (5yr quarterly)...")
    try:
        fin = fetchers.fetch_financials(ticker)
        path = store.save_financials(ticker, fin)
        status["ok"].append(f"financials → {path}")
        status["financials_ok"] = True
    except Exception as e:
        logger.error(f"[{ticker}] Financials failed: {e}")
        status["fail"].append(f"financials: {e}")
        status["financials_ok"] = False
    
    # 2. Transcripts
    logger.info(f"[{ticker}] Searching transcripts...")
    try:
        transcripts = fetchers.fetch_transcripts(ticker, company)
        for t in transcripts:
            path = store.save_transcript(
                ticker, t["text"],
                source=t["source"],
                url=t.get("url", ""),
                quarter=t.get("quarter", ""),
                date=t.get("date", ""),
            )
            status["ok"].append(f"transcript ({t['source']}, {t['chars']} chars) → {path}")
        if transcripts:
            status["transcript_ok"] = True
        else:
            status["transcript_ok"] = False
            status["fail"].append("transcript: no transcript found from any source")
    except Exception as e:
        logger.error(f"[{ticker}] Transcript search failed: {e}")
        status["fail"].append(f"transcript: {e}")
        status["transcript_ok"] = False
    
    # 3. SEC filings
    logger.info(f"[{ticker}] Fetching SEC filings...")
    try:
        sec = fetchers.fetch_sec_filings(ticker)
        path = store.save_sec_filing(ticker, "latest", sec)
        n_filings = len(sec.get("filings", []))
        status["ok"].append(f"SEC filings ({n_filings} forms) → {path}")
        status["sec_ok"] = True
    except Exception as e:
        logger.error(f"[{ticker}] SEC filings failed: {e}")
        status["fail"].append(f"sec: {e}")
        status["sec_ok"] = False
    
    # 4. Press releases / presentations
    logger.info(f"[{ticker}] Searching press releases...")
    try:
        docs = fetchers.fetch_press_releases(ticker, company)
        for d in docs:
            path = store.save_press_release(ticker, d)
            status["ok"].append(f"{d['type']} ({d.get('source', '?')}) → {path}")
        if docs:
            status["press_ok"] = True
        else:
            status["fail"].append("press: no press release or presentation found")
            status["press_ok"] = False
    except Exception as e:
        logger.error(f"[{ticker}] Press release search failed: {e}")
        status["fail"].append(f"press: {e}")
        status["press_ok"] = False
    
    # 5. IR page HTML
    logger.info(f"[{ticker}] Fetching IR page...")
    try:
        html = fetchers.fetch_ir_page(ticker)
        if html:
            path = store.save_ir_page(ticker, html)
            status["ok"].append(f"IR page → {path}")
            status["ir_ok"] = True
        else:
            status["skipped"].append("ir_page: no IR URL found or fetch failed")
            status["ir_ok"] = False
    except Exception as e:
        logger.error(f"[{ticker}] IR page failed: {e}")
        status["fail"].append(f"ir_page: {e}")
        status["ir_ok"] = False
    
    # 6. Earnings calendar
    logger.info(f"[{ticker}] Saving earnings calendar...")
    try:
        # Calendar data is already in financials, extract it
        fin = store.ticker_dir(ticker) / "normalized" / "financials.json"
        if fin.exists():
            import json
            with open(fin) as f:
                fin_data = json.load(f)
            cal = fin_data.get("earnings_dates", {})
            if cal:
                path = store.save_earnings_calendar(ticker, cal)
                status["ok"].append(f"earnings calendar → {path}")
    except Exception as e:
        logger.error(f"[{ticker}] Calendar save failed: {e}")
    
    # 7. Audio URLs (find but don't download — too heavy for Phase 1)
    logger.info(f"[{ticker}] Searching audio URLs...")
    try:
        audio_urls = fetchers.fetch_audio_urls(ticker)
        if audio_urls:
            path = store.save_press_release(ticker, {"type": "audio_urls", "urls": audio_urls})
            status["ok"].append(f"audio URLs ({len(audio_urls)} found) → {path}")
    except Exception as e:
        logger.debug(f"[{ticker}] Audio search failed: {e}")
    
    # Update manifest
    elapsed = time.time() - t0
    store.update_manifest(
        ticker,
        company=company,
        status="ok" if status["financials_ok"] else "partial",
        sources={
            "financials": {"status": "ok" if status.get("financials_ok") else "failed"},
            "transcript": {"status": "ok" if status.get("transcript_ok") else "missing"},
            "sec": {"status": "ok" if status.get("sec_ok") else "failed"},
            "press_release": {"status": "ok" if status.get("press_ok") else "missing"},
            "ir_page": {"status": "ok" if status.get("ir_ok") else "missing"},
        },
        collection_duration_s=round(elapsed, 1),
        collected_at=datetime.now(timezone.utc).isoformat(),
    )
    
    status["duration_s"] = round(elapsed, 1)
    return status


def run_full(tickers: List[str] = None):
    """Full collection mode — get everything for specified (or Mag 7) tickers."""
    if tickers:
        # Lookup company names from registry
        universe = registry.get_universe()
        name_map = {m["ticker"]: m.get("company", m["ticker"]) for m in universe}
        targets = [(t.upper(), name_map.get(t.upper(), t.upper())) for t in tickers]
    else:
        targets = [(m["ticker"], m["company"]) for m in registry.MAG7]
    
    logger.info(f"=== Preload FULL mode — {len(targets)} tickers ===")
    for t, c in targets:
        logger.info(f"  {t}: {c}")
    
    results = []
    for i, (ticker, company) in enumerate(targets):
        logger.info(f"\n{'='*60}")
        logger.info(f"[{i+1}/{len(targets)}] {ticker} ({company})")
        logger.info(f"{'='*60}")
        
        status = _collect_ticker_full(ticker, company)
        results.append(status)
        
        # Summary after each ticker
        logger.info(f"[{ticker}] Done in {status['duration_s']}s — "
                    f"{len(status['ok'])} ok, {len(status['fail'])} fail, "
                    f"{len(status['skipped'])} skipped")
    
    # Final summary
    logger.info(f"\n{'='*60}")
    logger.info(f"PRELOAD COMPLETE — {len(results)} tickers")
    logger.info(f"{'='*60}")
    total_ok = sum(len(r["ok"]) for r in results)
    total_fail = sum(len(r["fail"]) for r in results)
    logger.info(f"Total: {total_ok} ok, {total_fail} fail")
    
    for r in results:
        emoji = "✅" if not r["fail"] else "⚠️"
        logger.info(f"  {emoji} {r['ticker']}: {len(r['ok'])} ok, {len(r['fail'])} fail "
                    f"({r['duration_s']}s)")
    
    # Save global state
    preload_state = {
        "last_full_run": datetime.now(timezone.utc).isoformat(),
        "tickers_processed": len(results),
        "total_ok": total_ok,
        "total_fail": total_fail,
        "results": [
            {
                "ticker": r["ticker"],
                "ok_count": len(r["ok"]),
                "fail_count": len(r["fail"]),
                "duration_s": r["duration_s"],
                "financials_ok": r.get("financials_ok", False),
                "transcript_ok": r.get("transcript_ok", False),
                "sec_ok": r.get("sec_ok", False),
            }
            for r in results
        ],
    }
    state_path = _backend_root / ".cache" / "preload_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    with open(state_path, "w") as f:
        json.dump(preload_state, f, indent=2, default=str)
    logger.info(f"State saved: {state_path}")


def run_light():
    """Light refresh — financials only for Mag 7."""
    from backend.preload.registry import MAG7
    logger.info("=== Preload LIGHT mode — financials only ===")
    for m in MAG7:
        ticker, company = m["ticker"], m["company"]
        logger.info(f"[{ticker}] Light refresh...")
        try:
            fin = fetchers.fetch_financials(ticker)
            store.save_financials(ticker, fin)
            store.update_manifest(ticker, last_light_refresh=datetime.now(timezone.utc).isoformat())
            logger.info(f"[{ticker}] ✅")
        except Exception as e:
            logger.error(f"[{ticker}] ❌ {e}")


def main():
    parser = argparse.ArgumentParser(description="Preload scheduler")
    parser.add_argument("--mode", choices=["full", "light", "transcripts-only"],
                        default="full", help="Collection mode")
    parser.add_argument("--tickers", type=str, default=None,
                        help="Comma-separated tickers (default: Mag 7)")
    args = parser.parse_args()
    
    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
    
    if args.mode == "full":
        run_full(tickers)
    elif args.mode == "light":
        run_light()
    elif args.mode == "transcripts-only":
        logger.info("Transcripts-only mode not implemented yet")


if __name__ == "__main__":
    main()
