"""
Shared HTTP client with connection pooling.
Replaces ad-hoc `import requests` everywhere — single client, better perf.

Usage:
    from backend.http_client import http
    resp = http.get("https://api.example.com/data", timeout=10)
    data = resp.json()
"""

import httpx

# Connection pool: reduced limits to prevent FD exhaustion under parallel analysis load.
# With 2+ concurrent ticker analyses each spawning Codex subprocesses, the default
# 20 keepalive + 50 max connections was pushing us toward the 1024 ulimit ceiling.
# Drop keepalive to 5 (enough for sequential API calls) and cap max at 20.
http = httpx.Client(
    timeout=httpx.Timeout(30.0, connect=10.0),
    limits=httpx.Limits(max_keepalive_connections=5, max_connections=20),
    http2=False,
    headers={"User-Agent": "StockAnalysisPipeline/1.0"},
)
