"""
Preload system — silently collects maximum data for prioritized tickers.

Phase 1: Mag 7 bulk collection (transcripts, financials, SEC filings, press releases, audio)
Design: standalone module, run via `python3 -m backend.preload.scheduler --mode full`
"""
