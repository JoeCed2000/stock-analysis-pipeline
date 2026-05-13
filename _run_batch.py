"""Batch analysis script for daily cron job."""
import os
import sys

# Load .env
env_path = os.path.join(os.path.dirname(__file__), '.env')
with open(env_path) as f:
    for line in f:
        if line.strip() and not line.startswith('#') and '=' in line:
            k, v = line.strip().split('=', 1)
            os.environ[k] = v

sys.path.insert(0, os.path.dirname(__file__))
from backend.pipeline import analyze_ticker

TICKERS = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META', 'ASML', 'MC.PA']
OUTPUT_BASE = os.path.join(os.path.dirname(__file__), 'analyses')

for t in TICKERS:
    try:
        r = analyze_ticker(t, output_base=OUTPUT_BASE)
        print(f'{t}: {r.decision} {r.scoring.total}/40 conv={r.scoring.conviction}')
    except Exception as e:
        print(f'{t}: ERROR {e}')
