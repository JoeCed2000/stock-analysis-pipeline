# Vercel Deploy Silent Failure — Debugging Pattern

## Symptom
You pushed code to GitHub. Vercel is connected. But the deployed site still serves old code. The user sees old UI while you see new UI (different CDN edge). `curl` on the URL returns stale HTML.

## The Root Cause
Vercel's GitHub integration can disconnect silently — no error in the Vercel dashboard, no notification. GitHub webhook may fire but Vercel ignores it. Common after repo renames, permission changes, or token expiry.

## Detection Pattern (3 checks)

### Check 1: Compare Etags
```bash
# Before push
curl -sI "https://<project>.vercel.app/" | grep -i 'etag\|last-modified'

# After push + wait 60s
sleep 60
curl -sI "https://<project>.vercel.app/" | grep -i 'etag\|last-modified'
```
If Etag unchanged → Vercel did NOT redeploy.

### Check 2: Compare JS bundle hashes
```bash
# Remote HTML → extract JS filename
JS_FILE=$(curl -s "https://<project>.vercel.app/" | grep -o 'assets/index-[^"]*\.js')
echo "Remote JS: $JS_FILE"

# Local build → extract JS filename
LOCAL_JS=$(ls dist/assets/index-*.js)
echo "Local JS: $LOCAL_JS"
```
If hashes differ and remote hash hasn't changed after push → stale deployment.

### Check 3: Check deployment timestamp
```bash
curl -sI "https://<project>.vercel.app/" | grep 'last-modified'
# Compare with git log timestamp of the commit you pushed
git log --oneline -1 --format='%ai'
```
If last-modified is hours old while your push was minutes ago → broken auto-deploy.

## The Rebuild Trap

If you make a trivial change (comment, whitespace) and push, Vite may produce the SAME JS hash → Vercel CDN sees same Etag → serves cached version. 

**Fix:** Make a real content change that alters the module graph. Change a hex color, add a non-trivial string, modify an inline style value. Then push. The JS hash will change → CDN cache invalidates.

```bash
# Verify after push that new JS hash is DIFFERENT from old
OLD_JS="assets/index-QC4r4S0C.js"
curl -s "https://<project>.vercel.app/" | grep -o 'assets/index-[^"]*\.js'
# Should NOT be the same as OLD_JS
```

## The New Project Fallback

If redeploy in the same project fails repeatedly, create a **new Vercel project** importing the same GitHub repo. Vercel will give it a fresh domain (e.g., `project-name.vercel.app`). Then:

1. Configure env vars (VITE_API_URL, etc.) in the new project
2. Deploy
3. Verify the new URL works
4. Delete the old project to avoid confusion

## Post-Deploy Verification

After ANY deploy (manual or auto):
```bash
# 1. HTML references new JS
curl -s "https://<project>.vercel.app/" | grep -o 'assets/index-[^"]*\.js'

# 2. New JS contains expected changes
curl -s "https://<project>.vercel.app/<new-js-file>" | grep -c 'ExpectedNewIdentifier'

# 3. Browser smoke test
# Navigate, type input, verify rendered output has no old patterns
```

## Related
- `completion-verification-checklist` § Phase 4.5 — full deployment verification checklist
- `systematic-debugging` § Phase 0 — Render/serverless debugging
