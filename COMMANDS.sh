#!/bin/bash
# SA Operational Commands — stock-analysis-pipeline
# Project: /home/ced/codex-projects/stock-analysis-pipeline/
#
# The old /mnt/c/Users/cedon/Documents/Codex/... paths are dead (repo moved to
# ~/codex-projects). Updated 2026-08-10.

SA_DIR=/home/ced/codex-projects/stock-analysis-pipeline

# ── RESTART (after any backend change) ──
# The backend is a systemd --user unit with Restart=always. The old alias did
# `fuser -k 8780/tcp` + `nohup uvicorn`: systemd instantly respawned the killed
# process, then the nohup one raced it for the port — the same crash-loop that
# got sa-backend.service disabled on 2026-06-12. Always go through systemd.
alias sa-restart='systemctl --user restart stock-pipeline.service && sleep 4 && systemctl --user is-active stock-pipeline.service'

# ── REBUILD FRONTEND ──
# The backend serves frontend/dist/ off disk, so a build IS the frontend deploy;
# no restart needed unless .py files changed.
alias sa-rebuild='cd "$SA_DIR/frontend" && npm run build && echo "✅ Rebuild done — frontend is live. sa-restart only if .py changed."'

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
  # Match either quoting style: the minifier rewrites "..." to `...`, which made
  # the old double-quote-only pattern report a false FAIL on a healthy deploy.
  API_BASE=$(curl -s "http://localhost:8780/stock-analysis/assets/$BUNDLE" \
    | grep -oP '["`\x27]/stock-analysis/api["`\x27]' | head -1)
  echo "API_BASE: $API_BASE"

  # 5. Cache-Control
  CACHE=$(curl -sI http://localhost:8780/stock-analysis/ | grep -i 'cache-control')
  echo "Cache: $CACHE"

  [[ "$HTTP" == "200" && "$HTTP2" == "200" && -n "$API_BASE" ]] && echo "✅ ALL OK" || echo "❌ FAIL"
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
