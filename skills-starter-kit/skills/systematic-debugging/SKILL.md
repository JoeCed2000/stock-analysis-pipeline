---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior. 4-phase root cause investigation — NO fixes without understanding the problem first.
version: 1.1.0
author: Hermes Agent (adapted from obra/superpowers)
license: MIT
metadata:
  hermes:
    tags: [debugging, troubleshooting, problem-solving, root-cause, investigation]
    related_skills: [test-driven-development, writing-plans, subagent-driven-development]
---

# Systematic Debugging

## Overview

Random fixes waste time and create new bugs. Quick patches mask underlying issues.

**Core principle:** ALWAYS find root cause before attempting fixes. Symptom fixes are failure.

**Violating the letter of this process is violating the spirit of debugging.**

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Phase 1, you cannot propose fixes.

## Phase 0: Render/Serverless Debugging (CRITICAL)

**Before any debugging on Render, Vercel, or similar ephemeral platforms:**

1. **Is the code actually deployed?** — `curl -s "https://..." | head -20` to see if the response matches expectations. A health check returning 200 does NOT mean new code is live — Render serves old code during the build phase (1-2 min gap).
2. **Did the disk survive?** — Render wipes ephemeral storage on every deploy. Any files written to disk in the previous deploy are GONE.
3. **API rate-limit check** — Finnhub 429, SEC EDGAR 403 from shared Render IPs. If an API call works from lapced but not Render, it's an IP block — use cron from lapced.
4. **Background threads may be dead** — Render kills daemon threads when the server idles. Never assume a background thread completed.
5. **Deploy delay rule** — After pushing, wait 60-90 seconds before testing. If the new behavior isn't visible, check `git log --oneline -1` on the deployed instance to confirm which commit is running.
5b. **Simulate failure locally before deploying** — For Render-specific failures (yfinance blocked, SEC EDGAR blocked, Finnhub rate-limited), test the failure scenario on lapced FIRST. Monkeypatch the failing function to return `None`/`{}` and verify your fix works locally. A 7-commit deploy→test→fix→deploy loop wastes 40+ min. One local test saves all of it. Example: `get_yahoo_data = lambda ticker: None` → verify `_cache_get_yf` fallback kicks in.
6. **Stale env vars** — Hermes agent environments persist across sessions. `.env` values loaded with `os.environ.setdefault()` may be shadowed by 3-session-old stale vars. Use direct assignment.
7. **Multiple analysis directories** — Each deploy wipe + re-analysis creates new dirs. The status endpoint sorts by name; dummy dirs can shadow real ones. Always verify which directory is being read.
8. **Vercel/Netlify auto-deploy may be silently broken** — GitHub integration can disconnect without warning. After pushing, always verify the deployment picked up the new code: check `Etag`, `last-modified`, or the JS bundle hash. If the Etag hasn't changed after 2+ pushes, the auto-deploy is broken — trigger a manual redeploy in the Vercel dashboard.
9. **CDN cache hides the new deployment** — `x-vercel-cache: HIT` means the edge CDN is serving a cached version. Even if the deployment is correct, the user may see old content. Always check the `age` header (seconds since cached) and compare with the deployment timestamp. If `age` > deployment time, the CDN hasn't refreshed — force cache bust with a real content change (not just comments) or flush the CDN.

- `references/render-debugging-case-study.md` — 7 checks, 6 bugs prevented, 100 min saved.
**Vercel silent failure case study**: `references/vercel-deploy-silent-failure.md` — 4 pushes ignored, Etag stuck, user sees old code, diagnosis checklist.
**HTMX form serialization**: `references/htmx-name-attribute-required.md` — HTMX `hx-include` serializes by `name`, not `id`. Missing `name` → value silently dropped, backend receives empty parameter. Symptom: "sélectionné mais serveur dit rien sélectionné". Fix: add `name="param"`.

## When to Use

Use for ANY technical issue:
- Test failures
- Bugs in production
- Unexpected behavior
- Performance problems
- Build failures
- Integration issues

**Use this ESPECIALLY when:**
- Under time pressure (emergencies make guessing tempting)
- "Just one quick fix" seems obvious
- You've already tried multiple fixes
- Previous fix didn't work
- You don't fully understand the issue

**Don't skip when:**
- Issue seems simple (simple bugs have root causes too)
- You're in a hurry (rushing guarantees rework)
- Someone wants it fixed NOW (systematic is faster than thrashing)

## The Four Phases

You MUST complete each phase before proceeding to the next.

---

### Phase 0b: Migration Bulk Checklist (CRITICAL — avant toute migration >3 fichiers)

**Quand convertir un pattern dans >3 fichiers (ex: `requests` → `httpx`, `sync` → `async`, `print` → `logging`)** :

Avant de dire « fini », exécuter cette checklist mécanique :

- [ ] **Imports** : chaque fichier qui utilise le nouveau client (`http.get`, `http.post`) a `from backend.http_client import http` dans son scope. Vérifier avec `grep -rln "http\.\(get\|post\)" backend/ | while read f; do grep -q "from backend.http_client import http" "$f" || echo "MISSING: $f"; done`
- [ ] **Exceptions** : chaque `except requests.X` a été converti vers `httpx.Y` (`Timeout`→`TimeoutException`, `RequestException`→`RequestError`)
- [ ] **Pas de features ajoutées** : la migration ne doit pas introduire de configuration spéculative (http2, pooling custom, headers modifiés). Séparer migration et amélioration.
- [ ] **Résiduels** : `grep -rn "import requests" backend/` retourne 0 (hors commentaires)
- [ ] **Hacks** : `grep -rn '__import__' backend/` pour les packages externes retourne 0
- [ ] **Tests** : la suite de tests complète passe AVANT de déclarer la migration terminée
- [ ] **Audit script** : si un script d'audit existe (`scripts/audit_http_imports.sh`), le lancer

**Ne pas skipper** : chaque item coché manuellement ou par script. Pas de « j'ai vérifié mentalement ».

**Pitfall 2026-05-05** : migration `requests`→`httpx` sur 10 fichiers → 3 bugs (imports manquants, except périmé, http2 inutile). Coût : 20 min + 1 round Codex supplémentaire.

**BEFORE attempting ANY fix:**

### 1. Read Error Messages Carefully

- Don't skip past errors or warnings
- They often contain the exact solution
- Read stack traces completely
- Note line numbers, file paths, error codes
- **CRITICAL: Note HTTP status codes, specific error strings, timestamps — concrete data, not impressions**

**Action:** Use `read_file` on the relevant source files. Use `search_files` to find the error string in the codebase.

### 1b. API Integration: Inspect Real Responses Before Mocking (CRITICAL)

**WHEN debugging an API/SDK integration where tests use mocks:**

**BEFORE writing ANY mock or trusting existing ones, inspect the REAL API responses:**

1. **Read the SDK/API documentation** — not just method names, but data shapes, status transitions, edge cases
2. **Inspect the actual SDK objects** with `dir()`, `inspect.signature()`, `model_fields`
3. **Make a real API call** (or read real response logs) to see actual data structures
4. **Compare mock shapes against reality** — do mocks reproduce ThoughtContent vs TextContent? Nested objects? Status transitions?

**Red flags that mocks don't match reality:**
- `MagicMock(text="...")` when real API returns `[ThoughtContent, TextContent]`
- Mocking `status="completed"` without understanding it means "plan ready" in collaborative mode
- Mock provider returning `None` by default (Python `pass` → `None`), hiding `AttributeError`
- Test passes with 100+ tests but real API call fails immediately

**The rule:** Mocks that don't faithfully reproduce real response structures are **worse than no tests** — they create false confidence. A 100% passing test suite with unrealistic mocks means nothing in production.

**How to fix bad mocks:**
- Replace `MagicMock()` with objects that mirror real API types
- Simulate the exact status transitions the real API goes through
- Test both happy path AND the specific failure modes you've observed
- Add regression tests for every bug found in production that mocks missed

**Example (Gemini Interactions API):**
```python
# ❌ Bad mock — doesn't match reality
mock_interaction = MagicMock()
mock_interaction.status = "completed"
mock_interaction.outputs = [MagicMock(text="# Report")]

# ✅ Realistic mock — matches actual Gemini response
mock_thought = MagicMock()
mock_thought.text = None  # ThoughtContent has no .text
mock_plan = MagicMock()
mock_plan.text = "**Title:** Research Plan\n\n## Section 1..."
mock_interaction = MagicMock()
mock_interaction.status = "completed"
mock_interaction.outputs = [mock_thought, mock_plan]  # ThoughtContent THEN TextContent
```

### 1c. Separate Verified Facts from Hypotheses (MANDATORY)

**BEFORE proposing any cause, build a two-column table:**

| ✅ Verified Facts | ❓ Hypotheses (unconfirmed) |
|---|---|
| `pytest` shows 8 failures | Cause is rate limiting |
| Tests that POST are affected | `slowapi` misconfigured |
| `assert 429 == 201` in output | Rate limit counter not reset |

**Rule: Never state a hypothesis as a fact.** If the table has items in the right column, you do NOT know the root cause yet. Gather more evidence until the hypothesis column can be moved to verified.

**How to verify a hypothesis:**
- Check HTTP status codes in the actual response (`response.status_code`)
- Read the error message body, not just the exception type
- Add temporary logging/instrumentation
- Isolate the component and test it independently

**The user's golden rule applies here:** *"Un fait saillant n'est pas forcément la cause racine."* A conspicuous fact (e.g., "the limiter was just added") is not automatically the root cause.

### 1d. Frontend Component Contract — Read Before Patching (CRITICAL)

**WHEN debugging frontend code and considering a patch that modifies props/arguments
passed to a child component, function, or hook:**

**BEFORE writing ANY patch:**
1. **Read the target component's source** — `read_file` on the child component file
2. **Identify its interface** — what props does it accept? TypeScript types? PropTypes? JSDoc?
3. **Verify your proposed props exist** — does the component actually accept `onEdit`, `onDelete`, `onSubmit`?
4. **If the prop doesn't exist** → the fix belongs in the child component (add the prop handler there), NOT in the parent
5. **If you're patching the child** → read ALL parents that call it to ensure the new prop is passed everywhere

**Red flag:** "I'll just add the prop and see if it works" → **STOP. Read the child first.**

**This is the #1 cause of React crashes during frontend debugging.** Patching props
on a component you haven't read is guaranteed breakage. A single unread prop causes
a white screen, HMR loop, and wasted debugging time.

### 1d0. Debug Endpoint Pattern — Inspect Internal State (CRITICAL)

**WHEN debugging a backend where data exists on disk (cache files, ephemeral storage) but the API returns `None` or empty:** add a temporary diagnostic endpoint that exposes the exact file paths, contents, and data flow state.

**Pattern:**
```python
@app.get("/api/debug/yf-cache/{ticker}")
async def debug_yf_cache(ticker: str):
    """Temp debug endpoint — shows cache file existence + key values."""
    from module import _cache_get_yf, _cache_get
    yf = _cache_get_yf(ticker)
    main = _cache_get(ticker)
    return {
        "yf_cache_exists": bool(yf),
        "yf_pe": yf.get("pe_current") if yf else None,
        "main_cache_exists": bool(main),
        "main_pe": main.get("pe_current") if main else None,
    }
```

**Why this beats log diving:**
- Shows the EXACT state at query time (not 3 minutes ago)
- Proves whether data was written to the right file
- Proves whether the read path finds the data
- Can be checked from anywhere with curl

**Workflow:** Add endpoint → push → curl it → see if data exists → if not, trace the write path → fix → verify.

**This pattern diagnosed 4 bugs in one session (stock-analysis-pipeline, 2026-05-04):** cache file at wrong path, local dict not persisted, container wipe, data popped from API response. Without debug endpoints, each would have taken 30+ min of log spelunking.

### 1d3. Silent Catch — Never Mute Errors (CRITICAL)

**WHEN writing any `try/catch` (JS) or `try/except` (Python) block:** NEVER use an empty catch body or a comment-only catch. A catch that swallows the error makes bugs invisible.

**Pattern observed (stock-analysis-pipeline, 2026-05-03→04):**
```javascript
// ❌ Silent catch — bug invisible, user sees "nothing happens"
try {
  const data = await uploadTickerFile(file);
  setItems(data.items || []);
} catch (e) {
  // silently ignore parse errors
}
```

When the API call fails (network, 500, wrong URL), the UI shows no change — no error, no feedback. User clicks and nothing happens. The bug only surfaces during browser testing, but even then, there's no console error to guide debugging.

**Fix:** always log the error at minimum:
```javascript
try {
  const data = await uploadTickerFile(file);
  setItems(data.items || []);
} catch (e) {
  console.error('Parse error:', e);  // ← makes bug visible
}
```

**Rule:** every catch block MUST either:
- `console.error(e)` / `logger.error(...)` the error
- Show user-facing error state (`setError(e.message)`)
- Re-throw the error
- OR have a comment explaining WHY the error is intentionally suppressed (rare, e.g., optional cleanup)

**Red flag:** `// silently ignore` or `// ignore` or `catch {}` — **immediate fix required.**

### 1d4. Data Silently Dropped by r.pop() / delete (CRITICAL)

**WHEN an API response is missing a field you KNOW exists in the model (e.g., `pe_current` is in the cache, in the Pydantic object, but not in the JSON response):** search for `r.pop()` or `del r[...]` in the API handler.

**Pattern observed (stock-analysis-pipeline, 2026-05-04):** `valuation` was populated with `pe_current: 39.76` by the pipeline, but the API response showed `valuation: {}`. Root cause: `r.pop("valuation", None)` in the response builder silently removed ALL valuation data. The PE ratio existed in the model AND the cache but was explicitly deleted before the response was sent.

**Diagnostic:** after `model_dump()`, log the dict keys before any popping:
```python
r = result.model_dump()
logger.info(f"Keys before pop: {list(r.keys())}")  # shows ALL fields
# ... pops happen here ...
logger.info(f"Keys after pop: {list(r.keys())}")   # shows what was removed
```

**Fix checklist when a field is missing from API response:**
1. ✅ Field exists in Pydantic model? → Check model definition
2. ✅ Field populated by pipeline? → Check `result.model_dump()` output
3. ❓ Field in API response? → **Search for `r.pop(f"field") or `del r["field"]` in the handler**
4. ❓ Field renamed? → Search for dict key remapping (`r["new_name"] = r.pop("old_name")`)

**This is a silent data loss bug** — no error, no warning, the data just disappears between the pipeline and the client.

### 1d5. Local Dict Modified But Never Persisted Back to Parent (CRITICAL)

**WHEN merging cached data into a parent dict and the merged values don't appear downstream:** check whether the local copy was reassigned back to the parent.

**Pattern observed (stock-analysis-pipeline, 2026-05-04):**
```python
# ❌ yf_fin_live is a LOCAL copy, modifications lost
yf_fin_cached = yf_cached.get("financials", {})
yf_fin_live = yf_data.get("financials", {})  # detached if key absent
for key in ["revenue_annual", "net_income"]:
    if yf_fin_live.get(key) is None and yf_fin_cached.get(key) is not None:
        yf_fin_live[key] = yf_fin_cached[key]  # modifies LOCAL copy only
# yf_data["financials"] STILL has None values!

# ✅ Always persist back to parent
yf_data["financials"] = yf_fin_live  # ← THIS LINE IS MANDATORY
```

**Why it's insidious:** Python's `dict.get()` returns a reference if the key EXISTS, but a fresh empty dict if the key is ABSENT. The fresh dict has no connection to the parent. Modifications silently succeed on the local copy but never reach the parent.

**Red flag:** PE ratio shows up (merged at top level: `yf_data["pe_current"] = ...`) but Revenue/Net Income/FCF are None (merged into `yf_fin_live` which is a detached copy). Mixed results = check for dict detachment.

**Rule:** after modifying ANY local copy of a nested dict, always reassign: `parent["key"] = local_copy`. Don't assume `dict.get()` gave you a live reference.

### 1d6. Render Container Wipe — Enrich Cache Immediately, Not "Later" (CRITICAL)

**WHEN data is pushed to Render via a cron/local machine (yfinance, 10-K, transcripts):** never assume the pushed file will survive until the next read. Render free tier wipes the ephemeral filesystem on every container restart/cold start.

**Pattern observed (stock-analysis-pipeline, 2026-05-04):** yfinance data pushed to `_yf.json` via `/api/cache/financials`. Container restarted 30s later → file gone → PE/Revenue all None on next analysis.

**Fix: enrich the main cache IMMEDIATELY when data arrives:**
```python
# In the upload endpoint — enrich BOTH caches:
# 1. Save raw yfinance data to _yf.json (fallback for fresh get_stock_data calls)
# 2. Read {TICKER}.json (main stock cache, if exists)
# 3. Merge yfinance values where main cache has None
# 4. Write back enriched main cache
```

**Why dual cache + immediate enrichment:** `_yf.json` is the cold-start fallback. `{TICKER}.json` (enriched) is the hot path. If the container restarts and both are wiped, the next analysis recreates `{TICKER}.json` with Finnhub data, the cron repushes yfinance and enriches it immediately — no "wait for next read" gap.

**Rule:** for any data pushed from an external source to a Render endpoint, the endpoint MUST immediately merge it into the application's working cache. Never defer to "the next time someone reads it" — the filesystem may not survive that long.

**WHEN constructing download URLs in a frontend that uses Vite proxy (`API_BASE = '/api'`):** never prepend `/api/` to the URL path. `API_BASE` already contains the prefix.

```javascript
// ❌ Double prefix — /api/api/analyze/NVDA/download → 404 JSON
export function getTickerDownloadUrl(ticker) {
  return `${API_BASE}/api/analyze/${ticker}/download`;
}

// ✅ Correct — /api/analyze/NVDA/download → proxy → backend
export function getTickerDownloadUrl(ticker) {
  return `${API_BASE}/analyze/${ticker}/download`;
}
```

**Symptom:** user clicks download, gets `download.json` instead of `.zip`. Browser saves a JSON error response with the default filename "download".

**Diagnostic:** `document.querySelector('a[download]')?.href` in browser_console — look for doubled `/api/api/`.

**Common in:** any URL construction function that concatenates `API_BASE` + path. Check ALL such functions, not just the one being debugged.

### 1d2. Spinner/Loading State Not Visible — Placement & Cache Debugging (CRITICAL)

**WHEN user says "I don't see the spinner/loading indicator" after you added one:**

This is a TWO-LAYER problem: (1) is the code being served? (2) is the spinner placed where the user looks?

**Layer 1 — Cache poison (always check first):**
- NTFS + Vite: file watcher silently fails on `/mnt/c/...`, HMR never triggers
- Aggressive browser cache on localhost dev servers
- Use `fetch('/src/ChangedFile.jsx').then(r => r.text()).then(t => t.includes('NewIdentifier'))` in browser_console
- If false → restart Vite + tell user Ctrl+Shift+R
- See also: vite-cors-proxy § NTFS Cache Poison, systematic-debugging §1i

**Layer 2 — Placement (the real UX bug):**
- Spinners placed at **page level** (App.jsx, below all content) are invisible because the user's focus is on the form/button they just clicked
- Spinners placed **inside a long component** may be below the fold
- **Rule:** the spinner MUST appear **immediately below the action button that triggered loading**, not at page level
- In React: add `{loading && <Spinner />}` directly in the component that owns the button (e.g., TickerInput.jsx), not in the parent App.jsx
- The Analyze button should also change to `"⏳ Running..."` and become disabled

**Anti-pattern:** putting spinner in App.jsx (page root) and expecting user to scroll down past the form to see it.
**Correct:** spinner in TickerInput.jsx, right after `</form>`, with dark background container + border to make it visually distinct.

### 1e. Browser Snapshot Timeout — Fallback to browser_vision (CRITICAL)

**WHEN `browser_snapshot(full=true)` times out (30s+) on a complex React page:**

**DO NOT retry `browser_snapshot` — it will timeout again.** The page is likely too heavy for the snapshot engine (large DOM, many elements, slow rendering).

**Fallback pattern:**
1. `browser_vision(question="What does the page show? Are there errors?")` — vision works even when snapshot times out
2. `browser_console()` — check for JS errors while you're there
3. Use the vision analysis to verify page content instead of snapshot text

**Observed 2026-05-03**: BatchActions page with many interactive elements (7 buttons, status text, complex state) caused `browser_snapshot` to timeout consistently. `browser_vision` returned complete analysis in <10s.

**Rule**: 1 snapshot timeout → switch to browser_vision + console. Never retry snapshot unchanged.

- Can you trigger it reliably?
- What are the exact steps?
- Does it happen every time?
- If not reproducible → gather more data, don't guess

**Action:** Use the `terminal` tool to run the failing test or trigger the bug:

```bash
# Run specific failing test
pytest tests/test_module.py::test_name -v

# Run with verbose output
pytest tests/test_module.py -v --tb=long
```

### 3. Check Recent Changes

- What changed that could cause this?
- Git diff, recent commits
- New dependencies, config changes

**Action:**

```bash
# Recent commits
git log --oneline -10

# Uncommitted changes
git diff

# Changes in specific file
git log -p --follow src/problematic_file.py | head -100
```

### 4. Gather Evidence in Multi-Component Systems

**WHEN system has multiple components (API → service → database, CI → build → deploy):**

**BEFORE proposing fixes, add diagnostic instrumentation:**

For EACH component boundary:
- Log what data enters the component
- Log what data exits the component
- Verify environment/config propagation
- Check state at each layer

Run once to gather evidence showing WHERE it breaks.
### 1h. Variable Shadowing in Report/Loop Code (CRITICAL)

**WHEN a function generates a report with both object references and loop variables:** never reuse a variable name that was assigned earlier in the function. Python's scoping rules mean the loop variable **overwrites** the object reference.

[... snip, see references/js-formdata-blob-vs-file.md for similar from JS side ...]

**Red flag:** `AttributeError: 'float' object has no attribute 'X'` inside a loop → check for variable shadowing immediately.

**ALL of these mean: STOP. Return to Phase 1.**

**If 3+ fixes failed:** Question the architecture (Phase 4 step 5).
4. **Check backend logs** — `terminal("tail -50 <logfile>")` for silent errors, 500s, tracebacks
5. **Check browser console** — `browser_console()` for JS errors, failed API calls, warnings

### 6b. Parallel Visual UAT Pattern (Multi-Page / Multi-View)

**WHEN verifying 3+ pages, routes, or independent views after a frontend change:**

Spawn parallel sub-agents — each checks ONE page. The orchestrator (you) collects results.

```python
delegate_task(tasks=[
    {
        "goal": "Visual UAT: Dashboard home page at http://localhost:PORT",
        "context": "Navigate to the dashboard home page. Take a full snapshot. Check browser_console for errors. Verify KPIs, tables, and navigation render correctly. Report: PASS (all OK) or FAIL with specific errors.",
        "toolsets": ["browser"]
    },
    {
        "goal": "Visual UAT: Settings/Config page at http://localhost:PORT/settings",
        "context": "Navigate to the settings page. Full snapshot. Console check. Verify forms, toggles, save buttons work. Report PASS/FAIL with details.",
        "toolsets": ["browser"]
    },
    {
        "goal": "Visual UAT: Check backend logs for silent errors",
        "context": "Run: tail -100 /path/to/logfile. Look for 500 errors, tracebacks, warnings. Report any anomalies found.",
        "toolsets": ["terminal"]
    }
])
```

**After parallel UAT:** if any agent reports FAIL, fix the issue and re-run only that page's check.
All agents must report PASS before the fix is declared complete.

**Anti-pattern:** *"Tests pass, it must work"* → **NO.** Tests don't catch CORS errors,
API contract mismatches, or missing props. Only a real browser load catches these.

**Rule:** `curl 200 ≠ UI fonctionnelle`. A page that returns 200 but renders a white
screen is BROKEN. Browser snapshot with empty content = BROKEN.

### 7. Verification Checklist (Frontend)

Before marking a frontend bug as resolved:
- [ ] `browser_navigate` → page loads without white screen
- [ ] `browser_console` → no uncaught JS errors, no failed API calls
- [ ] `browser_snapshot(full=true)` → expected content visible (text, tables, buttons)
- [ ] Backend logs checked → no 500s, tracebacks, or silent failures
- [ ] All visible features exercised (not just the fixed one)

---

## Red Flags — STOP and Follow Process

If you catch yourself thinking:
- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "Add multiple changes, run tests"
- "Skip the test, I'll manually verify"
- **"It's probably X, let me fix that"**
- **"It's failing because of X" (without verified evidence)**
- "I don't fully understand but this might work"
- "Pattern says X but I'll adapt it differently"
- "Here are the main problems: [lists fixes without investigation]"
- Proposing solutions before tracing data flow
- **"One more fix attempt" (when already tried 2+)**
- **Each fix reveals a new problem in a different place**
- **Asserting a root cause without checking HTTP codes, logs, or actual component behavior**
- **"Tests pass, the frontend must work"** — tests don't catch CORS, missing props, API contract mismatches
- **"curl returns 200, the page is up"** — a 200 with a white screen is BROKEN. Browser snapshot required.
- **Patching props on a component you haven't read** — guaranteed React crash
- **Backend endpoint works (curl 200), frontend must be fine** — the browser may show an OLD cached version of the component (Vite HMR on NTFS doesn't detect file changes). Always browser_snapshot after frontend changes — never trust curl alone.
- **I restarted Vite, it should be fine** — browser may still hold cached JS modules. Verify with fetch('/src/...') AND tell user to Ctrl+Shift+R.
- **Cards in grid look cramped with chart bars cut off, but grid column is wide enough** — card has `minWidth`/`maxWidth` but no `width: 100%` → shrink-to-fit. Also check SVG for missing `viewBox`.
- **URL with doubled /api/api/ prefix** — API_BASE already contains /api. Symptom: download returns JSON instead of ZIP. Check with document.querySelector('a[download]')?.href.
- **Modifying files in a project without confirming TARGET_PROJECT** — context compaction or cross-session handoff can mix references to multiple projects (AlphaRadar, stock-analysis, hedge-fund). Before ANY file modification, re-verify: which project are we working on RIGHT NOW? A `read_file` on the project's AGENTS.md header confirms the project name. NEVER assume the active project from context alone — compacted sessions blur project boundaries.
- **Context compaction hallucinates project state** — the summary may claim that file X was created when it was not. Never trust compaction claims about file existence. Always verify with find/search_files before acting on them.
- **User + vision AI say X, but remote check says Y** — when both the user's screenshot AND vision analysis agree on old/stale content, and your remote curl says otherwise, the deployment is split across CDN edge nodes. The user and vision AI are right — the bug is in the deployment pipeline, not their perception. Check Etag/last-modified before dismissing their report.
- **HTMX form element has `id` but no `name`** — `hx-include` serializes by `name`, not `id`. A `<select id="pp-project">` without `name="project"` sends nothing. Symptom: "Nothing selected" when something IS selected. Fix: add `name="<param>"`.

### 1i. Frontend Stale Cache — Code Written But User Doesn't See It

WHEN you have written code, committed it, restarted the server, but the user reports it still looks broken:

This is almost always a cache poison — the browser is serving stale code. Common causes:
- NTFS + Vite: Vite file watcher fails on /mnt/c/..., HMR never triggers
- Aggressive browser cache: localhost dev servers are cached aggressively
- Double cache: both Vite (module cache) and browser (HTTP cache) hold old versions

Diagnostic flow (in order, fastest first):

1. Verify what Vite is actually serving (browser_console):
   fetch('/src/components/ChangedFile.jsx').then(r => r.text()).then(t => t.includes('NewIdentifier'))
   false = Vite cache poison = restart Vite; true = code is live, user needs hard refresh

2. Check file on disk matches expectations (terminal):
   grep 'NewIdentifier' /path/to/frontend/src/file.jsx
   found = file correct, Vite not reloading = restart Vite
   not found = patch did not apply = re-patch

3. After Vite restart, verify again with fetch('/src/...')
   true = tell user: Ctrl+Shift+R (hard refresh ignores cache)

4. If still broken: open in private/incognito window (fresh cache context)
   Only then re-test with browser_navigate + browser_snapshot

Anti-pattern: restart Vite and assume it worked — browser may still hold cached JS. Always verify with fetch + tell user to hard-refresh.

See also: vite-cors-proxy skill, section NTFS Cache Poison.
See also: `free-deployment-vercel-render` skill → `references/slow-backend-timeout-pattern.md` (Vercel CDN verification + fetch timeout + backend timeout).

### 1j. CSS Grid Card Shrink + SVG Fixed Dimensions (CRITICAL)

**WHEN result cards in a CSS Grid appear cramped with chart bars cut off:** check TWO things simultaneously:
1. Does the card have `width: 100%`? Without it, `minmax(Npx, 1fr)` columns don't stretch cards — they shrink to content width.
2. Does the SVG have a `viewBox`? Without it, fixed `width={224}` never adapts to the card width.

Both must be fixed together — fixing only one gives a distorted layout.

Full diagnostic flow and fix: see `references/grid-card-shrink-svg-viewbox.md`.

### 1f. Dedup Failure: Dynamic Keys in Comparison (CRITICAL)

**WHEN a deduplication mechanism exists but STILL produces duplicate entries:** check whether the comparison key includes dynamic data (timestamps, counters, timers).

**Pattern observed (Gemini Cockpit):** `_append_step()` correctly deduplicated consecutive identical steps — but the step text included `[MM:SS]` timer. Every poll produced a "different" step because the timer changed, defeating the dedup.

**Fix:** separate the LIVE display value (with timer) from the STORED comparison key (without timer).
```python
# ❌ Break dedup
enriched = f"Processing... [{mins:02d}:{secs:02d}]"
job.steps_json = _append_step(steps, enriched)  # Timer makes every step unique

# ✅ Preserve dedup
job.current_step = f"Processing... [{mins:02d}:{secs:02d}]"  # Live display
job.steps_json = _append_step(steps, "Processing...")          # Storage key (no timer)
```

**Red flag:** dedup that "should work" but doesn't → check if any component of the comparison key varies on each call (timestamps, auto-increment IDs, random suffixes).

### 1g. Pydantic Type Mismatch from External APIs (CRITICAL)

**WHEN a Pydantic model receives data from an external API (yfinance, Finnhub, etc.):** never assume a field's type based on its name or intuition. Always inspect the actual data the API returns.

**Pattern observed (stock-analysis-pipeline):** `yfinance.info['earningsQuarterlyGrowth']` returns a **float** (0.945 = 94.5%), not a string. The Pydantic model had `guidance_official: Optional[str]`, causing `ValidationError`.

**Fix:** model the field as `Optional[float]` if the API returns a float, or convert in the data layer before passing to Pydantic.

**Checklist for every new external API field:**
1. Print `type(value)` for a real call before writing the model
2. If the value can be multiple types (float or str depending on ticker), use `Union[float, str]`
3. Add the real type to a pitfall doc for that API

## 🔴 Pitfall: Killing Working Sub-Agents

**Symptom:** Sub-agent (Codex, delegate_task) has been running 10+ min with repetitive output. You think it's looping → kill it. But it was running tests — each run re-displays diffs.

**Liveness check before kill:**
1. `process(action='poll')` → still running?
2. `ps -p <pid> -o %cpu` → CPU > 0%?
3. `process(action='log', limit=5)` → output changed in 60s?

Kill ONLY if ALL THREE = NO. Repetitive output ≠ stuck. Recovery: `git diff --stat` to salvage work.

### 1h. Variable Shadowing in Report/Loop Code (CRITICAL)

**WHEN a function generates a report with both object references and loop variables:** never reuse a variable name that was assigned earlier in the function. Python's scoping rules mean the loop variable **overwrites** the object reference.

**Pattern observed (stock-analysis-pipeline):**
```python
# ❌ val is both ValuationData AND a loop variable (float)
val = result.valuation  # ValuationData object
for label, val, src_id in financial_items:
    fmt(val.pe_current)  # AttributeError: 'float' object has no attribute 'pe_current'
```

**Fix:** use distinct names — `v` for the loop variable, keep `val` for the object.
```python
# ✅ Distinct names
valuation = result.valuation  # stays ValuationData throughout
for label, v, src_id in financial_items:
    fmt(valuation.pe_current)  # works
```

**Red flag:** `AttributeError: 'float' object has no attribute 'X'` inside a loop → check for variable shadowing immediately.

**ALL of these mean: STOP. Return to Phase 1.**

**If 3+ fixes failed:** Question the architecture (Phase 4 step 5).

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Issue is simple, don't need process" | Simple issues have root causes too. Process is fast for simple bugs. |
| "Emergency, no time for process" | Systematic debugging is FASTER than guess-and-check thrashing. |
| "Just try this first, then investigate" | First fix sets the pattern. Do it right from the start. |
| "I'll write test after confirming fix works" | Untested fixes don't stick. Test first proves it. |
| "Multiple fixes at once saves time" | Can't isolate what worked. Causes new bugs. |
| "Reference too long, I'll adapt the pattern" | Partial understanding guarantees bugs. Read it completely. |
| "I see the problem, let me fix it" | Seeing symptoms ≠ understanding root cause. |
| "One more fix attempt" (after 2+ failures) | 3+ failures = architectural problem. Question the pattern, don't fix again. |

## Quick Reference

| Phase | Key Activities | Success Criteria |
|-------|---------------|------------------|
| **1. Root Cause** | Read errors, reproduce, check changes, gather evidence, trace data flow | Understand WHAT and WHY |
| **2. Pattern** | Find working examples, compare, identify differences | Know what's different |
| **3. Hypothesis** | Form theory, test minimally, one variable at a time | Confirmed or new hypothesis |
| **4. Implementation** | Create regression test, fix root cause, verify | Bug resolved, all tests pass |

## Hermes Agent Integration

### Investigation Tools

Use these Hermes tools during Phase 1:

- **`search_files`** — Find error strings, trace function calls, locate patterns
- **`read_file`** — Read source code with line numbers for precise analysis
- **`terminal`** — Run tests, check git history, reproduce bugs
- **`web_search`/`web_extract`** — Research error messages, library docs

### With delegate_task

For complex multi-component debugging, dispatch investigation subagents:

```python
delegate_task(
    goal="Investigate why [specific test/behavior] fails",
    context="""
    Follow systematic-debugging skill:
    1. Read the error message carefully
    2. Reproduce the issue
    3. Trace the data flow to find root cause
    4. Report findings — do NOT fix yet

    Error: [paste full error]
    File: [path to failing code]
    Test command: [exact command]
    """,
    toolsets=['terminal', 'file']
)
```

### With test-driven-development

When fixing bugs:
1. Write a test that reproduces the bug (RED)
2. Debug systematically to find root cause
3. Fix the root cause (GREEN)
4. The test proves the fix and prevents regression

## Real-World Impact

From debugging sessions:
- Systematic approach: 15-30 minutes to fix
- Random fixes approach: 2-3 hours of thrashing
- First-time fix rate: 95% vs 40%
- New bugs introduced: Near zero vs common

**No shortcuts. No guessing. Systematic always wins.**

## Reference: Common Bug Patterns

- `references/timestamp-dedup-pitfall.md` — Timestamps in dedup keys cause silent duplication (every entry appears unique because the timer changes)
- `references/api-mock-mismatch.md` — When mocks don't match real API response shapes (ThoughtContent vs TextContent, status transitions)
- `references/grid-card-shrink-svg-viewbox.md` — CSS Grid cards without `width:100%` shrink to content width; SVG without `viewBox` stays fixed-size. Both must be fixed together.
- `references/pydantic-property-serialization.md` — Pydantic `model_dump()` silently drops `@property` computed fields. Frontend shows 0/null. Fix: inject manually or use `@computed_field`.
- `references/pdf-dark-mode-colors.md` — PDF text unreadable because colors were designed for dark web backgrounds, not white paper. Full palette fix table.
- `references/htmx-name-attribute-required.md` — HTMX hx-include serializes by name not id
- `references/empty-proxy-env-library-crash.md` — Empty HTTPS_PROXY env var crashes httpx-based libraries
