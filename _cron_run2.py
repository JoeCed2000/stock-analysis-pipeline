import os, sys
sys.path.insert(0, '.')

with open('.env') as f:
    for line in f:
        if line.strip() and not line.startswith('#') and '=' in line:
            k, v = line.strip().split('=', 1)
            os.environ[k] = v

from backend.pipeline import analyze_ticker

tickers = ['GOOGL','META','ASML','MC.PA']
for t in tickers:
    try:
        r = analyze_ticker(t, output_base='analyses')
        print(f'{t}: {r.decision} {r.scoring.total}/40')
    except Exception as e:
        print(f'{t}: ERROR {e}')
