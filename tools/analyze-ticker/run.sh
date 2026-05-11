#!/bin/bash
# analyze-ticker — $1=ticker $2=quarter (optional)
set -euo pipefail

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: run.sh <ticker> [quarter]"
  echo "  ticker  — Stock symbol (AAPL, NVDA, MSFT)"
  echo "  quarter — YYYYQN format or 'latest' (default: latest)"
  echo ""
  echo "See tool.json for full spec and error codes."
  exit 0
fi

TICKER="${1:?Usage: run.sh <ticker> [quarter]}"
QUARTER="${2:-latest}"
API_BASE="${SA_API_BASE:-http://127.0.0.1:8780}"

# Check backend is up
if ! curl -s -o /dev/null -w "%{http_code}" "$API_BASE/api/health" 2>/dev/null | grep -q 200; then
  echo '{"error": "BACKEND_DOWN", "message": "Stock Analysis backend not running on :8780"}' >&2
  exit 2
fi

# Call analyze endpoint
HTTP_CODE=$(curl -s -w "%{http_code}" -o /tmp/sa_analyze_$$.json   "$API_BASE/api/analyze/$TICKER?quarter=$QUARTER&deep_dive=false"   --max-time 110 2>/dev/null)

if [ "$HTTP_CODE" = "200" ]; then
  cat /tmp/sa_analyze_$$.json
  rm -f /tmp/sa_analyze_$$.json
  exit 0
elif [ "$HTTP_CODE" = "404" ]; then
  echo '{"error": "TICKER_NOT_FOUND", "message": "No data for '"$TICKER"'"}' >&2
  rm -f /tmp/sa_analyze_$$.json
  exit 1
elif [ "$HTTP_CODE" = "429" ]; then
  echo '{"error": "RATE_LIMITED", "message": "Retry after 60s"}' >&2
  rm -f /tmp/sa_analyze_$$.json
  exit 1
else
  echo '{"error": "BACKEND_ERROR", "message": "HTTP '"$HTTP_CODE"'"}' >&2
  rm -f /tmp/sa_analyze_$$.json
  exit 2
fi
