"""Daily backlog runner — processes all watchlist tickers."""
import os
import json

# Load .env
env_path = os.path.join(os.path.dirname(__file__), ".env")
with open(env_path) as f:
    for line in f:
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.strip().split("=", 1)
            os.environ[k] = v

from backend.pipeline import analyze_ticker

tickers = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "ASML", "MC.PA"]
results = {}
for t in tickers:
    try:
        r = analyze_ticker(t, output_base="analyses")
        conv = getattr(r.scoring, "conviction", "N/A") if hasattr(r, "scoring") else "N/A"
        results[t] = {
            "decision": r.decision,
            "score": r.scoring.total,
            "conviction": conv,
        }
        print(f"{t}: {r.decision} {r.scoring.total}/40 conviction={conv}")
    except Exception as e:
        results[t] = {"decision": "ERROR", "score": 0, "conviction": str(e)}
        print(f"{t}: ERROR {e}")

print("---SUMMARY_JSON---")
print(json.dumps(results))
