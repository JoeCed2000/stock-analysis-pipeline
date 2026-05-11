#!/bin/bash
# generate-pdf — $1=ticker $2=quarter $3=lang
set -euo pipefail

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: run.sh <ticker> [quarter] [lang]"
  echo "  ticker  — Stock symbol (AAPL, NVDA)"
  echo "  quarter — YYYYQN format or 'latest' (default)"
  echo "  lang    — 'en' or 'ja' (default: en)"
  echo ""
  echo "Generates a deep-dive earnings PDF (~14-20 pages)."
  echo "See tool.json for full spec and error codes."
  exit 0
fi

TICKER="${1:?Usage: run.sh <ticker> [quarter] [lang]}"
QUARTER="${2:-latest}"
LANG="${3:-en}"
API_BASE="${SA_API_BASE:-http://127.0.0.1:8780}"

# Check backend is up
if ! curl -s -o /dev/null -w "%{http_code}" "$API_BASE/api/health" 2>/dev/null | grep -q 200; then
  echo '{"error": "BACKEND_DOWN", "message": "Stock Analysis backend not running on :8780"}' >&2
  exit 2
fi

# Trigger deep-dive generation (synchronous)
HTTP_CODE=$(curl -s -w "%{http_code}" -o /tmp/sa_pdf_$$.json   "$API_BASE/api/report/$TICKER/pdf?quarter=$QUARTER&lang=$LANG"   --max-time 290 2>/dev/null)

if [ "$HTTP_CODE" = "200" ]; then
  # Response is a PDF, check size
  PDF_SIZE=$(wc -c < /tmp/sa_pdf_$$.json)
  if [ "$PDF_SIZE" -gt 1000 ]; then
    echo "{"status": "ok", "ticker": "$TICKER", "quarter": "$QUARTER", "lang": "$LANG", "pdf_size_bytes": $PDF_SIZE}"
  else
    echo '{"error": "GENERATION_FAILED", "message": "PDF too small — likely generation error"}' >&2
    exit 1
  fi
  rm -f /tmp/sa_pdf_$$.json
  exit 0
elif [ "$HTTP_CODE" = "404" ]; then
  echo '{"error": "TICKER_NOT_FOUND", "message": "No transcript for '"$TICKER $QUARTER"'"}' >&2
  rm -f /tmp/sa_pdf_$$.json
  exit 1
else
  echo '{"error": "GENERATION_FAILED", "message": "HTTP '"$HTTP_CODE"'"}' >&2
  rm -f /tmp/sa_pdf_$$.json
  exit 1
fi
