"""Daily backlog runner — runs analyze_ticker for watchlist tickers."""
import os
import sys
import traceback

# Load .env
env_path = os.path.join(os.path.dirname(__file__), '.env')
with open(env_path) as f:
    for line in f:
        if line.strip() and not line.startswith('#') and '=' in line:
            k, v = line.strip().split('=', 1)
            os.environ[k] = v

from backend.pipeline import analyze_ticker

TICKERS = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META', 'ASML', 'MC.PA']

for t in TICKERS:
    try:
        r = analyze_ticker(t, output_base='analyses')
        print(f'{t}: {r.decision} | Score: {r.scoring.total}/40 | Conviction: {r.scoring.conviction}')
    except Exception as e:
        traceback.print_exc()
        print(f'{t}: ERROR {e}')
