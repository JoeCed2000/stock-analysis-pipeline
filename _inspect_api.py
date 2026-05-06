#!/usr/bin/env python3
"""Quick API inspection — one-shot, deletable."""
import requests, json

resp = requests.get("https://stock-analysis-api-tdtj.onrender.com/api/analyses", timeout=120)
print(f"Status: {resp.status_code}")
data = resp.json()

if isinstance(data, dict):
    print(f"Keys: {list(data.keys())}")
    if "analyses" in data:
        print(f"Count: {len(data['analyses'])}")
        for a in data["analyses"][:10]:
            print(f"  - {a.get('directory', 'N/A')}")
    else:
        print(json.dumps(data, indent=2)[:800])
elif isinstance(data, list):
    print(f"List length: {len(data)}")
    for item in data[:5]:
        print(f"  - {item}")
else:
    print(data)
