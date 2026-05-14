#!/bin/bash
# SA Operational Commands — stock-analysis-pipeline
# Project: /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline/

# ── RESTART (after any backend change) ──
alias sa-restart='fuser -k 8780/tcp 2>/dev/null; sleep 2; cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && nohup .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8780 --workers 4 > /tmp/sa_uvicorn.log 2>&1 &'

# ── REBUILD FRONTEND ──
alias sa-rebuild='cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline/frontend && npm run build && echo "✅ Rebuild done — RESTART SERVER NEXT (sa-restart)"'

# ── FULL REDEPLOY (rebuild + restart) ──
alias sa-redeploy='sa-rebuild && sleep 1 && sa-restart && sleep 4 && sa-verify'

# ── VERIFY DEPLOY ──
sa-verify() {
  echo "=== SA Deploy Verification ==="
  
  # 1. API health
  HTTP=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8780/stock-analysis/api/health)
  echo "API health: $HTTP"
  
  # 2. Frontend
  HTTP2=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8780/stock-analysis/)
  echo "Frontend: $HTTP2"
  
  # 3. Bundle
  BUNDLE=$(curl -s http://localhost:8780/stock-analysis/ | grep -oP 'index-[^"]+\.js')
  echo "Bundle: $BUNDLE"
  
  # 4. API_BASE in bundle
  API_BASE=$(curl -s "http://localhost:8780/stock-analysis/assets/$BUNDLE" | grep -oP '"/[a-z-]+/api[^"]*"')
  echo "API_BASE: $API_BASE"
  
  # 5. Cache-Control
  CACHE=$(curl -sI http://localhost:8780/stock-analysis/ | grep -i 'cache-control')
  echo "Cache: $CACHE"
  
  [[ "$HTTP" == "200" && "$HTTP2" == "200" && "$API_BASE" == '"/stock-analysis/api"' ]] && echo "✅ ALL OK" || echo "❌ FAIL"
}

# ── QUICK TEST (single ticker via API) ──
sa-test() {
  TICKER=${1:-NVDA}
  echo "=== Testing $TICKER ==="
  
  # Queue analysis
  JOB=$(curl -s -X POST "http://localhost:8780/stock-analysis/api/analyze/async?lang=en" \
    -H "Content-Type: application/json" \
    -d "{\"tickers\":[\"$TICKER\"]}")
  JOB_ID=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
  echo "Job ID: $JOB_ID"
  
  # Poll (max 30 attempts, 3s each = 90s)
  for i in $(seq 1 30); do
    STATUS=$(curl -s "http://localhost:8780/stock-analysis/api/analyze/job/$JOB_ID")
    STATE=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))")
    echo "  [$i] $STATE"
    [[ "$STATE" == "done" ]] && echo "✅ Analysis complete" && return 0
    [[ "$STATE" == "error" ]] && echo "❌ Analysis failed" && return 1
    sleep 3
  done
  echo "⏰ Timeout"
}

# ── PRODUCTION VERIFY ──
sa-verify-prod() {
  echo "=== SA Production Verification ==="
  HTTP=$(curl -s -o /dev/null -w '%{http_code}' https://sa.cedlabusa.net/stock-analysis/api/health)
  BUNDLE=$(curl -s https://sa.cedlabusa.net/stock-analysis/ | grep -oP 'index-[^"]+\.js')
  CFCACHE=$(curl -sI https://sa.cedlabusa.net/stock-analysis/ | grep -i 'cf-cache-status')
  echo "API: $HTTP | Bundle: $BUNDLE | CF: $CFCACHE"
  [[ "$HTTP" == "200" ]] && echo "✅ Prod OK" || echo "❌ Prod FAIL"
}
