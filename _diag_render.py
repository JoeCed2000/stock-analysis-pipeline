#!/usr/bin/env python3
"""Diagnostic: check Render API reachability."""
import requests, os, json
from pathlib import Path

env_path = Path('/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline/.env')
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

RENDER_BASE = os.getenv('RENDER_API_URL', 'https://stock-analysis-api-tdtj.onrender.com')
print(f'RENDER_BASE={RENDER_BASE}')

# Test /api/analyses
resp = requests.get(f'{RENDER_BASE}/api/analyses', timeout=30)
print(f'/api/analyses status={resp.status_code}')
data = resp.json()
print(f'analyses count={len(data.get("analyses", []))}')
for a in data.get('analyses', [])[:3]:
    print(f'  dir={a.get("directory","?")} stage={a.get("stage","?")}')

# Test a specific dossier status
resp2 = requests.get(f'{RENDER_BASE}/api/dossier/TSLA/status', timeout=30)
print(f'/api/dossier/TSLA/status = {resp2.status_code}')
print(json.dumps(resp2.json(), indent=2)[:500])
