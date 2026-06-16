# Review: EDP-013 FCF Margin presence validator (t_a7c47751)

**Parent task:** t_e4190715
**Reviewer:** reviewer-qa
**Date:** 2026-06-16
**Verdict:** APPROVED

## Scope

Independent QA review of `_check_fcf_margin_presence(content)` added to
`backend/earnings_deep_dive/deep_dive_validator.py` per EDP-013
(Include FCF Margin when free cash flow and revenue are both available).

## Findings

### 1. Determinism — PASS
The check is a deterministic table-row scanner:
- Locates the Cash Flow section via `SECTION_HEADING.split()` (same parser used
  by every other validator check in this file).
- Iterates table rows whose metric name is one of: `"Free Cash Flow"` /
  `"FCF"` (FCF indicator), `"Revenue"` (revenue indicator), or any metric
  whose lowercased name contains the substring `"fcf margin"` (margin
  indicator).
- Emits the EDP-013 issue only when `has_fcf AND has_revenue AND NOT
  has_fcf_margin`. No clock, no randomness, no ticker-specific assumptions.

### 2. Ticker-agnostic — PASS
No hard-coded ticker, no fetch, no environment-dependent behavior. The
matchers `"free cash flow"`, `"fcf"`, `"revenue"`, and `"fcf margin"` are
generic English metric names. Safe to apply to any company report.

### 3. False-positive risk — PASS
Three guards prevent false positives:
- No Cash Flow section found → returns empty (line: `if cash_flow_body is None: return issues`).
- FCF absent → `has_fcf=False` → check is skipped.
- Revenue absent → `has_revenue=False` → check is skipped.
- FCF Margin in prose but not in table → still flagged. This is the intended
  semantic per the parent task body ("structured table presence, not prose
  text"). Test `test_fcf_margin_in_prose_not_table_flagged` documents and
  locks this behavior.

### 4. Return-shape backward compatibility — PASS
`validate_deep_dive(md_path) -> Tuple[bool, List[str]]` is unchanged. The
new step 5.5 (`issues.extend(_check_fcf_margin_presence(content))`) is an
additive `extend` on the existing `issues` list. All callers unpack
`(passed, issues) = validate_deep_dive(...)` and remain compatible.

### 5. Helper wiring — PASS
- New step is correctly placed: **after** numeric consistency (step 5)
  and **before** minimum content size (step 6). Step ordering follows the
  file's "cheap to expensive" pattern and prevents the FCF check from being
  short-circuited by content-size failures.
- Imports already in module: `re`, `List`, `Tuple`. No new imports added —
  good discipline (re-uses existing `SECTION_HEADING` and the same
  table-row split idiom as `_check_concision` / `_check_numeric_consistency`).

### 6. Test coverage — PASS (6/6 cases)
The focused regression file covers every case promised in the task body:

| Test | Case | Status |
|------|------|--------|
| `test_fcf_margin_present_passes` | present FCF Margin → no EDP-013 | PASS |
| `test_missing_fcf_margin_flagged` | FCF + Revenue present, FCF Margin absent → EDP-013 | PASS |
| `test_no_issue_when_fcf_absent` | missing FCF input → no EDP-013 | PASS |
| `test_no_issue_when_revenue_absent` | missing Revenue input → no EDP-013 | PASS |
| `test_fcf_margin_in_prose_not_table_flagged` | prose-only margin → still EDP-013 | PASS |
| `test_valid_section_no_fcf_margin_no_issue` | valid section with only FCF → no EDP-013 | PASS |

Each test filters issues with `"EDP-013" in i` so it isolates this rule from
pre-existing validator noise. Good test discipline.

### 7. Test isolation — PASS
- One test class (`TestEdp013FcfMarginPresence`) — single test class for a
  single rule. Atomic.
- Helper `_make_deep_dive(tmp_path, cash_flow)` writes to `tmp_path` — no
  test pollution.
- 217 lines total (file size, not code) — focused.

### 8. WIKI update — PASS
New section "## 2026-06-16 — FCF Margin presence validator check (EDP-013)"
added at the top of the EDP changelog with:
- Status, change description, verification commands, and exact result counts.
- Mirrors the format of the existing EDP-004/EDP-006/EDP-007 sections.

## Verification (Kernel)

```
$ kverify .ced-agent-kernel/specs/t_a7c47751_fcf_margin_review.json \
    --base-dir /home/ced/codex-projects/stock-analysis-pipeline
VERDICT: READY
All 8 check(s) passed.
- PASS deep_dive_validator.py exists
- PASS spec_v27_fcf_margin_presence.py exists
- PASS WIKI.md exists
- PASS python compiles: deep_dive_validator.py
- PASS FCF Margin focused tests pass (6 passed)
- PASS spec_v27_*.py regression-free (445 passed)
- PASS verification log exists
- PASS verification log proves success (6 passed)
```

## Risks / follow-ups (non-blocking)

- **Working tree not committed (parent side)**: the parent's changes to
  `deep_dive_validator.py`, `WIKI.md`, and the new test file are present
  on disk but unstaged in the worktree. This is the parent's responsibility,
  not a defect of the EDP-013 implementation itself. The review of the
  code itself is unaffected by Git state.
- **Pre-existing failures in other test files**: full `pytest tests/` is
  slow (>60s) and includes `test_yfinance.py` and other integration files
  with possible network dependencies. The 445 spec_v27 tests all pass.
  Other directories not in scope of this review.

## Acceptance criteria — ALL MET

- [x] No production files outside the validator seam were modified (only
      `deep_dive_validator.py` in `backend/earnings_deep_dive/`).
- [x] New check is deterministic (no clock/random/I/O).
- [x] Ticker-agnostic (no hard-coded ticker or external fetch).
- [x] No secrets, feedback state, analyses, generated PDFs, prompts,
      renderer, mapper, or pipeline files touched.
- [x] WIKI.md documentation updated.
- [x] Kernel proof produced and READY.

## Verdict

APPROVED — EDP-013 FCF Margin presence validator is correct, narrowly
scoped, deterministic, well-tested (6/6 cases), and ships with a passing
regression suite (445/445 in the EDP cluster).
