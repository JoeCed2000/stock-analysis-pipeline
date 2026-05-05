#!/usr/bin/env bash
# audit_http_imports.sh — Post-migration audit for shared HTTP client consistency
# Usage: ./scripts/audit_http_imports.sh [project_root]
# Checks:
#   1. No residual `import requests` in backend/ (excluding http_client.py comment)
#   2. Every file using http.get/http.post has `from backend.http_client import http`
#   3. No `requests.Timeout` / `requests.RequestException` left behind
#   4. No `http2=True` left enabled

set -euo pipefail
ROOT="${1:-.}"
cd "$ROOT"

ERRORS=0
echo "=== Audit: HTTP Client Consistency ==="
echo ""

# ── Check 1: residual import requests ──
echo "1. Residual 'import requests' in backend/ ..."
RESIDUAL=$(grep -rn "^import requests\|^    import requests" backend/ --include="*.py" | grep -v "http_client.py" || true)
if [ -n "$RESIDUAL" ]; then
    echo "   FAIL — residual imports found:"
    echo "$RESIDUAL"
    ((ERRORS++))
else
    echo "   OK"
fi

# ── Check 2: http.get/post without import ──
echo ""
echo "2. http.get/post usage without import ..."
grep -rln "http\.\(get\|post\|put\|delete\|patch\)" backend/ --include="*.py" | while read file; do
    if ! grep -q "from backend.http_client import http" "$file" && ! grep -q "from backend.http_client import" "$file"; then
        echo "   FAIL — $file uses http.get/post but missing 'from backend.http_client import http'"
        exit 1
    fi
done
if [ $? -eq 0 ]; then
    echo "   OK"
else
    ((ERRORS++))
fi

# ── Check 3: residual requests exceptions ──
echo ""
echo "3. Residual 'requests.Timeout' / 'requests.RequestException' ..."
REQUESTS_EXC=$(grep -rn "requests\.\(Timeout\|RequestException\|ConnectionError\|HTTPError\)" backend/ --include="*.py" || true)
if [ -n "$REQUESTS_EXC" ]; then
    echo "   FAIL — residual requests exceptions found:"
    echo "$REQUESTS_EXC"
    ((ERRORS++))
else
    echo "   OK"
fi

# ── Check 4: http2=True still enabled ──
echo ""
echo "4. http2=True check ..."
HTTP2=$(grep -rn "http2\s*=\s*True" backend/ --include="*.py" || true)
if [ -n "$HTTP2" ]; then
    echo "   FAIL — http2=True found (requires 'h2' package):"
    echo "$HTTP2"
    ((ERRORS++))
else
    echo "   OK"
fi

# ── Check 5: __import__ hacks for external packages ──
echo ""
echo "5. __import__ hacks (non-stdlib) ..."
# Check for __import__ of non-stdlib packages (httpx, requests, etc.)
IMPORT_HACK=$(grep -rn '__import__("httpx")\|__import__("requests")\|__import__("urllib")' backend/ --include="*.py" || true)
if [ -n "$IMPORT_HACK" ]; then
    echo "   FAIL — __import__() hacks found:"
    echo "$IMPORT_HACK"
    ((ERRORS++))
else
    echo "   OK"
fi

# ── Summary ──
echo ""
echo "=== Audit Complete ==="
if [ "$ERRORS" -eq 0 ]; then
    echo "ALL CHECKS PASSED"
    exit 0
else
    echo "$ERRORS check(s) FAILED"
    exit 1
fi
