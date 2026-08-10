#!/bin/bash
# tunnel-sync.sh — OBSOLETE, DISABLED 2026-08-10. Do not run.
#
# This script belongs to a deployment that no longer exists:
#   - it opens an EPHEMERAL quick tunnel (*.trycloudflare.com); production uses
#     a NAMED tunnel run by the cloudflared-tunnel.service systemd --user unit
#   - it deploys the frontend to Vercel; production serves frontend/dist/
#     straight from the FastAPI backend, so `npm run build` IS the deploy
#   - PROJECT_DIR still points at /mnt/c/Users/cedon/... (repo moved to
#     ~/codex-projects long ago)
#
# Running it would overwrite frontend/.env.production with a throwaway
# trycloudflare URL and rebuild — which breaks the production bundle, since
# prod needs VITE_API_URL=/stock-analysis/api.
#
# Current procedure: see DEPLOY.md. Delete this file once you are sure nothing
# external calls it.

echo "tunnel-sync.sh is obsolete and disabled — see DEPLOY.md for the real deploy." >&2
exit 1

set -e
PROJECT_DIR="/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline"
FRONTEND_DIR="$PROJECT_DIR/frontend"
TUNNEL_LOG="/tmp/cf_tunnel_url.txt"
PID_FILE="/tmp/cf_tunnel.pid"

cd "$PROJECT_DIR"

# 1. Kill any existing cloudflared
if [ -f "$PID_FILE" ]; then
    kill $(cat "$PID_FILE") 2>/dev/null || true
    rm "$PID_FILE"
fi

# 2. Start cloudflared in background, capture URL
cloudflared tunnel --url http://localhost:8780 2>&1 | while IFS= read -r line; do
    echo "$line"
    # Extract URL: https://xxxx.trycloudflare.com
    if echo "$line" | grep -q 'trycloudflare.com'; then
        URL=$(echo "$line" | grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1)
        if [ -n "$URL" ]; then
            URL="${URL}/api"
            echo "$URL" > "$TUNNEL_LOG"
            echo "TUNNEL_URL=$URL"
        fi
    fi
done &

CLOUDFLARED_PID=$!
echo $CLOUDFLARED_PID > "$PID_FILE"

# 3. Wait for URL to appear
for i in $(seq 1 20); do
    if [ -f "$TUNNEL_LOG" ] && [ -s "$TUNNEL_LOG" ]; then
        break
    fi
    sleep 1
done

if [ ! -f "$TUNNEL_LOG" ] || [ ! -s "$TUNNEL_LOG" ]; then
    echo "ERROR: Tunnel URL not found after 20s"
    exit 1
fi

TUNNEL_URL=$(cat "$TUNNEL_LOG")
echo "Tunnel ready: $TUNNEL_URL"

# 4. Check if URL changed (skip rebuild if same)
CURRENT_URL=$(grep VITE_API_URL "$FRONTEND_DIR/.env.production" 2>/dev/null | cut -d= -f2 || echo "")
if [ "$CURRENT_URL" = "$TUNNEL_URL" ]; then
    echo "URL unchanged, skipping redeploy"
    exit 0
fi

# 5. Update .env.production
echo "VITE_API_URL=$TUNNEL_URL" > "$FRONTEND_DIR/.env.production"
echo "Updated .env.production → $TUNNEL_URL"

# 6. Rebuild frontend
cd "$FRONTEND_DIR"
echo "Building frontend..."
npm run build 2>&1 | tail -3

# 7. Deploy to Vercel
echo "Deploying to Vercel..."
DEPLOY_OUTPUT=$(npx vercel --prod --yes 2>&1)
echo "$DEPLOY_OUTPUT" | tail -5

# 8. Verify health
echo "Verifying..."
sleep 2
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$TUNNEL_URL/api/health" 2>/dev/null || echo "000")
echo "Health check: HTTP $HTTP_CODE"

echo ""
echo "✅ Tunnel synced: $TUNNEL_URL"
echo "   Frontend: https://stock-analysis-pipeline.vercel.app"
