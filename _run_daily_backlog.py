#!/usr/bin/env python3
"""Daily backlog runner — Cron-friendly script."""
import os, sys

# Load .env
env_path = os.path.join(os.path.dirname(__file__), '.env')
with open(env_path) as f:
    for line in f:
        if line.strip() and not line.startswith('#') and '=' in line:
            k, v = line.strip().split('=', 1)
            os.environ[k] = v

from backend.pipeline import analyze_ticker

# Default watchlist (no BACKLOG.md found)
tickers = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META', 'ASML', 'MC.PA']

for t in tickers:
    try:
        print(f'[{t}] Starting analysis...', flush=True)
        r = analyze_ticker(t, output_base='analyses')
        print(f'{t}: DECISION={r.decision} SCORE={r.scoring.total}/40 CONVICTION={r.conviction}', flush=True)
    except Exception as e:
        import traceback
        print(f'{t}: ERROR {e}', flush=True)
        traceback.print_exc()
    sys.stdout.flush()
