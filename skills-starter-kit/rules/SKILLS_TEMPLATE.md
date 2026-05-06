# SKILLS.md — Project Skills for Codex

> This file is read by Codex alongside AGENTS.md (zero token cost).
> Contains the top 5 skills distilled into actionable instructions for this project type.
> Hermes has the full skills — this is the compact version for Codex.

## SKILL 1: TDD (Test-Driven Development)

**Iron law:** NO production code without a failing test first.

Cycle: RED (write test, watch it fail) → GREEN (minimal code to pass) → REFACTOR (clean up).

Triad: Happy path + Unhappy path + Edge cases. All three. Always.

```bash
# RED
pytest tests/test_module.py::test_feature -v   # Must FAIL
# GREEN
pytest tests/test_module.py::test_feature -v   # Must PASS
# Refactor + full suite
pytest tests/ -q                               # No regressions
```

Anti-patterns: code before test (→ delete it), test passes on first run (→ it tests nothing),
"just this once" (→ always the first time you ship a bug).

## SKILL 2: Systematic Debugging

**Iron law:** NO fix without understanding root cause.

Phases:
1. **Root cause** — read error messages COMPLETELY. Reproduce the bug. Trace data flow upstream.
2. **Pattern analysis** — find working examples in the same codebase. Compare.
3. **Hypothesis** — form ONE hypothesis. Test MINIMALLY. One variable at a time.
4. **Implementation** — create regression test FIRST, then fix root cause.

**Before any fix, build a 2-column table:**
| ✅ Verified Facts | ❓ Hypotheses |
|---|---|

Never state a hypothesis as a fact. 3+ failed fixes → STOP. Question the architecture.

## SKILL 3: Agentic Engineering Self-Review

Before declaring done, scan your own code for these LLM-typical flaws:

- **Bloat** : verbose, repetitive. If 200 lines can be 50, rewrite.
- **Copy-paste** : duplicated logic instead of abstraction.
- **Fragile abstractions** : awkward, brittle, "works but it's gross".
- **Implicit correlations** : assuming email=ID, relying on undocumented order.
- **Resistance to simplification** : if code doesn't get simpler after 2-3 passes, stop.

## SKILL 4: Think in Code

If a task requires >3 file reads: write ONE Python script that analyzes everything in a single pass.

```
search_files (discovery) → execute_code (structured extraction) → JSON output
```

Never read 10 files sequentially when one script can do it in one pass.

## SKILL 5: Verification Before "Done"

Before declaring ANY task complete:
- □ `stat`/`ls` on EVERY file claimed created
- □ `curl` on EVERY endpoint claimed functional (check status code)
- □ `browser_navigate` + `browser_console` on EVERY frontend change (curl 200 ≠ UI works)
- □ `git diff --staged --stat` before EVERY commit
- □ Tests pass AND you can describe in plain language what the code does

If ANY box unchecked → NOT done. Never trust self-reports without file inspection.

---

## Security (ALWAYS)

- NEVER secrets in command lines, scripts, or committed files
- .env + .gitignore BEFORE first commit
- Secret leaked to git → filter-branch + gc --prune=now + regenerate key
- No ffplay/aplay/audio playback without explicit permission
- Backup critical files before modifying: `cp file file.bak`
