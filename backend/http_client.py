"""
Shared HTTP client with connection pooling.
Replaces ad-hoc `import requests` everywhere — single client, better perf.

Usage:
    from backend.http_client import http
    resp = http.get("https://api.example.com/data", timeout=10)
    data = resp.json()
"""

import httpx

# Connection pool: 20 max connections, 30s keep-alive
http = httpx.Client(
    timeout=httpx.Timeout(30.0, connect=10.0),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
    http2=False,
    headers={"User-Agent": "StockAnalysisPipeline/1.0"},
)
