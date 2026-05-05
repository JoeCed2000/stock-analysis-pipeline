import os
import sys

# Load .env
with open('.env') as f:
    for line in f:
        if line.strip() and not line.startswith('#') and '=' in line:
            k, v = line.strip().split('=', 1)
            os.environ[k] = v

from backend.pipeline import analyze_ticker

tickers = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META', 'ASML', 'MC.PA']
for t in tickers:
    try:
        r = analyze_ticker(t, output_base='analyses')
        conv = getattr(r.scoring, 'conviction', 'N/A')
        print(f'{t}: {r.decision} {r.scoring.total}/40 conv={conv}')
    except Exception as e:
        print(f'{t}: ERROR {e}')
