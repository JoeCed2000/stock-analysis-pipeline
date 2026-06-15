# QA Review — Forbidden-heading validator checks (EDP-004, EDP-011)

Date: 2026-06-16
Reviewer: reviewer-qa (kanban task t_a999104e)
Target change: parent task t_d282872c
Verdict: **APPROVED**

## Verdict summary

The parent change adds a deterministic, ticker-agnostic forbidden-heading
scanner to `validate_deep_dive()` and wires it in as step 0.5. The new
check is narrow, the new tests cover both the positive and the negative
allow-list cases, and Ced Agent Kernel strict verification returned READY
(7/7 checks PASS, exit 0). One residual concern (EDP-011 regex breadth) is
informational and is not a blocker for this slice — it can be tightened
in a follow-up task if false-positives appear in production.

## Scope verification (write_scope compliance)

Accepted the parent's `git status` and confirmed the only working-tree
mutations are inside the approved seam:

| File | Status | Inside approved scope? |
|---|---|---|
| `backend/earnings_deep_dive/deep_dive_validator.py` (M) | Modified | ✅ validator seam — explicitly authorized |
| `tests/spec_v27_forbidden_headings.py` (??) | New | ✅ focused forbidden-heading regression — explicitly authorized |
| `WIKI.md` (M) | Modified | ✅ documentation — explicitly authorized |
| `ops/` (??) | Untracked directory | ⚠️ NOT in scope of t_d282872c. Left untouched. Out of this review's mandate. |
| 5 ahead of `origin/kanban/spec-fonctionnelle-sa` | Pre-existing commits from prior tasks | ✅ unrelated to this slice |

No production files outside the validator seam were modified.
No secrets, no feedback state, no schema files were touched.

## Code review (agentic-engineering checklist)

### 1. Bloat / copy-paste / fragile abstraction
- The new function `_check_forbidden_headings(content)` is 28 lines, sits in
  a single file, and reuses the existing `SECTION_HEADING` regex. No
  duplication, no new abstraction layer.
- The two new module-level constants `FORBIDDEN_BACKGROUND_HEADINGS` and
  `FORBIDDEN_QUALITY_PATTERNS` are co-located with the function that uses
  them. No premature abstraction.
- `lstrip("🌟⚠️✨")` on the heading text is consistent with the existing
  emoji-stripping pattern used elsewhere in the file. No new pattern
  invented.

### 2. Ticker-agnosticism (acceptance criterion)
- EDP-004 forbidden set is a static list of 5 English strings; no
  per-ticker branch in `_check_forbidden_headings`. ✅
- EDP-011 regex `\bQuality\b` is a single compiled pattern; no per-ticker
  branch. The two exclusion paths (`required_names` membership and
  `"Earnings" in canonical`) are also static. ✅
- Decision at line `if "Earnings" in canonical or "earnings" in canonical`
  is case-insensitive (covers "Earnings" and "earnings"). Minor style nit:
  the inner branch could collapse to a single `casefold()` compare, but
  this is micro-optimization, not a defect.

### 3. Backward compatibility of `validate_deep_dive()` return shape
- The new step (0.5) only `extend()`s the `issues` list and does not
  modify the `(passed, issues)` return tuple. ✅
- Confirmed signature unchanged: `Tuple[bool, List[str]]` (read at
  `deep_dive_validator.py:269-275` — "Returns: (passed, issues)" docstring).
- All 4 callers identified by CodeGraph
  (`validate_deep_dive_or_retry`, `backend/main.py earnings_deep_dive`,
  `scripts/render_deep_dive_from_md.py amain`, `backend/pipeline.py
  _add_earnings_deep_dive_if_transcript`) consume the same tuple and
  would continue to work — no call site needs to change.

### 4. No accidental broad content heuristic
- EDP-004 uses **substring** match (e.g. "Competitive Landscape" flags a
  heading called "Competitive Landscape Considerations"). This is
  intentional: the parent's task scope is to flag anything that
  *resembles* a stable background section. Substring is the right
  granularity here. Documented in the WIKI as "exact substring matching".
- EDP-011 uses **regex word-boundary** match. This is broader: it would
  also flag "Management Quality", "Quality of Earnings", "ROE Quality",
  etc. **Informational finding**: this is a known limitation (the parent
  acknowledged only "Backlog Quality" and "Earnings Quality" as
  exclusions). If real LLM output produces these headings, the slice
  would need a follow-up. For now, the 12 tests + the 0.28s runtime
  show it does not over-flag the existing canonical sections.
  - Severity: INFO (not a blocker for this first slice).

### 5. Determinism
- The function is pure (string in, list out). No I/O, no RNG, no datetime.
  Same input → same issues list. ✅
- EDP-004 iteration order is deterministic (forbidden list order ×
  heading regex match order). EDP-011 same. ✅

### 6. Test coverage
- 12 tests in `tests/spec_v27_forbidden_headings.py`:
  - 7 EDP-004 tests: valid, 4 single-heading cases, multi-heading,
    legitimate-`### Competitive Context` negative case.
  - 5 EDP-011 tests: 2 generic-flag cases, 3 negative cases
    (Backlog Quality, Earnings Quality, leading "Quality" word).
- The negative cases matter: they lock in the allow-list semantics so a
  future refactor cannot accidentally remove them. ✅

## Functional verification

```
.venv/bin/python3 -m pytest tests/spec_v27_forbidden_headings.py -q
→ 12 passed in 0.09s   ✅

.venv/bin/python3 -m pytest tests/spec_v27_forbidden_headings.py \
    tests/spec_v27_missing_data_leaks.py tests/test_validator.py \
    tests/spec_v27_verdict_valuation_dq_segments.py \
    tests/spec_v27_period_consistency.py tests/spec_v27_metrics_ledger.py \
    tests/spec_v27_source_registry.py -q
→ 157 passed in 0.28s   ✅ (matches parent's claim; 0 regressions)

.venv/bin/python3 -m pytest tests/ -k "deep_dive or forbidden or earnings" -q
→ 90 passed, 1014 deselected   ✅
```

## Ced Agent Kernel (strict mode)

```
kverify .ced-agent-kernel/specs/t_a999104e_code_change_verified.json \
    --base-dir /home/ced/codex-projects/stock-analysis-pipeline
```

Verdict: **READY** (7/7 checks PASS, exit 0)

Checks proven:
1. `path_exists` × 3 — validator, new test file, WIKI.md all on disk.
2. `python_compile` — `deep_dive_validator.py` compiles.
3. `command_succeeds` — focused pytest returns 0 with "12 passed" in stdout.
4. `path_exists` — verification log present.
5. `file_contains` — log contains "12 passed" pattern.

No `SPEC WARNINGS`, no `FAIL` checks.

## WIKI_EVIDENCE

Read `WIKI.md` (working tree). The 2026-06-15 — Forbidden-heading
validator checks section accurately documents:
- The seam (deep_dive_validator.py).
- The two forbidden sets.
- The 12 new tests.
- The exact pytest verification command and 157/157 result.
- Kernel READY verdict.

Cross-checked against the diff — WIKI matches the implementation, no
stale claims.

## Findings

| # | Severity | Area | Detail |
|---|---|---|---|
| 1 | INFO | EDP-011 regex breadth | `\bQuality\b` will also flag "Management Quality", "Quality of Earnings", "ROE Quality" etc. Parent acknowledges this is a first slice; current 12 tests + WIKI doc cover the documented exclusions. Recommend a follow-up task if production tickers show false positives. |

No P0/P1/P2 blockers. Single INFO finding is non-blocking.

## Decision

**APPROVED** — the change is minimal, deterministic, ticker-agnostic,
backward-compatible on the `(passed, issues)` return shape, and
independently verified by 12 new tests, 157 mixed-suite tests, and
Ced Agent Kernel strict READY (7/7).

The work satisfies all 4 acceptance criteria:
1. ✅ No production files outside the approved validator seam were
   modified (WIKI.md documentation is explicitly authorized).
2. ✅ New checks are deterministic and ticker-agnostic.
3. ✅ No secrets or feedback state touched.
4. ✅ One short review artifact written under `docs/feedback-audits/`
   with Kernel READY proof included above.
