# Empty Proxy Env Vars → Library Crash

**Pitfall**: Some Python libraries (edgartools via httpxthrottlecache, and potentially any library using httpx) crash on startup when `HTTPS_PROXY` or `HTTP_PROXY` is set to an empty string `''`.

**Symptom**:
```
ValueError: Unknown scheme for proxy URL URL('')
  File ".../httpxthrottlecache/ratelimiter.py", line 21, in __init__
  File ".../httpx/_config.py", line 214, in __init__
```

**Root cause**: The env var exists but is empty. httpx interprets `''` as a proxy URL and fails to parse it.

**Why this happens**: WSL inherits proxy env vars from Windows. They're often set to empty strings by system configuration rather than being absent.

**Fix** (Python):
```python
import os
for var in ('HTTPS_PROXY', 'HTTP_PROXY', 'https_proxy', 'http_proxy', 'ALL_PROXY', 'all_proxy'):
    if os.environ.get(var, 'x') == '':
        del os.environ[var]
```

**Fix** (shell):
```bash
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
python -c "from edgar import Company; ..."
```

**Detection**: `env | grep -i proxy` — if any var shows `=` with no value, you'll hit this.

**Affected libraries**: edgartools, any library using `httpxthrottlecache`, potentially any httpx-based library that checks proxy env vars.

**Real case** (2026-05-05): edgartools crashed on first import in stock-analysis-pipeline because `HTTPS_PROXY=''` was inherited from the WSL environment. The library's `RateLimitingTransport` tried to create a proxy from the empty string.
