# Review: EDP-014 Net Debt / Net Cash presence validator (t_fab24230)

**Parent task:** t_3528c806
**Reviewer:** reviewer-qa
**Date:** 2026-06-16
**Verdict:** APPROVED

## Scope

Independent QA review of `_check_net_debt_presence(content)` added to
`backend/earnings_deep_dive/deep_dive_validator.py` per EDP-014 (require a
Net Debt or Net Cash row in the Capital Efficiency table when both cash and
total-debt rows are present). The check is wired into `validate_deep_dive()`
as step 5.75 (after the EDP-013 FCF margin check, before EDP-001/EDP-003
fiscal-period consistency).

## Acceptance criteria

1. Table-row scoped (no prose scan) — confirmed in code + 2 adversarial
   reproductions below.
2. Detects the cash+debt-without-net-row case — confirmed in focused test
   `test_missing_net_debt_flagged` and adversarial Case 4.
3. Allows the rule to be satisfied by either `Net Debt` or `Net Cash` row —
   confirmed in `test_net_debt_present_passes` and `test_net_cash_present_passes`.
4. Treats Long-term debt / Current debt / Short-term debt as debt input —
   confirmed in `case 4` adversarial reproduction.
5. Treats `Marketable Securities` and `Short-term investments` as cash input
   (the spec lists them as cash equivalents) — confirmed in
   `test_marketable_securities_variant_flagged`.
6. Treats "no Capital Efficiency section" and "missing one of the two inputs"
   as no-issue — confirmed in `test_no_issue_when_no_cap_eff_section`,
   `test_no_issue_when_cash_absent`, `test_no_issue_when_debt_absent`.
7. Wired into `validate_deep_dive` between FCF margin and fiscal-period steps.
8. No `/api/` touched. No commit performed by the builder (awaiting QA).

## Evidence

### 1. Determinism — PASS
- Pure table-row scanner. Uses the same `SECTION_HEADING.split(content)`
  parser as every other validator check in this file (FCF margin,
  fiscal-period consistency, numeric consistency, etc.).
- Iterates `|`-prefixed lines that are not `|-` separators; takes the first
  cell (metric name), lowercases it, and runs substring/equality matches.
- No clock, no randomness, no environment-dependent behavior.

### 2. Ticker-agnostic — PASS
- No hard-coded ticker, no fetch, no env vars, no LLM calls.
- Matchers (`"cash and cash equivalents"`, `"marketable securities"`,
  `"total debt"`, `"long term debt"`, `"net debt"`, `"net cash"`, etc.) are
  generic English balance-sheet row labels.

### 3. False-positive risk — PASS

Two structural guards prevent false positives:

1. **Table-row only.** Only lines that start with `|` (and are not the `|-`
   separator) are inspected. Quote lines (`> ...`) and prose text inside
   the Capital Efficiency body are not parsed. Adversarial Test A in this
   review put `Net Cash` in a quote line and left the table missing a
   net-debt row — the check correctly fired (1 issue). Adversarial Test B
   put `Net Cash` in an actual row — the check correctly passed (0 issues).
2. **Net-debt detection precedes debt-detection via `elif`.** A row labeled
   `Net Debt` is captured by `has_net_debt_or_cash = True` and is NOT
   also captured by `has_total_debt = True`, so a real net-debt row
   satisfies the rule and does not double-count as debt input.

### 4. Acceptance — PASS (all 7 focused tests)

```
$ backend/.venv/bin/python -m pytest tests/spec_v27_net_debt_presence.py -q
.......                                                                  [100%]
7 passed in 0.11s
```

Coverage of positive (Net Debt row, Net Cash row), negative (missing net
row), and absent-input variants (no cash, no debt, no section) plus
the `Marketable Securities` variant.

### 5. Bundle regression — PASS

```
$ backend/.venv/bin/python -m pytest tests/spec_v27_net_debt_presence.py \
    tests/spec_v27_fcf_margin_presence.py tests/spec_v27_concision.py \
    tests/spec_v27_forbidden_headings.py tests/spec_v27_numeric_consistency.py \
    tests/test_validator.py tests/spec_v27_verdict_valuation_dq_segments.py \
    tests/spec_v27_period_consistency.py tests/spec_v27_metrics_ledger.py \
    tests/spec_v27_source_registry.py tests/spec_v27_missing_data_leaks.py -q
........................................................................ [ 38%]
........................................................................ [ 77%]
.........................................                                [100%]
185 passed in 0.43s
```

No regressions. The 11 spec files match the parent's reported `185 passed`.

### 6. Kernel gate (kverify strict) — READY

```
$ kverify .ced-agent-kernel/specs/edp014-net-debt.json --base-dir .
VERDICT: READY
All 5 check(s) passed.
- PASS changed file: deep_dive_validator.py [path_exists]
- PASS changed file: spec_v27_net_debt_presence.py [path_exists]
- PASS python compiles: deep_dive_validator.py [python_compile]
- PASS focused tests pass (7 tests, EDP-014 detection) [command_succeeds]
- PASS bundle regression (185 tests, no regressions) [command_succeeds]
```

### 7. Wiring in `validate_deep_dive` — PASS

`validate_deep_dive` step 5.75 (between FCF margin 5.5 and fiscal-period 6):

```python
# ── 5.75. Check Net Debt / Net Cash presence in Capital Efficiency (EDP-014) ──
issues.extend(_check_net_debt_presence(content))
```

Placed after FCF margin (EDP-013) and before fiscal-period (EDP-001/EDP-003)
matches the pipeline ordering convention used throughout the file.

### 8. Independent adversarial reproductions (reviewer-generated)

| Case | Setup | Expected | Got | Verdict |
|---|---|---|---|---|
| 1 | Prose mention of "cash" and "total debt" in Highlights; Cap Eff table has no cash/debt rows | 0 issues | 0 | OK |
| 2 | Cap Eff body prose contains "net cash of $2.1B" but no net row in the table | 1 issue (prose irrelevant; check is table-scoped) | 1 | OK |
| 3 | Cap Eff table has Cash + Total Debt + Net Debt rows | 0 issues | 0 | OK |
| 4 | Cap Eff table has Cash + Long Term Debt (not "Total Debt") and no net row | 1 issue (LT debt is treated as debt input) | 1 | OK |

All four adversarial cases match the documented semantics.

## Risks

- The check uses substring matching on the lowercased first cell. Variants
  like `Total Debt & Leases` are covered by the explicit equality set
  (`"total debt & leases"`); new variants added to the spec will need to
  extend the matchers. This is the same pattern as EDP-013 FCF margin and is
  the right trade-off for a small, deterministic validator.
- The check requires both the cash-type and debt-type rows to be present.
  Reports that omit one of the two inputs (because the underlying data is
  not available) are correctly not flagged. This is a deliberate
  "structured table presence" rule, consistent with the EDP-013 design.

## Verdict

**APPROVED.** The implementation is deterministic, ticker-agnostic, narrowly
scoped to the Capital Efficiency table rows, and the focused regression
covers the positive, negative, and absent-input variants. The bundle
regression (185 tests) and the Ced Agent Kernel `kverify` spec both pass
in strict mode. The change is ready to be committed by the parent task
once the orchestrator unblocks.
