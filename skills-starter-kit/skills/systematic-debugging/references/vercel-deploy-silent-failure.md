# Vercel Auto-Deploy Silent Failure — Case Study

**Date:** 2026-05-04
**Project:** stock-analysis-pipeline (frontend)
**Root cause:** Vercel GitHub integration stopped triggering auto-deploys without any notification

## Timeline

| Time (GMT) | Event | Evidence |
|------------|-------|----------|
| 15:43 | Commit a8c5295 pushed | Remove valid/invalid UI |
| 15:43:57 | Vercel deploys a8c5295 | Etag `96bccc6d...` |
| 15:50 | Commit d826230 pushed | Batch logging fix |
| 15:55 | Commit f7b65b6 pushed | Enrich /api/analyses |
| 17:00 | User reports still seeing "valid · invalid" | Browser screenshot |
| 17:08 | Commit fc050e6 pushed | Force redeploy attempt |
| 17:10 | Commit 0ec580a pushed | Cache bust with color change |
| 17:11 | Etag STILL `96bccc6d...` | Auto-deploy confirmed broken |

**4 pushes ignored. 0 notifications from Vercel. User sees code from 1.5h ago.**

## Diagnosis Checklist

When user reports seeing old code despite your recent pushes:

1. **Check Etag/last-modified on the deployed URL:**
   ```bash
   curl -sI "https://DEPLOYED_URL/" | grep -i 'etag\|last-modified'
   ```
2. **Compare with local git:**
   ```bash
   cd /path/to/project && git log --oneline -1
   ```
3. **Check JS bundle hash on deployment:**
   ```bash
   curl -s "https://DEPLOYED_URL/" | grep -o 'assets/index-[^"]*\.js'
   ```
4. **Check CDN cache headers:**
   ```bash
   curl -sI "https://DEPLOYED_URL/" | grep -i 'x-vercel-cache\|age'
   ```
   - `x-vercel-cache: HIT` + large `age` = CDN serving stale content
   - Fresh deployment should have `age: 0` or low seconds
5. **Search the remote JS for expected new content:**
   ```bash
   curl -s "JS_BUNDLE_URL" | grep -c 'NewIdentifier'
   ```
   - `0` = old code served, `>0` = new code deployed

## Symptoms

- User reports seeing UI that was already changed/removed
- Vision AI analysis of user's screenshot reports old text
- Your own `browser_navigate` shows new code (different CDN edge node)
- `git push` succeeds but CDN Etag never changes
- Vercel dashboard shows no recent deployments

## Fix

1. Go to Vercel dashboard → project → Deployments
2. Click Redeploy on the latest commit
3. Or re-link GitHub integration if disconnected
4. If the old project is hopelessly stuck (Etag unchanged after multiple manual redeploys): create a NEW Vercel project importing the same GitHub repo. The new project gets a fresh URL and fresh auto-deploy setup. Delete the old project after verifying the new one works.
5. After redeploy, verify Etag changed via: curl -sI DEPLOYED_URL | grep -i etag
6. Tell user to Ctrl+Shift+R (hard refresh)

Real-world example (2026-05-04): stock-analysis-pipeline old project (frontend-six-zeta-81.vercel.app) auto-deploy broke silently — 4 pushes ignored over 1.5h. Created new Vercel project → new URL (stock-analysis-pipeline.vercel.app) → auto-deploy working again. Cost: 90 min debugging time that would have been 5 min if Etag was checked after the first push.

## Prevention

- After every push to production frontend, wait 60s then verify Etag changed
- If Etag unchanged after 90s, assume auto-deploy failed → manual redeploy
- Don't trust `git push` alone for CDN-hosted frontends (Vercel, Netlify, Cloudflare Pages)
- Add deployment verification to post-push checklist

## Anti-Pattern: Dismissing User + Vision AI When They Agree

**Symptom:** user sends a screenshot showing old UI text. Vision AI confirms the old text. You check the deployed JS remotely, find no trace of the old text, and conclude both must be wrong — user cache, vision hallucination, etc.

**Reality:** the remote JS check hits a DIFFERENT CDN edge node than the user's browser. Your `curl` from WSL gets the new deployment; their browser in France gets the old one. When user AND vision AI both report the same thing, they're almost certainly right — the bug is in the deployment pipeline, not in their perception.

**Rule:** user report + vision AI agreement = deployment problem, not perception problem. Check Etag/last-modified BEFORE arguing.
