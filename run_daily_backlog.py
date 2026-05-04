"""Daily backlog runner — executes analysis pipeline for all tickers."""
import os
import sys

# Load .env
env_path = os.path.join(os.path.dirname(__file__), ".env")
with open(env_path) as f:
    for line in f:
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.strip().split("=", 1)
            os.environ[k] = v

sys.path.insert(0, os.path.dirname(__file__))
from backend.pipeline import analyze_ticker

tickers = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "ASML", "MC.PA"]
for t in tickers:
    try:
        r = analyze_ticker(t, output_base="analyses")
        print(f"{t}: {r.decision} | {r.scoring.total}/40 | {r.conviction} | {r.company_name}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"{t}: ERROR {e}")
