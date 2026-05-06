---
name: completion-verification-checklist
description: "Systematic post-implementation verification — scan files, cross-reference specs, table of findings, fix before declaring done. Mandatory before any 'done' declaration."
version: 1.0.0
metadata:
  hermes:
    tags: [verification, quality, audit, completion]
    priority: critical
---

# Completion Verification Checklist

## The Rule

**Never declare a task "done" without running this checklist.** "Tests pass" or "curl 200" is NOT sufficient evidence.

## Phase 0: Automated Pre-Flight (NEW)

Before manual verification, run the automated pre-push validator if available:
- [ ] `python3 /home/ced/CedControlCenter/scripts/pre_push_check.py --project . --report`
- This checks: secrets in diff, destructive commands, sensitive files staged, build syntax, test suite
- If BLOCKED: fix criticals before continuing to manual phases
- The pre_push_check is NOT a replacement for Phase 1-5 — it's a fast automated gate

## Phase 0.5: Pre-Modification Backup (MANDATORY)

**Before ANY code modification**, even for a "quick fix":
- [ ] `cp target_file target_file.bak.$(date +%Y%m%d_%H%M)` 
- [ ] Verify backup exists: `ls -la target_file.bak.*`
- This applies to: config files, .env, main.py, pipeline files, any file >50 lines
- Skip only for: new files (nothing to back up), trivial 1-line comment changes
- **Pitfall:** The most common "cl" trigger is modifying code without backup first. The user expects rollback capability on every change.

## Phase 1: File Existence Audit

- [ ] `search_files` or `find` to list all files claimed as created/modified
- [ ] Cross-reference with the task spec/plan — any missing files?
- [ ] Check file sizes — 0-byte or <100 byte files are suspicious

## Phase 2.5: Spec-to-Implementation Audit (PDF/NEW)

When a spec document exists (PDF, markdown, Google Doc):
- [ ] Extract spec with PyMuPDF — NEVER work from markdown extracts
- [ ] List every required field, section, data point
- [ ] Cross-reference against schemas + provider functions
- [ ] Classify: ✅ Present / 🔴 Critical gap / ⚠️ Inherent gap
- [ ] Mark gaps in **bold** so user sees them immediately
- [ ] For each gap: identify which provider has the data (yfinance, Finnhub, etc.)
- [ ] Full methodology: `references/spec-field-audit-methodology.md`

For EACH file:
- [ ] Open with `read_file` — is the content what was expected?
- [ ] For PDFs: is file size reasonable? (>1KB for real content). **Check text colors — dark-mode UI palettes (#c9d1d9, #8b949e) on white paper = illegible.** See `references/pdf-print-colors.md`.
- [ ] For ZIPs: unzip and list contents. **Never trust a ZIP count without extracting.**
- [ ] For reports: grep for key sections (headings, data points)

## Phase 3: ZIP Content Audit (CRITICAL)

When the deliverable is a ZIP file:
- [ ] Download the ZIP from the actual endpoint (curl)
- [ ] `unzip -l` or `python zipfile` to list ALL files
- [ ] Extract to temp dir and inspect file contents
- [ ] Verify NO empty READMEs are the only content in a section
- [ ] Verify real documents (PDF > 1KB, XLSX > 1KB)
- [ ] Count REAL content files vs placeholder files
- [ ] Report: "X real files, Y placeholders across Z sections"

**Full procedure**: `references/zip-content-audit-procedure.md` — copy-paste ready commands for ZIP audit.

## Phase 4: Endpoint Verification

For EACH endpoint:
- [ ] `curl -w "%{http_code}"` — verify 200 (not 404/500/403)
- [ ] Check response body for expected data
- [ ] Check Content-Type header is correct (application/zip, not text/html)

## Phase 4.5: Deployment Verification (CDN platforms)

**When the frontend is deployed on Vercel, Netlify, or similar CDN platforms:**

- [ ] After pushing, wait 60s then check `Etag`/`last-modified` on the deployed URL
- [ ] If Etag unchanged after 90s → auto-deploy is broken → manual redeploy in dashboard
- [ ] Check `x-vercel-cache` or equivalent header — `HIT` with large `age` = stale CDN
- [ ] Search remote JS bundle for expected new content (`grep -c 'NewIdentifier'`)
- [ ] If CDN stale, force cache bust with a real content change (not just comments)

**Pitfall:** `git push` success ≠ deployment updated. Vercel/Netlify GitHub integrations can disconnect silently. The user will see old code while you see new code (different CDN edge). Always verify the Etag changed after push. See `systematic-debugging` → `references/vercel-deploy-silent-failure.md`.

## Phase 5: Integration Check

- [ ] Frontend calls correct backend URL (no double /api/api/)
- [ ] Browser console has no uncaught JS errors
- [ ] Browser snapshot shows expected UI elements
- [ ] All user-facing states tested (loading, empty, error, success)

## Phase 6: Parallel Multi-Agent Recipe (RECOMMENDED for large changes)

When the codebase has changes across multiple layers (backend, frontend, config), spawn 3 parallel sub-agents instead of testing sequentially:

| Agent | Scope | Tools |
|-------|-------|-------|
| **Agent A** | Backend API + ZIP dossier audit | terminal, web |
| **Agent B** | Frontend deploy + HTML/API URL check | terminal, web |
| **Agent C** | Codebase file-by-file + test suite | terminal, file |

**Agent A prompt template:**
```
Test ALL backend endpoints: health, analyze, dossier/status, dossier/download.
Download the ZIP, unzip, audit EVERY file (size, PDF header, content vs placeholder).
Count real files vs placeholders. Test edge cases.
```

**Agent B prompt template:**
```
Check frontend deployment: curl -I for Etag/age, grep HTML for API URL.
Verify no localhost references. Check script bundle hash.
```

**Agent C prompt template:**
```
Read EVERY new/modified file. Verify imports, exports, function signatures.
Run full test suite. Check config completeness (.env, render.yaml).
Produce table: file → status → issue.
```

**Pattern established 2026-05-05**: 3 agents in parallel with `delegate_task(tasks=[...])` reduced recipe time from ~30min sequential to ~10min parallel. Agent B (frontend) completed in 7min, Agent C (codebase) rate-limited at 37s, Agent A (backend) timed out at 600s due to slow Render analysis. **Lesson**: Agents A gets the longest timeout (600s). Agent C needs to avoid hitting LLM rate limits (batch reads).

## The Table

Present findings in a table BEFORE declaring done:

| Item | Status | Detail |
|------|--------|--------|
| file X created | ✅ Confirmed | Path, size |
| file Y missing | ❌ Missing | Not on disk |
| endpoint /api/Z | ✅ 200 | Response correct |
| ZIP content | ⚠️ Weak | 3/7 sections have real files |

## Red Flags

- "Tests pass, must work" → **NO.** Go through Phase 3-5.
- "curl 200" → **NO.** Check response body.
- "I already checked" → **Check again.** Fresh verification.
- "It's a small change" → **Small changes cause big bugs.** Run the checklist.
