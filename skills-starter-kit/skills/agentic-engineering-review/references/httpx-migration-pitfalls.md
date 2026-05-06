# httpx Migration Pitfalls (requests → httpx)

Pitfalls discovered during the stock-analysis-pipeline `requests → httpx.Client` migration (2026-05-05). 10 files converted, 20+ imports replaced.

## 1. Function-scope import forgotten

**Pattern:** A function uses `requests.get()` with a local `import requests`. The migration replaces the import with `from backend.http_client import http`, but the import line is accidentally deleted without adding a new one — or the function never had the import because a sibling function imported it first. The `http` name is unresolved, raises `NameError`, and is swallowed by a broad `except Exception`.

**Real case:** `_get_latest_10k_url()` and `extract_10k_sections()` in `sources_collector.py` had `import requests` removed but no replacement import. `http.get()` raised `NameError` → swallowed → 10-K extraction silently broken.

**Detection:**
```bash
grep -n "http\.\(get\|post\|put\|delete\)(" backend/*.py | while read line; do
  file=$(echo "$line" | cut -d: -f1)
  lineno=$(echo "$line" | cut -d: -f2)
  # Check if `from backend.http_client import http` exists in the function or at module level
done
```

**Fix:** Every function that calls `http.get/post/etc.` must have its own `from backend.http_client import http` if the module-level import doesn't exist.

## 2. `_source`/audit field not set on all return paths

**Pattern:** A data pipeline adds a `_source` field for traceability, but the field is only set on the main success path. Cache hits, fallback paths, and error-recovery paths return data without `_source`.

**Real case:** `get_stock_data()` in `sources_collector.py`:
- Cache hit: returned `cached` dict without `_source`  
- Pure yfinance fallback: set `_source = "yfinance"` but never assigned `result["_source"]`
- Finnhub/TwelveData path: set `_source` correctly, but the cache persisted the result before `_source` was added

**Fix:** Set the audit field at EVERY return point, not just the happy path. Add it to cached data on write AND on read.

## 3. `__import__("httpx").TimeoutException` workaround

**Pattern:** Instead of adding `import httpx` at module level, the code uses `__import__("httpx").TimeoutException` inline in an except clause. Works but is fragile, unreadable, and misses linter checks.

**Real case:** `translator.py` used `except __import__("httpx").TimeoutException:` instead of `except httpx.TimeoutException:`.

**Fix:** Add `import httpx` at module level, use `except httpx.TimeoutException:` directly.

## 4. `http2=True` without `h2` package

**Pattern:** `httpx.Client(http2=True)` requires `pip install httpx[h2]`. If only `httpx` is installed, `http2=True` raises `ImportError` at client creation time.

**Fix:** Either install `httpx[h2]` or set `http2=False`. For REST APIs (not streaming/gRPC), HTTP/2 offers negligible benefit.

## 5. Mock target migration: `requests.get` → `backend.http_client.http.get`

**Pattern:** Tests that mock `requests.get` break when the code switches to `httpx.Client.get`. The mock must target the actual callable being used.

**Options:**
- `patch("backend.http_client.http.get")` — mocks the shared client globally
- `patch("backend.sources_collector.http.get")` — only if the module imports it at module level

**Real case:** Circuit breaker tests mocked `requests.get` → all 3 tests passed silently because the real Finnhub API was called (and succeeded) instead of the mock.

**Fix:** Use `patch("backend.http_client.http.get", side_effect=mock_get)` and add `**kwargs` to mock signatures (httpx passes additional kwargs like `params`, `headers`).

## 6. Exception type migration

| requests | httpx |
|----------|-------|
| `requests.Timeout` | `httpx.TimeoutException` |
| `requests.ConnectionError` | `httpx.ConnectError` |
| `requests.RequestException` | `httpx.RequestError` |
| `requests.HTTPError` | `httpx.HTTPStatusError` |

**Pitfall:** `except requests.Timeout` silently becomes dead code after migration. httpx timeouts raise `httpx.TimeoutException`, which is NOT a subclass of `requests.Timeout`. The timeout is caught by a broader `except Exception` and retry logic is skipped.

## 7. Comments/docs still referencing HTTP/2 or requests

**Pattern:** After migration, docstrings and comments still claim "HTTP/2 enabled" or "uses requests". These stale comments mislead future readers.

**Fix:** Scan for `HTTP/2`, `requests.` in comments after migration.

## 8. Unused imports left behind

**Pattern:** During migration, `from backend.http_client import http` is added but the old `import requests` is removed. In some cases the new import is added in a code path that never uses it (e.g., `except ImportError: from backend.http_client import http; return None`).

**Real case:** `kimi_provider.py` imported `http` in an except block that immediately returns `None`.

**Fix:** Verify each `from backend.http_client import http` is followed by at least one `http.` call in the same scope.
