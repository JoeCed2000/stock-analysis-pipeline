#!/usr/bin/env python3
"""Check what /api/analyses returns from Render."""
import requests, json

RENDER_BASE = "https://stock-analysis-api-tdtj.onrender.com"
resp = requests.get(f"{RENDER_BASE}/api/analyses", timeout=15)
print("Status:", resp.status_code)
data = resp.json()
print(json.dumps(data, indent=2)[:3000])
