# Render Debugging Case Study — stock-analysis-pipeline 2026-05-04

## The problem

User: "Building dossier trop long, répertoires manquants, md au lieu de PDF"

Agent applied 8 patches over 70 minutes. None worked because the root cause (Render free tier limitations) was never investigated first.

## Phase 0 in action

### Check 1: Is the code actually deployed?
- Pushed fix, waited 30s, tested → old behavior
- **Missed**: Render takes 60-90s to deploy. Health check returning 200 does NOT mean new code is live.
- **Fix**: Wait 90s after push, then verify with `curl | head` to check if the response matches expectations.

### Check 2: Did the disk survive?
- Each Render deploy WIPES the ephemeral filesystem
- Previous analysis directories (with 20+ files) gone after each push
- **Missed**: Assumed files persisted across deploys
- **Fix**: Always re-trigger analysis after a deploy. Never assume disk state.

### Check 3: API rate-limit check
- SEC EDGAR blocks Render's shared IP (403)
- Finnhub returns empty `peers: []`, `news: []` from Render
- **Missed**: Spent 20min debugging "why 10-K not downloading" before realizing it's IP-blocked
- **Fix**: Test API calls from lapced (unfiltered) vs Render (shared IP). If only Render fails → it's a rate-limit.

### Check 4: Background threads may be dead
- `generate_dossier_background()` spawned a daemon thread
- Thread silently failed on Render — no logs, no errors, just empty files
- **Missed**: Assumed "thread spawned = thread completed"
- **Fix**: All essential work → synchronous. Threads = cache/optimization only.

### Check 5: Deploy delay
- 10+ pushes in 70 minutes, each tested after ~30s
- Half the tests ran against OLD code
- **Fix**: 90s minimum wait after push. Verify with `git log` endpoint or version string.

### Check 6: Stale env vars
- `os.environ.setdefault("DOSSIER_UPLOAD_SECRET", ...)` — kept the WRONG secret from a previous session
- Upload to Render got 403 for 45 minutes before root cause found
- **Fix**: `os.environ[k] = v` (force override), never `setdefault()`

### Check 7: Multiple analysis directories
- Upload endpoint created dummy `NVDA_UPLOADED` directory
- Alphabetical sort: `UPLOADED` > `NVIDIA_Corp` → dummy dir was selected over real analysis
- Status showed 3 files (all in dummy dir) instead of 20 files (in real dir)
- **Fix**: Skip directories with "UPLOADED" in name. Prefer dirs with `report.md`.

## Cost of skipping Phase 0

| Bug | Time wasted | Phase 0 check that would have caught it |
|-----|-------------|----------------------------------------|
| Thread background muet | 30 min | Check 4 (background threads) |
| Cache in-memory bloquant | 20 min | Check 2 (disk state) |
| SEC EDGAR bloqué | 15 min | Check 3 (API rate-limit) |
| Secret upload 403 | 15 min | Check 6 (stale env vars) |
| Dummy dir shadowing | 10 min | Check 7 (multiple dirs) |
| Deploy delay false tests | 10 min | Check 1 + 5 (deploy verification) |
| **Total** | **~100 min** | **6/7 checks would have prevented bugs** |

## The Iron Law proven

> NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST

If Phase 0 had been run before the first patch, 6 of 7 bugs would have been caught at the hypothesis stage. Instead, 10 patches were applied blind — each revealing a new symptom of the same root cause (Render free tier limitations).
