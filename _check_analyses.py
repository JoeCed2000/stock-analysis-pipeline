#!/usr/bin/env python3
"""Quick check: what does /api/analyses return?"""
import requests, json, sys

try:
    r = requests.get("https://stock-analysis-api-tdtj.onrender.com/api/analyses", timeout=120)
    print(f"Status: {r.status_code}")
    data = r.json()
    print(f"Keys: {list(data.keys())}")
    analyses = data.get("analyses", [])
    print(f"Analysis count: {len(analyses)}")
    for a in analyses[:20]:
        print(json.dumps(a))
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
