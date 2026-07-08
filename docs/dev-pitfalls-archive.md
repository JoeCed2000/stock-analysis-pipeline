# SA Pipeline — Dev Pitfalls Archive (ex ced-sa-pipeline-dev skill)

> Déplacé le 2026-07-08 (curation Fable). Accumulation de pitfalls datés 2026-05 ; contient des sections dupliquées (appends répétés). Les conventions actives restent dans la skill `ced-sa-pipeline-dev`.

## Pitfalls

### 🔴 Data Source: key_financials > yf_data for PDF rendering (2026-05-30)

The Company Overview PDF renderer (`company_overview_pdf.py`) must check `overview['key_financials']` from Spark BEFORE falling back to `yf_data`. yfinance does NOT reliably return: `grossMargins`, `operatingMargins`, `freeCashflow`, `pegRatio`, `revenueGrowth`, `companyOfficers`, `fiftyTwoWeekLow/High`. The Spark prompt now includes all 12 fields in `key_financials`. Pattern: `value = fin.get('field') or yf_data.get('camelCase')`. Affected renderers: `_render_executive_snapshot()`, `_render_kpis()`, `_get_investor_summary()`. See `references/company-overview-pdf-pitfalls.md` for full 7-pitfall reference.

**Ced's correction:** *"Tu fais toujours les choses trop vite 😅 C'est ça la différence entre Codex et toi, il est lent parce qu'il teste tout et vérifie tout... Alors que tu fonces et tu laisses passer des trucs."*

**The pattern I fall into:**
1. Tests green → commit → push → declare "done"
2. Skip production verification (browser, deployment, restart gap)
3. Assume "committed = deployed = visible to client"

**The Codex pattern I should emulate:**
1. Tests green → commit → push
2. Restart backend → verify health shows new commit
3. Browser-verify the change on production URL
4. Check for backend restart gap (code on disk ≠ code in memory)
5. THEN declare done

**Real case (2026-05-29):** After the Nami-san prompt hardening (8 files, 30+ replacements), I was about to declare done after tests (432/434 pass) and commit. Ced's "Respire un bon coup" was the trigger — he wanted me to slow down and verify EVERYTHING, not just tests. I did restart the backend and verify health, but the pattern of rushing was the real issue.

**Trigger check before every "done" declaration:**
- "Did I verify this on the production URL?"
- "Did I restart the backend if Python files changed?"
- "Did I browser_navigate and see the change working?"
- "Would Ced say 'tu fonces' right now?"

If the answer to the last question is YES → STOP. Slow down. Verify. Then declare done.

### Spec/Wiki Out of Sync
The spec (`docs/spec-fonctionnelle.md`) and wiki (`docs/llm-wiki/projects/stock-analysis-pipeline.md`) must be updated after EVERY task. Missing updates create drift between documented state and actual code state.

### 🔴 Pre-Existing Test Failures Are Bugs — Fix Them (2026-05-29)

**Ced's correction:** *"C'est pas parce que c'est pre existant qu'il ne faut pas corriger !"*

Pre-existing test failures are NOT acceptable baseline noise. When working in a test file that has stale failures, fix ALL of them — not just the ones related to the current task. The test suite should be greener after every session.

**Stale test patterns and fixes:**
- Template section order drifted → update test to match current TEMPLATE_SECTION_KEYS
- Label format changed in mapper → update test assertions to match current output
- Domain normalization changed source labels → update test expectations
- Incomplete feature (JP placeholders defined but not wired) → relax test, note gap
- Impossible condition (canonical sources always have URLs) → update test invariant
- Forbidden placeholders in prompts → fix the prompts (replace with approved terms)

**Real case (2026-05-29):** 6 pre-existing failures in `test_earnings_pdf_template.py` — all fixed in commit `5ef5d88`. Template order, source labels, JP placeholders, render model validation, and prompt placeholders all updated.

Reference: `references/test-repair-stale-tests.md` — full methodology with 6 real case studies.

### Full Test Suite Timeout
`pytest tests/` on the full suite times out at 60s. Use the V2.x-focused subset for task verification:
```bash
pytest tests/spec_v27_*.py tests/test_v27_*.py -v
```

### Wiki Not in Git Repo
The wiki file lives at `codex-projects/docs/llm-wiki/` which is OUTSIDE the `stock-analysis-pipeline` git repo. Wiki updates cannot be committed — they're filesystem-only changes.

### 🔴 Python Bytecode Staleness — `__pycache__` Must Be Cleared After Edits

**Critical pitfall (2026-05-29):** After editing Python files with `patch` or `write_file`, the `__pycache__` directory may serve STALE compiled bytecode. The file on disk contains the new code, but `import` loads the old `.pyc`. This causes hours of confusion — code looks correct when read with `read_file`/`grep`, but runtime behavior is from the OLD version.

**Symptoms:**
- `grep`/`read_file` shows new code, but Python produces old output
- `inspect.getsource()` shows new code, but runtime behavior is old
- After multiple `patch` operations, behavior doesn't change

**Fix:**
```bash
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -name "*.pyc" -delete
```

**Real case:** After rewriting `_fallback_overview()` to remove forbidden markers (`LLM synthesis was unavailable`, `transcript-level validation`), Python continued to produce the OLD fallback text. File on disk was correct, `__pycache__` had stale bytecode. Clearing pycache fixed it immediately.

**Trigger:** After ANY `patch` or `write_file` on Python files, clear `__pycache__` before testing the changes.

### asyncio.run() Cannot Be Called From a Running Event Loop (2026-05-30)

**Critical bug:** `_generate_deep_dive_async()` is an async function called via `asyncio.run()` inside a thread. Inside it, calling `asyncio.run(get_company_overview(...))` fails with `"asyncio.run() cannot be called from a running event loop"` because you can't nest event loops.

**Fix:** Use `await` directly since the function is already async:
```python
# ❌ WRONG — nested event loop
company_overview = asyncio.run(get_company_overview(ticker, language=lang))

# ✅ CORRECT — await inside async function
company_overview = await get_company_overview(ticker, language=lang)
```

**Symptom:** Log shows `"Company overview skipped: asyncio.run() cannot be called from a running event loop"` — company overview is silently None, downstream uses fallback/deterministic data.

**Detection:** `grep "asyncio.run()" backend/main.py` — any call inside an async function is a bug.

### NTFS vs ext4 Codebase Copies — Edit the Running Copy (2026-05-30)

The SA pipeline exists in TWO locations:
- **NTFS:** `/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline/` (Windows-accessible)
- **ext4:** `/home/ced/codex-projects/stock-analysis-pipeline/` (where uvicorn ACTUALLY runs)

**The backend runs from ext4.** Check with: `readlink /proc/$(pgrep -f "uvicorn.*8780")/cwd`

**When editing:** always target the ext4 copy (`/home/ced/codex-projects/...`). Changes to NTFS don't affect the running backend. The two copies can diverge — verify with `diff` before editing.

**After editing:** the backend watchdog will auto-respawn the uvicorn process. Use `tb sa-check` to verify the restart picked up the new code. You don't need to manually kill/restart — the watchdog handles it.

### Hermes Profile Wrapper Gotchas — Use Absolute Paths
Under Hermes profiles, `~/.local/bin/` may contain wrappers that trigger profile switching or gateway restarts. **Always use absolute `/usr/bin/` or `/bin/` paths** for common commands in terminal calls:
- `df` → use `/bin/df` (wrapped by `~/.local/bin/df` which triggers gateway restart)
- `du` → use `/usr/bin/du`
- `find` → use `/usr/bin/find`
- `grep` → use `/usr/bin/grep`
- `sort` → use `/usr/bin/sort`
- `head` / `tail` → safe to use normally (not wrapped)

**Symptom if violated:** terminal commands time out with output like "🔄 Switching to DeepSeek First profile... ♻️ Restarting gateway..."

### Admin Page Performance
Without pagination, the admin page fetches all 525+ entries in one call and renders a giant table. The fix: add `offset` param to `read_recent_sqlite()` (SQL `OFFSET` clause), pass through the API endpoint, return `total` count, and add page controls (⏮ ◀ Page X of Y ▶ ⏭) to `AdminPage.jsx`. Page size: 50, auto-refresh stays on current page.

### React Component Size
`AnalysisCard.jsx` was 496 lines. Pattern for reduction: (a) extract pure helpers to an `AnalysisUtils.js` file (constants, scoring functions), (b) extract stateful side-effect logic to a custom hook (`useDossierPolling.js`), (c) hoist inline styles to module-level consts. Result: 275 lines (-45%). Target: keep components under 300 lines.

Reference: `references/prompt-hardening-nami-removal.md` — systematic 8-file cleanup methodology for removing Nami-san/Namiさん references from the entire pipeline (prompts, mapper, renderer, template, validators, i18n). Includes the prompt-validator circle pattern: when the validator blocks output that the prompt explicitly requests, fix the PROMPT first — that's the root cause.

### Nami/Internal Instruction Leaks in PDF Output

The `_section_continuation()` function in `pdf_renderer.py` generates default commentary for sections (Highlights, Operating Metrics, Cash Flow) when LLM-generated text is unavailable. The English version contained:
- `"For Nami-san: {company} positives and risks must tie back..."`
- `"Model example company figures are never reused for another ticker."`
- `"For Nami-san: revenue, gross profit..."`
And the Japanese version contained `"🧠 Namiさん向け補足"`.

**These are internal instructions, not client-facing content.** They must never appear in exported PDFs.

**🔴 Root cause (2026-05-29):** The LLM prompt (`prompts.py`) explicitly instructed the LLM to use `"For Nami-san:"`, `"Essential insight for Nami-san:"`, `"Nami-san takeaway"`, and equivalent Japanese labels. The validator blocked them — but the prompt was the SOURCE. Fix the prompt first, keep validators as safety nets. See `references/prompt-hardening-nami-removal.md` for the complete methodology.

Fix:
- Replace with professional, reusable default text across 8 files
- English: `"Key takeaways are derived from sourced metrics, transcript, press release, or company presentation."`, `"All figures are sourced; no data is invented."`
- Japanese: strip the Nami emoji/directive, use `投資家向け` / `機関投資家向け`
- System persona: `"writing an earnings deep-dive for Nami-san"` → `"writing an earnings deep-dive for an institutional fund manager"`
- Template defaults: `"Nami takeaway"` → `"Investor takeaway"`, `"Namiコメント"` → `"投資家コメント"`

### Missing-Data Language — Appropriate Taxonomy

See `references/missing-data-taxonomy.md` for the complete formal taxonomy, migration guide, audit script, and all files touched in the 2026-05-29 normalization pass.

### Replacement Pattern Ordering — Specific Before General

When applying multiple string replacements in sequence, always order from most specific (longest) to least specific (shortest). If a shorter pattern runs first, it partially consumes a longer pattern, making the longer pattern never match.

**Real bug (commit 1b3f874):** MISSING_DATA_REPLACEMENTS had "Not retrieved" before "Not retrieved from transcript". Result: "Not retrieved from transcript" was partially replaced to "Not disclosed from transcript" — the second pattern never fired.

Fix:
```python
# RIGHT ORDER — specific first
MISSING_DATA_REPLACEMENTS = [
    ("Not retrieved from transcript", "Not verified from reviewed sources"),
    ("Not retrieved", "Not disclosed"),
]
```

Same principle applies to audience patterns: "For Nami-san:" before "Nami-san" catch-all.

**Test rule:** always include a test with the longer pattern to catch ordering bugs (see test_normalizes_not_retrieved_from_transcript).

### Quality Gate System Integration

When adding new validation rules, add them to `backend/earnings_deep_dive/pre_render_validator.py`:
1. Add pattern to `FORBIDDEN_MARKERS` list
2. Run: `pytest tests/ -k pre_render -q`
3. The export pipeline blocks on any Critical/High validator findings

**Current FORBIDDEN_MARKERS (as of 2026-05-29):**
- `Not available`, `DATA NOT AVAILABLE`, `DONNÉE NON DISPONIBLE`
- `CRITICAL OVERRIDE`, `PRECISION INJECTION` (prompt directive leaks)
- `Not retrieved` (old placeholder wording)
- `Section unavailable` (old placeholder)
- `primary returned no content`, `fallback failed`, `provider returned empty` (debug leaks)

### Cache Envelope Trap — `_overview_cache_set` Wraps Data

`_overview_cache_set()` writes `{version, timestamp, data}` — the `data` key contains the actual overview dict. Direct `json.load()` on the cache file returns the envelope, not the flat data. Use `_overview_cache_get()` or `get_company_overview()` which unwrap automatically.

**Symptom:** Loading cache with `json.load()` gives only 3 keys (`version`, `timestamp`, `data`), then `CompanyOverview(**data)` fails with missing fields.

**Fix:** Always read through `get_company_overview()` (async) or `_overview_cache_get()` (sync). Never `json.load()` the cache file directly for validation.

### FORBIDDEN_MARKERS Contradiction Pattern

**Trigger:** Pre-render validator blocks PDFs with "For Nami-san:" markers in deep-dive sections.

**Root cause:** `audience_mode="nami_personal"` (the default) preserves "For Nami-san:" intentionally — generator's `_sanitize_for_audience()` skips replacement in nami mode. But FORBIDDEN_MARKERS always flags it. Two subsystems disagree on what's "forbidden."

**Fix:** Remove mode-specific labels ("For Nami-san:", "Namiさん向け") from FORBIDDEN_MARKERS. Add explanatory comment. The generator handles mode filtering; validator should only block universal internal leaks.

**Test update:** `test_nami_san_blocked` → `test_nami_san_allowed` (expects PASS). See `references/validator-forbidden-markers-contradiction.md`.

### Spark Fallback Chain Pattern (2026-05-30 — Spark is now PRIMARY)

**As of 2026-05-30:** Spark (`gpt-5.3-codex-spark`) is the DEFAULT model for all `_codex_chat()` calls. Ced's ChatGPT Plus subscription gives separate credit pools — the default model (gpt-5.5) may be quota-exhausted while Spark still has credits.

**Model configuration in `codex_provider.py`:**
```python
def _codex_chat(prompt, system="", max_tokens=1000, model="gpt-5.3-codex-spark"):
    # Uses Spark by default (Ced's Pro account has separate Spark credits)
    args = [CODEX_BIN, "exec", "--ephemeral", "--skip-git-repo-check", "--json"]
    if model:
        args.extend(["-m", model])
    ...
```

**🔴 Critical: the model name is `gpt-5.3-codex-spark`, NOT `gpt-5.3-spark`.** Using the wrong name causes Codex CLI to fall back to the default model silently. Verify with: `codex exec -m gpt-5.3-codex-spark "say hi"` — should show `model: gpt-5.3-codex-spark` in header.

**Rate limiting caveat:** Spark is fast for small prompts (~3s) but can exceed 60s for large prompts (~3000+ tokens, e.g. the company overview synthesis prompt). After multiple rapid calls, Spark may hang (4+ min with zero output). Wait 15-30 min between heavy pipeline runs.

**🔴 Quota dashboard interpretation — green bars = REMAINING, not used:** The Codex quota dashboard shows green progress bars. A bar at 100% means the quota is FULL (available), not exhausted. Do NOT interpret full green bars as "rate limited" — that's the opposite of what they mean. If `codex exec -m gpt-5.3-codex-spark "say hi"` works but a large prompt hangs, the issue is prompt size/API latency, not quota.

**Real case (2026-05-30):** Ced sent a screenshot showing all Spark quota bars at 100% green. I declared "rate-limited" and killed 3 running Spark processes that were about to complete. Ced called me out: "C'est pas juste que tu es impatient ??" — he was right. The processes were working; I lacked patience.

**Subprocess environment:** All Codex subprocesses MUST run with `HOME=/home/ced` (the real OS home, not the Hermes profile home). The `_codex_chat()` function handles this via `env["HOME"] = _REAL_HOME`.

### Fallback Data Quality — Must Pass Validator Gates

The deterministic fallback (`_fallback_overview()`) must produce data that passes
all 11 validator gates. Key requirements:
- Growth drivers: ≥40 chars each, ≥3 items, substantive (not "Revenue growth: +X%")
- Business risks: ≥40 chars each, ≥3 items, operational (not just market volatility)
- Moats: ≥40 chars each, ≥2 items, explained (not single words like "Brand")
- Segments: actual names extracted from description, not number words ("two")
- Competitors: at least 1 entry with competitor_name

Real case (NVDA 2026-05-30): fallback originally produced 37-char growth drivers
and 2 risks. Validator caught both (2 blocking errors). After hardening:
4 drivers (146-175 chars), 3 risks (211-245 chars) → 0 errors.

### Single try/except Kills Entire Pipeline Branch (2026-05-29)

When `generate_company_profile()` AND `generate_company_overview_pdf()` share one `try/except`, a `TypeError` in the first function silently kills the second. The old `md_to_pdf()`-generated stale PDF survives as fallback, masking the regression.

**Real case:** `market_cap = "$5.22T"` (string, not float) caused `TypeError` in `company_profile.py:102`. `generate_company_overview_pdf()` never called. New renderer's `NVDA_company_overview_investor_profile_*.pdf` never created. Download endpoint served stale `company_profile_NVDA.pdf` with `###` markdown and internal language.

**Fix:** Either split into two `try/except` blocks, or normalize all numeric inputs before passing to `generate_company_profile()`.

**Detection:** `find analyses/ -name "*_company_overview_investor_profile_*"` — if empty, the renderer silently failed.

### _parse_money() Suffix Coverage (2026-05-29)

`_parse_money()` only handled B/M/K single-char suffixes. Word suffixes ("trillion", "billion", "million") and T suffix were NOT handled. `$3.2 trillion` parsed as None. RULE 39 market cap consistency checks silently passed on trillion-scale contradictions.

**Fix:** Added word-suffix detection before single-char detection. Order: trillion → billion → million (most-specific first), then T → B → M → K.

### Company Overview Quality Gates — RULES 34-41 (2026-05-29)

8 new blocking validation rules added: content completeness (34), growth drivers quality (35), moat quality (36), business risks quality (37), CEO leadership & vision (38), numerical consistency (39), source quality (40), no markdown syntax (41). 90 spec tests. Full details in `references/company-overview-quality-gates-rules-34-41.md`.

See: `references/quality-gate-system.md` and `references/missing-data-taxonomy.md`
See: `references/quality-gate-system.md`
`except Exception: pass` in `async_dossier.py` and `edgar_extractor.py` masks real failures. Always add at minimum `logger.warning()` or `logger.debug()` before `pass`. Audit with: `grep -rn "except.*:" backend/*.py | grep -v logger`.

### Backup Files
`*.bak` files accumulate in `frontend/src/` from migration work. They're in `.gitignore` but should be deleted. Check: `find frontend/src/ -name '*.bak*'`.

### 🔴 Prompt-Validator Alignment: Catch-22 (2026-05-30)
When the prompt tells the LLM to write "X" but the validator blocks "X", the pipeline can never succeed. The validator is correct (X is bad output), but the prompt is the ROOT CAUSE. **Before adding any validator rule that blocks a phrase, grep the prompts for that phrase.** Fix: replace the phrasing in the prompt + add it to FORBIDDEN CLAIM PATTERNS. Reference: `references/prompt-validator-alignment.md`. Case: `prompts.py` line 852 said "write 'Data not available'" but validator RULE 16a blocked "Not available" — 3 NVDA runs failed before the prompt was fixed (commit `a81cbe5`).

### Frontend dist is NOT committed
`frontend/dist/` is in `.gitignore`. Build with `npm run build` from `frontend/`. The backend serves from `frontend/dist/` (not `backend/dist/`). After every frontend change, run the build.

### Interrupted Session Recovery — Commit Timeline Beats Stale Todos
When a provider/gateway crash interrupts an SA session, the preserved todo list may be stale. Recover state in this order before saying what remains:
1. `git log --oneline -15` on `kanban/spec-fonctionnelle-sa` to identify completed commits.
2. `git status --short` + `git diff --stat` to separate committed work from loose/uncommitted edits.
3. Compare against Ced's pasted transcript if available — treat it as primary evidence.
4. Report three buckets: **committed done**, **uncommitted/local diff**, **not verified/interrupted**.

Real case: after 404 + tests work, `6b42017 feat(ui): 404 page` was committed, while backend health/version timeout edits and `.bak` deletions were still local; the "tests" task had been interrupted by provider failures.

### Retroactive Task Creation — Dispatcher Waste (2026-05-27)

**Pattern:** Ced does work directly (commits code), then creates a Kanban task as an after-the-fact record, marks it `done`. The dispatcher later picks up the task and tries to run workers on already-completed work. Workers crash or waste cycles.

**Why it's a problem:**
- The task's workspace is empty (work already committed to main repo)
- Worker profiles (especially reviewer-qa) try to review code that's already merged
- If a provider is down, the dispatcher enters a crash storm (12 consecutive crashes on t_ece0378e)

**Fix:** When creating a task for already-completed work:
- Use `--max-retries 0` to prevent dispatcher from picking it up
- OR create the task directly in `archived` status
- OR use `hermes kanban create` with `--status archived` if the CLI supports it
- Add `SKIP_REVIEW` to the task body to prevent review dispatch

**Detection:** Task `created_at` ≈ `completed_at` AND `commit_time < created_at` → retroactive task.

**Real case (t_ece0378e, 2026-05-27):** Commit a375420 at 10:55, task created at 10:57, marked done at 10:57. Next day, dispatcher spawned 12 reviewer-qa workers that all crashed on legacy agent bridge outage.

### Historical Nami Feedback vs Live Feedback Inbox

When Ced asks whether Nami "sent remarks" or whether feedback is still pending, separate **historical evidence** from the **live inbox** — they are not the same thing.

Verification order:
1. Check **Kanban/history evidence** first:
   - task titles/bodies mentioning `Nami`, `feedback`, or `F1-F5`
   - prior review/implementation tasks like feedback-mapping or PDF-fix tasks
2. Check **repo evidence**:
   - `git log --grep='Nami\|feedback\|remarque'`
   - `tests_e2e/test_sa_recette.py` for the `F1-F5 — Nami Feedback Fixes` section
   - commits that explicitly mention Nami/PDF feedback
3. Check the **live inbox** separately:
   - query `/api/admin/feedback` with auth
   - treat `count=0` as "no current pending live feedback", NOT "Nami never sent remarks"
4. Treat ad-hoc files like `analyses/feedback.jsonl` cautiously:
   - they may contain test/demo entries (`AAPL`, `Good 0`, etc.)
   - do **not** treat them as canonical client feedback without corroboration

Interpretation:
- Historical Kanban tasks + tests + commits = strong proof that Nami feedback existed and was worked through.
- Empty `/api/admin/feedback` = no live pending feedback right now.
- A remaining blocked task may be unrelated to Nami's remarks; do not assume the last blocker is still a feedback item.

Real case (2026-05-28): the repo/board clearly showed historical F1-F5 feedback from Nami, while the live admin feedback endpoint returned `count=0`. The only remaining blocker was a valuation-context mixed-signal issue, not an unprocessed Nami remark.

### Deployment Truth Gate — Uncommitted Local Diff Is Not Deployed

When Ced asks whether SA is deployed, answer from evidence, not intuition. Run the deployment truth check before claiming "deployed" or "not deployed":
```bash
git rev-parse --short HEAD
git status --short
curl -sS --max-time 12 https://sa.cedlabusa.net/api/health
curl -sS --max-time 12 https://sa.cedlabusa.net/stock-analysis/api/health
```
Interpretation:
- If production health reports the same commit as local `HEAD` but `git status --short` has modified/deleted files, production is on the committed baseline only. The local diff is **not deployed**.
- A green `/api/health` only proves the server is alive and which commit it reports; it does not prove uncommitted changes, frontend dist freshness, or browser-visible behavior.
- If health/version report the new commit but the changed endpoint still behaves like old code, suspect stale running imports or multiple uvicorn processes. Do a clean restart, clear targeted `backend/**/__pycache__`, and re-test the changed endpoint — not just health.
- For frontend/client-facing changes, still run browser verification on `sa.cedlabusa.net` before saying done.

Real cases:
- Production and local `HEAD` both reported `6b42017`, but `backend/main.py`, `backend/models.py`, and frontend `.bak` deletions were uncommitted. Correct answer: prod was not stale vs `HEAD`, but the new fixes were not deployed.
- After commit `18b6e7d`, health/version reported the new commit but `/stock-analysis/api/analyze/async` still returned legacy 422 until stale uvicorn processes were killed, targeted pycache was cleared, and `uvicorn backend.main:app` was restarted cleanly.

Detailed proof recipe: `references/deployment-browser-proof-gate.md`.

### Admin Feedback History — Canonical Store vs Wrong Checkout

When the SA admin page shows **"No feedback yet"**, do not conclude that no feedback was ever posted. The admin UI is only as good as `GET /api/admin/feedback`, and that endpoint reads from the **current runtime checkout** under:
- `analyses/feedback_<TICKER>/index.json`
- sorted by `submitted_at` descending

Debug/verification order:
1. Verify the live endpoint result separately from historical evidence:
   - browser/admin fetch or authenticated API call to `/api/admin/feedback`
2. Inspect the store actually used by the running backend:
   - `backend/feedback_store.py` → `ANALYSES_DIR = Path(__file__).parent.parent / "analyses"`
   - list `analyses/feedback_*`
3. Compare alternate checkouts if the repo exists both on ext4 and NTFS (`/home/...` vs `/mnt/...`). Historical feedback may exist in one tree while production/runtime reads the other.
4. Only after that interpret the UI message.

Interpretation rules:
- `count=0` means **the runtime store is empty**, not necessarily that Nami never posted feedback.
- `feedback.jsonl` is legacy/ad-hoc and should not be treated as the admin source of truth unless the backend is explicitly changed.
- If dates are "missing", check whether entries exist first. `AdminPage.jsx` already renders `fb.submitted_at`; no entries means no rendered dates. The current display is also short-form (`JJ/MM HH:MM:SS`-style), not a full archival timestamp.
- If Ced asks whether feedback "didn't work", distinguish three cases explicitly:
  1. **Submit failed visibly** — backend returns non-OK and `FeedbackPanel.jsx` shows `❌ ...` to the user.
  2. **Submit worked but history is invisible** — the classic split-store case (`/home` vs `/mnt`) where the POST writes one checkout and admin reads another.
  3. **Feedback happened outside the app** — remarks were sent by message/orally and therefore never persisted in `feedback_<TICKER>/index.json`.
- Therefore, an empty admin inbox plus no stored `P1/P5/P7/P9` labels is stronger evidence of **wrong store or off-app feedback** than of a silent backend drop.

Reference: `references/admin-feedback-canonical-store.md`.

### Canonical Analyses Root — Eliminate /home vs /mnt Split-Brain

If the repo exists in both ext4 (`/home/...`) and NTFS (`/mnt/...`) checkouts, never assume the running backend and the inspected data tree are the same. In SA, hardcoded `Path(__file__).parent.parent / "analyses"` references created split-brain behavior: live feedback/history existed in one checkout while the admin API read the other.

Structural fix pattern:
- Introduce a single shared root variable: `SA_ANALYSES_DIR`
- Centralize path resolution in one helper module (for example `backend/storage_paths.py`)
- Route **all** analyses-adjacent readers/writers through that helper:
  - main runtime `ANALYSES_DIR`
  - admin feedback store
  - preload store
  - deep-dive/output-dir validation
- Set the same `SA_ANALYSES_DIR` in both the ext4 and NTFS `.env` files when both runtimes may be used
- Migrate any historical `feedback_<TICKER>/index.json` directories into the canonical store before concluding feedback is missing

Verification order:
1. Compare ext4 vs NTFS `analyses/` inventories before changing code.
2. Prove which checkout the live backend is serving (health/commit + running process cwd if needed).
3. After the fix, verify `/api/admin/feedback` through the browser on `sa.cedlabusa.net`, not just local curl.
4. Add targeted tests for path resolution and for endpoint/store coherence.

Interpretation rule:
- `feedback.jsonl` may exist as legacy/test data; the admin inbox source of truth is `analyses/feedback_<TICKER>/index.json` unless the backend is explicitly changed.
- Labels like `P1/P5/P7/P9` can be QA journey IDs from docs/tests and may **not** exist in stored feedback rows. Distinguish documentation labels from persisted client feedback.

Reference: `references/canonical-analyses-root.md`.

### Feedback Attachments Visible But Not Clickable

If feedback uploads are present on disk and listed in the UI, do **not** stop at "storage works". The missing piece is usually a serving path + link rendering gap.

Fix pattern:
- confirm canonical files under `SA_ANALYSES_DIR/feedback_<TICKER>/` and `index.json`
- add a dedicated backend route for feedback attachments
- validate path traversal defensively (`..`, absolute paths, basename-only)
- render attachment chips as anchors in **both** `FeedbackPage.jsx` and `AdminPage.jsx`
- add targeted backend tests for success + 404 cases
- build frontend, then verify the running backend actually loaded the new route before claiming the UI is fixed

Important interpretation rule:
- visible filenames are not proof of attachment usability
- green tests + built frontend are not deployment proof if the live backend still returns 404/403 until restart

Reference: `references/feedback-attachment-download-links.md`.

### Feedback PDF Link Opens JSON `Invalid API key` (403)

If clicking a feedback PDF opens JSON like `{"detail":"Invalid API key"}` instead of a PDF, the link route is still behind `_require_auth` even though browser users are opening a direct file URL.

Diagnosis sequence:
1. Reproduce with a direct GET to `/stock-analysis/api/feedback-file/<bucket>/<file>` (expect 403 + JSON before fix).
2. Confirm frontend link is correct (`target="_blank"`, encoded filename, right API base).
3. Inspect backend route declaration for `dependencies=[Depends(_require_auth)]`.

Fix pattern used in SA:
- make `/api/feedback-file/{bucket}/{filename:path}` **public read-only** for attachment downloads,
- keep path safety in `get_feedback_file_path` (basename/path traversal guard),
- do **not** expose or append API keys in attachment URLs.

Mandatory proof before claiming done:
- targeted backend tests still pass (`tests/test_feedback.py`),
- production browser check: feedback link opens native PDF viewer,
- production HTTP check: `200` + `Content-Type: application/pdf`.

### Seeking Alpha Cookie Import Format Trap (Desktop `Cookies.txt`)

When SA transcript access is tested from a desktop-exported `Cookies.txt`, do **not** assume Netscape `domain\tflag\tpath\tsecure\texpiry\tname\tvalue` column order. Some exports use `name\tvalue\tdomain\tpath\texpires...`.

Failure mode observed:
- parser assumes wrong columns
- malformed `Cookie` header is saved
- probe fails with `reason=request_error` and unicode/ascii encoding noise
- looks like auth/network failure but root cause is parser mapping

Safe pattern:
1. Inspect column shape first (count + first rows) before building the header.
2. Build cookie pairs from the correct `name/value` columns.
3. Filter rows to `.seekingalpha.com` / `seekingalpha.com` domains before save.
4. Save via `/api/admin/seeking-alpha/access`, then test via `/api/admin/seeking-alpha/test`.
5. Verify in browser admin panel (`#admin`) with "Test transcript access" and expect `Authenticated` + `HTTP 200`.

Reference: `references/seeking-alpha-cookie-import-format.md`.

### TestClient Host Pattern — Auth and Rate Limit Bypass

FastAPI `TestClient` uses synthetic client host `testclient`, not `127.0.0.1`/`localhost`. If local-only auth bypass or rate-limit bypass checks only localhost values, in-process tests can fail with 403 or shared rate-limit pollution while real localhost curl works.

Safe pattern for SA tests:
- Treat `testclient` as an in-process test host in auth and rate-limit code.
- Keep the bypass narrow and explicitly documented: production network traffic cannot originate from the synthetic `testclient` host.
- Revalidate with targeted tests before broader suites.

Real case: `/api/analyses` and `/api/batch/upload` returned 403 in tests because `_require_auth` bypassed localhost but not `testclient`; rate limits also keyed all TestClient requests to one synthetic host.

### Backward-Compatible API Request Models

If a smoke test or existing client sends a singular legacy field (`ticker`) while the current API expects plural (`tickers`), prefer a backward-compatible model validator when it does not weaken validation:
- Accept `{"ticker": "NVDA"}` by transforming it to `{"tickers": ["NVDA"]}`.
- Still reject empty requests with a clear validation error.
- Preserve the multi-ticker contract as the canonical shape.
- Add both model-level tests and endpoint-level tests that mock the job/thread boundary so the compatibility path is proven without launching a full analysis.

Real case: `/api/analyze/async` expected `tickers`, but smoke coverage used legacy `ticker`; adding a Pydantic `model_validator(mode="before")` fixed compatibility without changing the endpoint contract.

### UI Feature Vanished After "Unrelated" Frontend Commit

If Ced says "it worked this morning and now it's gone", treat it as a likely **recent commit regression** before blaming cache/deploy.

Fast verification sequence:
1. `git log --oneline -n 20` to locate recent frontend commits.
2. `git show <suspect_commit>` to confirm if routes/components/buttons were removed.
3. Verify production behavior in browser (`/stock-analysis/`, then target hash like `#feedback`) and confirm with console error check.
4. Restore from known-good commit when appropriate (targeted file checkout/cherry-pick), rebuild frontend, and re-test on production URL.

Interpretation rule:
- "API health green" does not prove feature parity; hash routes and UI entry points can still be missing.
- A commit that removes a component file (`D frontend/src/components/...`) is high-confidence evidence for user-visible disappearance.

### Ticker Input Parser Failures Can Look Like Tunnel Failures

When Ced reports that typing a ticker on `sa.cedlabusa.net` does "nothing", do not stop at Cloudflare Tunnel health. The ticker input debounces into `/api/batch/upload`; if that parser call is rate-limited or fails silently, the UI may show no chip/button even though the tunnel, static bundle, and analyze endpoint are healthy.

Debug sequence:
- Verify tunnel/backend/static with `tb sa-check`, but treat this as necessary-not-sufficient.
- Use browser production flow: type `NVDA`, confirm `NVDA TICKER` chip and `Analyze 1 ticker` button.
- Inspect browser network for `/stock-analysis/api/batch/upload` before analyzing.
- If curl upload returns 403 without `Origin`/`Referer`, that is expected auth protection; reproduce with browser same-origin headers or the browser tool.

Robust fix pattern:
- Rate-limit by `(client_ip, tier)`, not IP alone, so page/static/default traffic does not consume analyze/parser quotas.
- Keep debounce parser `/api/batch/upload` in a light/default tier unless abuse data requires otherwise.
- Add a frontend local fallback for simple tickers/ISINs and show a visible warning instead of only `console.error`.
- Add a regression test where many page loads from the same client do not block parser upload.

Detailed recipe: `references/ticker-input-parser-rate-limit.md`.

### Discovery Done ≠ User-Facing Fix Done (Closure Matrix Gate)

A completed discovery task (root-cause doc, reviewer approval, Kanban `done`) is **not** proof that user-visible fixes are shipped.

Before reporting "fixed", produce a closure matrix for each complaint:
- **Requested**: exact user complaint text (e.g., "TTM empty", "remove Feedback for Nami").
- **Code state**: implemented or not, with file-level proof.
- **Prod state**: verified in browser on `sa.cedlabusa.net` (not curl-only).
- **Deployment state**: committed/pushed and serving expected commit.
- **Kanban state**: requested task exists and is in correct status.

Rules:
1. If any column is missing, mark the item **partial** not done.
2. "Done 63" on board does not override live UI evidence.
3. Always separate historical evidence (past tasks/commits) from live inbox/runtime state.
4. For UX regressions, include both source-file proof and bundled-asset proof when relevant.

### Blocked Alert Reality Gate (real blocker vs residual board state)

When an alert says a project is "blocked", do not answer with a single global verdict. Classify each blocked task line-item with evidence.

Required sequence:
1. Inspect each blocked task row and capture `task_id`, dependency, and whether `completed_at` is set.
2. For any candidate real blocker, reproduce one concrete technical symptom now (focused function or endpoint check).
3. For any task marked blocked with `completed_at` present, classify it as probable residual/admin state unless contradictory live evidence appears.
4. Report split verdict per project/task:
   - **real blocker**: still reproducible now,
   - **residual blocker**: historical board state/no active execution block.

Rule: never label the whole alert "stale" or "not stale" without per-task classification.

### Status-Answer Integrity Gate ("Bientôt fini ?")

If Ced asks a short status question like "Bientôt fini ?", do not answer "c'est fini" unless all user asks are closed with tool-backed proof.

Required before a "finished" answer:
- each pending ask mapped to evidence (file diff, test/build output, browser proof),
- no remaining TODOs marked in-progress/pending for the same request set,
- production verification completed for user-facing behavior.

If not complete, answer with explicit partial state:
- what is done,
- what remains,
- next concrete step.

This prevents confidence drift where a conversational status reply outruns actual implementation state.

Use this gate especially for P0 SA regressions where users report "it still shows X" despite prior root-cause analysis.

### 🔴 Company Overview PDF — Open Inline, Not Download (2026-05-30)

The frontend `<a>` tag uses `target="_blank"` correctly, but the backend `FileResponse` defaults to `Content-Disposition: attachment` (forces download). The fix: set `content_disposition_type="inline"` for PDFs so the browser opens them in a new tab.

**Backend fix (`main.py` download endpoint):**
```python
# PDF → inline (open in new tab); MD/JSON → attachment (download)
disposition = "inline" if media_type == "application/pdf" else "attachment"
return FileResponse(
    file_path,
    media_type=media_type,
    filename=file_path.name,
    content_disposition_type=disposition,
)
```

**Verification:** `curl -sI` on the endpoint should show `content-disposition: inline; filename="..."` for PDFs.

**Ced's request:** "Je veux que ça ouvre le PDF dans une nouvelle fenêtre, pas que ça download" — the button should open the PDF in a new browser tab, not trigger a file save dialog.

### Company Overview Click + Markdown Polish Gate (new-window + professional render)

When Ced asks whether **Company Overview** opens correctly, do not infer from code alone. Prove behavior in the browser:
1. Navigate production page containing the Company Overview download/open action.
2. Click the control and verify a new tab/window behavior (`window.open(..., '_blank', 'noopener')` or equivalent observed runtime effect).
3. Validate response shape from browser context: status `200`, `Content-Type: application/pdf`, payload starts `%PDF`.
4. Run console check (`0` JS errors) after the interaction.

When Ced reports "bullets are misaligned" or raw markdown headings (`###`) visible in a PDF/report:
1. Use the **actual desktop screenshots** as primary evidence (not only source inspection).
2. Trace the full chain: markdown artifact → formatter (`_format_markdown`/paragraph helpers) → PDF renderer block used by that section.
3. Enforce normalization before render:
   - strip heading markers (`###`, `##`) where prose is expected,
   - normalize bullet markers/indentation consistently,
   - avoid mixed marker styles in the same section.
4. Re-generate the artifact and visually re-check the exact complained section.
5. Confirm `#feedback` points to the **new versioned attachment** (for example `*_v2.pdf`) so users don't reopen a stale cached file.

Rule: no "done" until both interaction proof (new window PDF) and visual polish proof (no raw markdown artifacts, aligned bullets) are captured.

### Peer Benchmark False-`N/A` Gate (merge overwrite bug)

If Ced says "il manque plein de trucs" on benchmark/context cards, treat this as a data-contract issue first, not a pure UI copy issue.

Mandatory sequence:
1. Verify source data exists (market snapshot values like `pe_ttm`).
2. Verify `/api/peer-benchmark/{ticker}` fields (`pe_ttm`, `pe_forward`, `peg_ratio`, summary statuses).
3. Verify user-visible labels in browser match the API result.
4. If source has values but endpoint returns unavailable, audit merge logic for null-overwrite (`None` replacing existing non-null).
5. Verify summary parsing handles contextual valuation labels (`premium`, `discount`, `at median`) so valid valuation evidence is not misreported as unavailable.
6. Generalization check: after fixing one ticker, validate at least two additional tickers through the same endpoint path.
7. Coverage check: confirm the subject ticker exists as a **root entry** in `backend/peer_universe.json` (being listed as someone else’s peer is not enough).
8. Contract check: compare `/api/peer-benchmark/{ticker}` with `/api/valuation/{ticker}`. If valuation payload does not expose `pe_forward`/`peg_ratio` or growth fields, peer labels will stay `N/A` even when collectors enrich internally.

Rule: every missing UI item must be mapped to a concrete API field + root cause statement before declaring remediation complete.
See also: `references/peer-benchmark-data-coverage.md`.

### Valuation Fallback Provenance Gate (Alpha → FMP → EODHD)

When reducing valuation `N/A` fields, implement and verify fallback as a **field-level chain** instead of a single-source overwrite.

Implementation rules:
1. Use ordered backfill per missing field: `alpha_vantage` → `fmp` → `eodhd`.
2. Fill only `None` fields (never overwrite existing populated values).
3. Capture the first provider that actually filled any field as `backfill_provider`.
4. Promote API provenance from that real provider (`source`) and mark `served_from=fallback` when applicable.

Validation rules:
1. Add targeted tests for:
   - no-overwrite behavior,
   - first-provider provenance retention,
   - fallback to later provider when earlier providers return empty.
2. Re-run same-origin production checks across a ticker basket (at least 3) and classify residual gaps explicitly:
   - **wiring bug** (field should be present but contract/merge lost it), or
   - **provider-unavailable** (all providers exhausted for that field).
3. Do not close with a generic "unknown" explanation; each remaining missing field must map to one of the two classes above.

This gate prevents false closure where fallback exists in code but unresolved `N/A` values are not classified with proof.

### WIKI-vs-Reality Verification Gate (2026-05-29)

When the WIKI.md claims fixes are DONE, always audit the actual production PDF before accepting the claim. The WIKI entry may be written optimistically before full end-to-end verification.

Verification sequence:
1. Find the latest PDF for the affected ticker (`analyses/*<TICKER>*/07_final_report/earnings_deep_dive.pdf`)
2. Extract text and count occurrences of the bug pattern
3. If count > 0, the fix is partial — not done
4. Cross-check: old pattern count AND new pattern count (e.g., "Not available" vs "Not disclosed")
5. Report fixed/partial/not-fixed explicitly

Real case: WIKI claimed all 7 screenshot defects fixed in commit 99cf747. PDF audit revealed `investor.nvidia.com` still present on pages 1 and 26, and 22 "Not available" occurrences vs only 6 "Not disclosed".

See: `references/screenshot-driven-pdf-qa-workflow.md`.

### Codex CLI HOME Path Resolution in Hermes Profiles

`backend/codex_provider.py` resolves `CODEX_BIN` via `os.path.expanduser("~/.hermes/node/bin/codex")`. Under Hermes profiles (deepseek-first, codex-first), `~` resolves to the **profile HOME** (e.g., `/home/ced/.hermes/profiles/deepseek-first/home/`), NOT the real user HOME. Result: `"Codex CLI not found at ..."` → `_codex_chat()` returns `None` → `_fallback_overview()` used for ALL LLM synthesis.

**Fix (tested 2026-05-29):**
```python
import pwd, shutil

_REAL_HOME = pwd.getpwuid(os.getuid()).pw_dir
_CODEX_CANDIDATES = [
    os.path.join(_REAL_HOME, ".hermes", "node", "bin", "codex"),  # Ced's canonical install
    shutil.which("codex"),                                           # PATH fallback
]
CODEX_BIN = None
for _c in _CODEX_CANDIDATES:
    if _c and os.path.exists(_c):
        CODEX_BIN = _c
        break
```

**Symptom:** Company Overview content is generic/fallback even though Codex CLI exists at `/home/ced/.hermes/node/bin/codex`. Check: `which codex` works, but `os.path.expanduser("~/.hermes/node/bin/codex")` resolves to profile-local fake home.

**Note:** Even with correct path resolution, Codex CLI may still fail with `401 Unauthorized` if the OpenAI API token is expired. The fallback data should always produce valid content for all fields as a safety net.

### PDF Renderer Pitfalls (2026-05-29, updated 2026-05-30)

**Multi-page table headers:** Tables use `splitByRow=1` but need `repeatRows=1` to repeat headers on page breaks. Without it, headers vanish on page 2+. Fix: `Table(data, colWidths=..., splitByRow=1, repeatRows=1, hAlign="LEFT")`.

**🔴 Data Source Priority — key_financials > yf_data (2026-05-30):** The Company Overview PDF renderer historically read metrics from `yf_data` (raw yfinance). But yfinance does NOT reliably return `grossMargins`, `operatingMargins`, `freeCashflow`, `pegRatio`, `revenueGrowth`, `companyOfficers`, `fiftyTwoWeekLow/High`. The Spark-generated `overview['key_financials']` has ALL these fields. Renderers MUST check `fin.get('field') or yf_data.get('camelCase')`. Affects: `_render_executive_snapshot()`, `_render_kpis()`, `_get_investor_summary()`. See: `references/company-overview-pdf-pitfalls.md`.

**Sentence split regex:** `business_description.split('.')` breaks on "U.S.", "Inc." → truncated bullets. Use `re.split(r'(?<=[.!?])\s+', text)` with `len > 3` filter. See: `references/company-overview-pdf-pitfalls.md` § Pitfall 6.

**🔴 Codex Spark hang pattern (2026-05-30):** Spark successfully completes ~1 call per session, then systematically hangs (0 bytes output, zombie). First-attempt timeout of 300s with early-kill if output file is still 0 bytes. DeepSeek V3 as API fallback. See: `references/company-overview-pdf-pitfalls.md` § Pitfall 7.

**Orphan section titles:** Section titles (`"section"` ParagraphStyle) need `keepWithNext=1` to prevent the title appearing at the bottom of a page with its table on the next page.

**Placeholder charts:** `_generate_metrics_chart()` shows "EPS data not available" / "Revenue data not available" placeholder text. §25 forbids placeholder charts. Fix: skip chart entirely if no data, and remove placeholder text from panels without data.

**FCF consistency check:** When checking FCF text vs metrics, use context-aware regex (`r'(?:free\s+cash\s+flow|FCF).{0,80}(\$[\d,.]+...)'`) — not all `$` amounts in Cash Flow are FCF (could be OCF or CapEx).

Reference: `references/renderer-bypass-validator-gap.md` — architectural gap where renderer-generated text skips validation; root cause analysis and mitigation strategy.

Reference: `references/prompt-hardening-nami-removal.md` — systematic 8-file cleanup methodology for Nami-san removal. Covers the prompt-validator circle pattern: when the validator blocks output the prompt explicitly requests, fix the PROMPT (root cause), not just the validator.

### Validator Severity Over-Classification — Format Rules Must NOT Block

When adding new validation rules to `pre_render_validator.py`, classify severity correctly:
- **`error`**: data fabrication, data corruption, internal leaks, factual contradictions
- **`warning`**: format issues (markdown syntax — the mapper handles conversion), editorial quality (near-duplicates), potential false positives (broad regex on legitimate labels)

**Real case (2026-05-29):** 7 rules were set to `error` instead of `warning`, causing ALL deep-dive PDFs to be blocked for 24+ hours (19-25 violations per analysis). The `raw_markdown_*` rules blocked on markdown pipe tables/headings/bullets — but the mapper (`_extract_markdown_table()`) parses these into structured data before the renderer generates PDFs. The validator was blocking the pipeline's NORMAL input format.

**Follow-up (2026-05-29, same session):** After downgrading to `warning`, the `raw_markdown_*` rules were still generating ~100 warnings per run — pure noise. They were **completely removed** (commit `0bdd0fd`) along with their test classes (TestRawMarkdownTable, TestRawMarkdownHeadings, TestRawMarkdownBullets). The mapper already handles markdown→structured conversion — the validator check was fully redundant. Warning count dropped from 131→108 (further reductions blocked by LLM variance and remaining content-quality rules).

**Detection:** If `validate_pre_render()` consistently blocks 15+ violations on healthy LLM output → audit severity classification. If a rule fires 10+ times per run and all instances are format-level (not data integrity), consider removal rather than downgrade — the mapper/renderer handles the conversion.

See: `references/validator-severity-classification.md` for the full downgrade protocol.
See: `references/prompt-metrics-field-name-leak.md` for the related field-name regurgitation pattern.

### Prompt Improvements Have Diminishing Returns on Format Warnings (2026-05-29)

When the validator produces ~100+ warnings per deep-dive run, prompt hardening for content quality (SEC labels, FCF consistency, capital efficiency, highlights dedup) will only affect ~10-15 of them. The bulk (~80-100) are `raw_markdown_*` — pipe tables, hash headings, star bullets — which are **inherent to the LLM's markdown output format** and unfixable via prompts.

**Evidence:** 4 prompt improvements applied to `prompts.py` (SEC source clarity, FCF value consistency, capital efficiency anti-NA, highlights dedup) had zero net impact (119 → 131 warnings, within LLM variance).

**Actual fix applied (same session):** Removed RULE 14 entirely (commit `0bdd0fd`) — the `raw_markdown_table`, `raw_markdown_headings`, `raw_markdown_bullets` rules were fully redundant because `_extract_markdown_table()` in the mapper already parses markdown into structured objects before the renderer generates PDFs. Warning count dropped from 131→108.

**Real fix options by impact:**
1. **Delete `raw_markdown_*` rules** ✅ DONE — mapper handles markdown→structured conversion. Warning count: -17 (net, LLM variance masks true reduction).
2. **Structured JSON output** — refactor the LLM to generate JSON sections instead of markdown. The renderer would format everything. ~2-3h effort, eliminates all remaining format warnings.
3. **Field-name sanitization in `_fmt_metrics()`** — replace internal field names (`operating_cash_flow`) with human labels before injecting into prompts. Would eliminate the intermittent `raw_provider_key` blocking errors. See `references/prompt-metrics-field-name-leak.md`.

**Rule:** Before investing time in prompt tuning, classify the warnings: format-level (removable rules) vs content-level (prompt-tunable). Only content-level warnings respond to prompt improvements. Format-level warnings need rule removal or architecture change.

### Validator Rule Pattern

See `references/validator-rule-pattern.md` for the complete pattern for adding pre-render validator rules. See `references/validator-rules-index.md` for the complete RULES 1-32 table.

Key convention: every `corrections.txt` defect that can be caught as a text/structural check on LLM output goes into `pre_render_validator.py` as a blocking (`severity="error"`) rule. Tests go in `tests/spec_v27_<feature>.py`. Non-regression: `pytest tests/spec_v27_*.py tests/test_v27_*.py -q`.

### Fix the Source, Not the Symptom (2026-05-29)

When the validator blocks generated text, check if the PROMPT is generating that text. Adding a validator gate is a symptom fix. Fixing the prompt so it doesn't generate forbidden patterns is the root cause fix.

**Real case:** FORBIDDEN_MARKERS blocked `"For Nami-san:"` in PDFs. Rather than just relying on the gate, the 30+ Nami-san references in `prompts.py` were replaced with professional neutral labels (`"Investor insight:"`, `"Key takeaway:"`, etc.). Validators stay as safety nets, not primary correction mechanisms.

See `references/nami-san-cleanup.md` for the full cleanup.

### FORBIDDEN_MARKERS Hardening (2026-05-29)

RULE 5 (FORBIDDEN_MARKERS) was upgraded from `severity="warning"` to `severity="error"` (BLOCKING). All internal leak patterns are now hard-fail. Markers include: "Not available", "CRITICAL OVERRIDE", "Model example", "For Nami-san:", "Namiさん向け".

When adding new markers: add to the `FORBIDDEN_MARKERS` list in `pre_render_validator.py`. All are substrings (no regex). The RULE 5 check iterates all sections and adds a `ValidationWarning(severity="error")` for each match.

### None vs none — Case Sensitivity Trap (2026-05-29)

RULE 30 (null artifacts) uses word-boundary regex to catch programming artifacts. "None" (Python) is case-SENSITIVE — English "none" is a valid word. Use separate regex lists for case-sensitive vs case-insensitive patterns:

```python
null_artifacts_case_sensitive = [(r'\bNone\b', 'None')]
null_artifacts_case_insensitive = [(r'\bnull\b', 'null'), (r'\bNaN\b', 'NaN'), ...]
```

**Current state (2026-05-29):** 356 V2.x tests, RULES 1-29.

### `_find_analysis_dirs` Glob Fragility

The glob pattern `*_TICKER_*` only matches directories like `NNNN_NVDA_YYYY`, NOT bare ticker directories (`NVDA`) or prefix-only directories (`NVDA_2026Q2`). When `run_analysis_parallel` creates directories named just `NVDA`, the download endpoint returns 404 even though the analysis exists.

**Fix:** Add fallback globs for exact ticker name and `{TICKER}*` patterns:
```python
dirs = sorted(ANALYSES_DIR.glob(f"*_{key}_*"), reverse=True)
exact = ANALYSES_DIR / key
if exact.is_dir() and exact not in dirs:
    dirs.append(exact)
for d in sorted(ANALYSES_DIR.glob(f"{key}*"), reverse=True):
    if d.is_dir() and d not in dirs:
        dirs.append(d)
```

### Company Overview Enhancement Pattern (4 touch-points)

When adding new sections to Company Overview, four places need updating: LLM prompt template, fallback function, Markdown renderer, and PDF converter. See `references/company-overview-enhancement-four-touch-points.md` for the full checklist and example.

### Post-Update Patch Verification (2026-05-29)

### Codex 401 vs Usage Limit — Different Errors, Different Fixes (2026-05-30)

When Codex CLI `exec` fails, the error message tells you exactly what's wrong:

| Error | Meaning | Fix |
|---|---|---|
| `401 Unauthorized: Missing bearer` | Auth token expired or missing | `codex login --device-auth` |
| `You've hit your usage limit` | Quota épuisé pour la période | Attendre le reset (indiqué dans l'erreur) ou acheter des crédits |

**Do not confuse them.** 401 = auth problem. Usage limit = quota problem. Running `codex login` won't fix a usage limit, and waiting won't fix a 401.

**Subprocess HOME env fix:** When `_codex_chat()` spawns a Codex subprocess under Hermes profiles, HOME is the profile-local path (`~/.hermes/profiles/<name>/home/`). The subprocess can't find `~/.codex/auth.json`. Fix: pass `env={"HOME": _REAL_HOME}` to `subprocess.Popen()`:

```python
_REAL_HOME = pwd.getpwuid(os.getuid()).pw_dir
env = os.environ.copy()
env["HOME"] = _REAL_HOME
proc = subprocess.Popen(args, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, close_fds=True, env=env)
```

**Diagnostic:** `codex login status` says "Not logged in" but `~/.codex/auth.json` has valid tokens → HOME is wrong. Test: `HOME=/home/ced codex exec "say hi"` → if it works, the subprocess env needs fixing.

### Pipeline Validation Gate Wiring (2026-05-30)

The validator must run BEFORE `generate_company_overview_pdf()`, not as a standalone check. Wiring pattern:

```python
# Build CompanyOverview Pydantic model from dict
co_model = CompanyOverview(
    company_profile=CompanyProfile(**cp_data),
    business_description=co_dict.get("business_description", ""),
    # ... all fields
)

validation = validate_pre_render(ticker=..., quarter=None, metrics=None, section_analysis={}, company_overview=co_model)

if not validation.passed:
    # Block PDF, write validation report
    logger.error(f"COMPANY OVERVIEW VALIDATION FAILED — {validation.error_count} gate(s)")
    # Write validation.txt next to overview JSON
    return  # Do NOT call generate_company_overview_pdf()
else:
    generate_company_overview_pdf(...)
```

**Key:** Convert dict to CompanyOverview model before validation. Use `_overview_cache_get()` (not raw `json.load()`) to read cached data — cache files have an envelope `{version, timestamp, data}`.

### Nami-san Prompt Hardening — Fix the Source, Not Just the Gate (2026-05-29)

**Pattern:** When validators block output that the prompt itself instructs the LLM to generate, you have a chicken-and-egg problem. The validator isn't wrong — the prompt is the root cause. Fix the prompt, not just the gate.

**Real case:** `corrections.txt` drove 32 validation rules into `pre_render_validator.py`. RULE 5 (FORBIDDEN_MARKERS) blocked `"For Nami-san:"` with severity=error. But the prompt (`prompts.py`) explicitly instructed the LLM to use `"For Nami-san:"`, `"Essential insight for Nami-san:"`, `"Namiさん向け"`, etc. The validator blocked the output → the LLM generated it again → cycle. The prompt was the ROOT CAUSE.

**Fix:** 30+ replacements across 8 files, removing ALL user-visible Nami references from the prompt chain:
- `prompts.py`: System persona `"for Nami-san"` → `"for an institutional fund manager"`; all section format labels → neutral (`"Investor insight:"`, `"Key takeaway:"`, `"Risk consideration:"`); variable `nami_label` → `insight_label`
- `mapper.py`: Fallback text `"🧠 Nami insight"` → `"🧠 Investor insight"`, JP equivalents
- `pdf_renderer.py`: Methodology text `"Nami-grade"` → `"institutional"`; marker list normalization; i18n keys
- `template.py`: `"Nami takeaway"` → `"Investor takeaway"`, `"Namiコメント"` → `"投資家コメント"`
- `validators.py`: `_EN_ALLOWED_TEMPLATE_CJK_RE` patterns updated
- `i18n.py`: Translation keys `"Nami基準"` → `"機関投資家基準"`

**Validators kept as safety nets:** `quality_gates.py`, `pre_render_validator.py`, `generator.py` (AUDIENCE_NAMI_PATTERNS) — they continue to block any Nami regression.

**Commit:** `0d42585` — 8 files, 48 insertions, 48 deletions. 432/434 tests pass (2 pre-existing failures).

**Verification:** Live NVDA deep-dive (56KB markdown, 302 lines) → **zero Nami references.** ✅

**Lesson:** When a validator blocks something the prompt generates, audit the prompt first. The validator-gate-first reflex ("add a rule to catch it") is a symptom fix. The root cause fix is prompt hardening.

Reference: `references/nami-san-prompt-hardening.md` — full inventory of 30+ replacements with before/after tables, root cause analysis, and verification proof.

Reference: `references/lightpanda-cdp-wsl2-setup.md` — (in hermes-toolbox) Lightpanda CDP server setup used during browser-based SA verification.

### LLM Prompt Directive Convention — "PRECISION INJECTION"

When LLM prompts need to inject hard data values (EPS, revenue, cash flow, ratios) to prevent hallucination, use the directive **"PRECISION INJECTION"** — never "CRITICAL OVERRIDE". The old term looks like a debug/engineering leak if the LLM echoes it in output. "PRECISION INJECTION" sounds like a data directive — if it leaks, it's much less damaging.

**Fix:** `git grep -l "CRITICAL OVERRIDE"` → rename all 14 occurrences in `prompts.py` (commit `ce012ff`). Also add both "CRITICAL OVERRIDE" and "PRECISION INJECTION" to `FORBIDDEN_MARKERS` in `pre_render_validator.py` so any leakage gets caught at the validation gate.

**Pattern:** Use 🔴 emoji + "PRECISION INJECTION" prefix for data-critical injections, ⚠️ for warnings:
```python
extra += f"\n\n🔴 PRECISION INJECTION — EPS: {direction} consensus by {abs(pct):.1f}%"
extra += f"\n⚠️  Revenue (quarterly) = ${float(rev_q)/1e9:.2f}B. Use in Revenue row."
```

### Post-Update Patch Verification (2026-05-29)

### Codex 401 vs Usage Limit — Different Errors, Different Fixes (2026-05-30)

When Codex CLI `exec` fails, the error message tells you exactly what's wrong:

| Error | Meaning | Fix |
|---|---|---|
| `401 Unauthorized: Missing bearer` | Auth token expired or missing | `codex login --device-auth` |
| `You've hit your usage limit` | Quota épuisé pour la période | Attendre le reset (indiqué dans l'erreur) ou acheter des crédits |

**Do not confuse them.** 401 = auth problem. Usage limit = quota problem. Running `codex login` won't fix a usage limit, and waiting won't fix a 401.

**Subprocess HOME env fix:** When `_codex_chat()` spawns a Codex subprocess under Hermes profiles, HOME is the profile-local path (`~/.hermes/profiles/<name>/home/`). The subprocess can't find `~/.codex/auth.json`. Fix: pass `env={"HOME": _REAL_HOME}` to `subprocess.Popen()`:

```python
_REAL_HOME = pwd.getpwuid(os.getuid()).pw_dir
env = os.environ.copy()
env["HOME"] = _REAL_HOME
proc = subprocess.Popen(args, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, close_fds=True, env=env)
```

**Diagnostic:** `codex login status` says "Not logged in" but `~/.codex/auth.json` has valid tokens → HOME is wrong. Test: `HOME=/home/ced codex exec "say hi"` → if it works, the subprocess env needs fixing.

### Pipeline Validation Gate Wiring (2026-05-30)

The validator must run BEFORE `generate_company_overview_pdf()`, not as a standalone check. Wiring pattern:

```python
# Build CompanyOverview Pydantic model from dict
co_model = CompanyOverview(
    company_profile=CompanyProfile(**cp_data),
    business_description=co_dict.get("business_description", ""),
    # ... all fields
)

validation = validate_pre_render(ticker=..., quarter=None, metrics=None, section_analysis={}, company_overview=co_model)

if not validation.passed:
    # Block PDF, write validation report
    logger.error(f"COMPANY OVERVIEW VALIDATION FAILED — {validation.error_count} gate(s)")
    # Write validation.txt next to overview JSON
    return  # Do NOT call generate_company_overview_pdf()
else:
    generate_company_overview_pdf(...)
```

**Key:** Convert dict to CompanyOverview model before validation. Use `_overview_cache_get()` (not raw `json.load()`) to read cached data — cache files have an envelope `{version, timestamp, data}`.

### Precision Function Name Search — Exact Match Matters (2026-05-29)

When searching for a function usage across the codebase, use the EXACT function name. A search for `getCompanyOverviewUrl` will return 0 results if the function is actually named `getCompanyOverviewDownloadUrl`. The grep/search_files tool does exact substring matching — partial names won't match.

**Real case:** I declared the Company Overview button missing because `search_files(pattern="getCompanyOverviewUrl")` returned 0 results. Ced corrected me: the button existed at `AnalysisCard.jsx:155` using `getCompanyOverviewDownloadUrl(ticker)`. The "Download" suffix was the difference.

**Fix:** When searching for function usage:
1. Copy the exact function name from the definition (line-by-line read)
2. If unknown, search the definition first: `search_files(pattern="export function.*overview", target="content")`
3. Then search for the exact name
4. If 0 results, try broader patterns like `overview.*download` or `company.*overview.*url`

After `hermes update` via `safe-update.sh`, the gateway drain often cuts Steps 3-5 (post-update patches, Telegram menu, health check). Always manually verify and re-apply:

```bash
# Step 3: Re-apply local patches
python3 ~/.hermes/scripts/post-update-patches.py
# Step 5: Health check
tb status
```

Also check if the update auto-stashed local changes (`WIKI.md` conflicts are common). Apply the stash if needed:
```bash
cd /home/ced/.hermes/hermes-agent
git stash list | head -3
git stash show -p stash@{0}
```

### Function Insertion in mapper.py — Don't Split Signature From Body

When adding a new `_build_*()` function to `mapper.py`, never insert it between another function's `def` line and its body. If you do, the original function's body becomes unreachable code inside the new function, and the original function returns `None` silently.

**Real bug (2026-05-29):** Inserted `_build_source_registry()` between `def _section_runtime_columns(...)` and its body. Result: `_section_runtime_columns` returned `None` → `list(runtime_columns)` → `TypeError: 'NoneType' object is not iterable` in 4 integration tests.

**Fix:** Always place new functions AFTER the COMPLETE existing function (after its final `return`). Use `patch` to insert before the NEXT function's `def` line, not inside the current one.

**Detection:** If the linter says `Function with declared return type must return value on all code paths`, check if you split a function's signature from its body.

### Backend Restart Gap — Code on Disk ≠ Code in Memory (CRITICAL)

### Prompt-Validator Circle — Fix the Source, Not the Symptom

When the pre-render validator blocks patterns that the LLM prompt explicitly requests, the validator is working correctly — the PROMPT is the root cause. Do not weaken the validator; fix the prompt.

**Real case (2026-05-29):** Validator blocked `"For Nami-san:"` in PDFs. The prompt (`prompts.py`) explicitly instructed the LLM to use `"For Nami-san:"`, `"Essential insight for Nami-san:"`, `"Nami-san takeaway"` in every section. Fix: 30+ replacements across 8 files to remove Nami language at the source. Validators kept as safety nets.

**Detection:** If validator blocks a pattern and `grep` finds the same pattern in `prompts.py` → prompt-validator circle.

**Fix:** Clean the prompt first (the SOURCE). After prompt is clean, the LLM won't generate forbidden patterns, and the validator passes naturally. Keep validators as regression safety nets.

See: `references/prompt-hardening-nami-removal.md`

Reference: `references/guidance-and-placeholder-prompt-fixes.md` — guidance source distinction pattern (CRITICAL block in prompt to distinguish company guidance from consensus) and forbidden placeholder remediation (replace "Data not available in transcript" → "Not retrieved", "—" → "a dash" in system prompts).

### Post-Processing Beats Prompt Tuning for Format Artifacts (2026-05-29)

When the LLM recites internal field names (`yfinance — eps_yoy=$2.14`) that were injected by `_fmt_metrics()`, prompt hardening has diminishing returns — the LLM sees the field names in the prompt and uses them as \"precise\" source labels. The structural fix is a **post-processing pass** between section assembly and PDF rendering.

**Implemented:** `post_process_markdown()` in `markdown.py` — three regex patterns + value-preserving callback. Wired into `generator.py` after `assemble_final_report()`. 14 field references → 0 on NVDA.

**Key technique:** Use `\S+` capture + `rstrip(\",.)};:\")` to preserve numerical values while stripping field names: `yfinance — eps_yoy=$2.14` → `yfinance ($2.14)`.

**Where to insert post-processors:** After `assemble_final_report()` but before `_append_sources_section()` — after sections are assembled but before source URLs are appended.

See: `references/prompt-metrics-field-name-leak.md` for full problem analysis and solution details.

### Backend Restart Gap — Code on Disk ≠ Code in Memory (CRITICAL)

After committing and pushing new validator code, the running uvicorn process still has the OLD code in memory. The health endpoint reads the commit hash from `git rev-parse --short HEAD` (current disk state), so it shows the new commit — but `validate_pre_render()` and all imported modules were loaded at process start and won't pick up changes.

**Real case (2026-05-29):** 8 commits pushed, health showed `9bd3168`, but validation passed and generated a 22-page PDF with 14 "For Nami-san:" leaks and 34 "NaN" occurrences. The old validator (RULE 5 severity=warning) didn't block. After restart, the new validator correctly BLOCKED the same analysis with 16+ errors.

**Detection:** If health shows new commit but behavior is old:
1. Check process start time: `ps -o lstart -p <PID>`
2. If start time is BEFORE your commits → process has old code → RESTART

**Fix:**
```bash
kill <old_pid>
cd codex-projects/stock-analysis-pipeline
.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8780 &
```

**Post-restart verification:** Trigger a fresh analysis and check `process(action='log')` for `PRE-RENDER HARD FAIL` lines — if present, the new gates are active.

**CI integration:** Add a `touch backend/main.py` or `kill -HUP` after every `git push` to force uvicorn reload in dev mode. In production, the deploy script should restart the service after pull.

Reference: `references/backend-restart-gap.md`

### Renderer Bypasses Validator — `_section_continuation()` Generates Unchecked Text

`validate_pre_render()` checks `section_analysis` (LLM-generated text) but **not** text generated by `pdf_renderer._section_continuation()`. If the renderer helper generates "For Nami-san:" commentary, it leaks into the PDF even though FORBIDDEN_MARKERS includes "For Nami-san:".

**Root cause:** `pdf_renderer.py` lines 693-720 (`_section_continuation()`) generates default commentary for Highlights, Operating Metrics, and Cash Flow sections. The LLM also generates "For Nami-san:" in the deep-dive synthesis output. The validator catches the LLM output (correctly blocking it), but any renderer-generated text would bypass.

**In this session:** The "For Nami-san:" text came from the LLM, NOT the renderer (the `_section_continuation()` English version is clean). The validator correctly blocked it. But the architectural gap remains: renderer-generated text is not validated.

**Mitigation:**
1. `_section_continuation()` already uses professional language for EN (post-fix from commit 99cf747)
2. FORBIDDEN_MARKERS catches leaked text from LLM output
3. Future: run a post-render text extraction pass on the generated PDF content using PyPDF2, then re-run `validate_pre_render()` on the extracted text

Reference: `references/renderer-bypass-validator-gap.md`

### Validator Test Mocks — Use Pydantic Models, Not `type()` Objects

`validate_pre_render()` builds `metric_map` via `metrics.model_dump()` (line ~520 of `pre_render_validator.py`). `type()` objects and bare dicts don't have `model_dump()`, so `metric_map` stays empty and rules that depend on metric values (EPS beat/miss, sanity checks) may fire incorrectly.

**Pattern:**
```python
# ✅ CORRECT — use actual Pydantic model
from backend.earnings_deep_dive.report_model import FinancialMetrics
metrics = FinancialMetrics(
    eps_actual=2.94, eps_estimate=2.80,
    revenue_actual=22.4e9, revenue_estimate=22.0e9,
)

# ❌ WRONG — type() has no model_dump()
metrics = type('Metrics', (), {'eps_actual': 2.94, ...})()
```

**Symptom:** Tests pass their own assertions but fail because OTHER rules (RULE 9 EPS/Revenue) fire on the same input due to empty `metric_map`.
