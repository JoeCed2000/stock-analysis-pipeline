#!/bin/bash
# audit_http_imports.sh — Verify httpx migration completeness
# Run from project root after any bulk library migration.
# Checks that every call site has the corresponding import.
#
# Usage: bash scripts/audit_http_imports.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'
errors=0
checked=0

echo "=== httpx Import Audit ==="
echo ""

# ── Check 1: Every http.get/post call has a corresponding import ──
echo "--- Check 1: http.* calls vs imports ---"
while IFS= read -r line; do
    file=$(echo "$line" | cut -d: -f1)
    [ -z "$file" ] && continue
    
    # Skip http_client.py itself (it defines http)
    [[ "$file" == *"http_client.py" ]] && continue
    # Skip test files (they import differently)
    [[ "$file" == *"test_"* ]] && continue
    # Skip .venv
    [[ "$file" == *".venv"* ]] && continue
    
    checked=$((checked + 1))
    
    # Check if this file imports http (module-level or function-level)
    if grep -q "from backend.http_client import http" "$file"; then
        echo -e "  ${GREEN}OK${NC}  $file"
    else
        echo -e "  ${RED}MISS${NC} $file — uses http.* but no 'from backend.http_client import http'"
        errors=$((errors + 1))
    fi
done < <(grep -rn "http\.\(get\|post\|put\|delete\|patch\)(" backend/ --include="*.py" | grep -v "^Binary" | cut -d: -f1 | sort -u)

# ── Check 2: No residual import requests (excluding http_client.py docstring) ──
echo ""
echo "--- Check 2: residual 'import requests' ---"
while IFS= read -r line; do
    file=$(echo "$line" | cut -d: -f1)
    content=$(echo "$line" | cut -d: -f2-)
    
    # Skip comments and docstrings
    if echo "$content" | grep -q "^\s*#"; then
        continue
    fi
    # Skip http_client.py (it's the migration target, references requests in comments)
    [[ "$file" == *"http_client.py" ]] && continue
    # Skip .venv
    [[ "$file" == *".venv"* ]] && continue
    # Skip test files that still reference requests for legacy reasons
    # [[ "$file" == *"test_"* ]] && continue
    
    echo -e "  ${RED}RESIDUAL${NC} $file: $content"
    errors=$((errors + 1))
done < <(grep -rn "import requests" backend/ --include="*.py" | grep -v "\.venv")

# ── Check 3: No requests.X exceptions remain (except in string context) ──
echo ""
echo "--- Check 3: residual 'requests.' exceptions ---"
while IFS= read -r line; do
    file=$(echo "$line" | cut -d: -f1)
    content=$(echo "$line" | cut -d: -f2-)
    
    # Skip comments
    if echo "$content" | grep -q "^\s*#"; then
        continue
    fi
    [[ "$file" == *".venv"* ]] && continue
    [[ "$file" == *"http_client.py" ]] && continue
    
    echo -e "  ${RED}RESIDUAL${NC} $file: $content"
    errors=$((errors + 1))
done < <(grep -rn "requests\.\(Timeout\|ConnectionError\|RequestException\|HTTPError\|get\|post\)" backend/ --include="*.py" | grep -v "\.venv" | grep -v "http_client.py")

# ── Check 4: No http2=True ──
echo ""
echo "--- Check 4: http2=True ---"
if grep -rn "http2\s*=\s*True" backend/ --include="*.py" | grep -qv "\.venv"; then
    echo -e "  ${RED}FOUND${NC} — http2=True detected"
    grep -rn "http2\s*=\s*True" backend/ --include="*.py" | grep -v "\.venv"
    errors=$((errors + 1))
else
    echo -e "  ${GREEN}OK${NC}"
fi

# ── Summary ──
echo ""
echo "=============================="
echo " Files checked : $checked"
echo " Errors found  : $errors"
echo "=============================="

if [ "$errors" -gt 0 ]; then
    echo -e "${RED}FAIL — $errors error(s) found${NC}"
    exit 1
else
    echo -e "${GREEN}PASS — all checks green${NC}"
    exit 0
fi
