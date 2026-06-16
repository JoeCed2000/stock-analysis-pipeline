# Review: EDP-001 / EDP-003 fiscal-period consistency validator — repair audit (t_10351a31)

**Parent task:** t_4d284a3d (repaired implementation), originally t_8210228a
**Reviewer:** reviewer-qa
**Date:** 2026-06-16
**Verdict:** **CHANGES_REQUIRED** — The 3 named false positives are fixed and tests pass, but two acceptance criteria are NOT met: (1) EDP-001 is now provably toothless on all realistic inputs, and (2) the Kernel spec t_4d284a3d does not actually verify READY (2 of 4 checks FAIL because referenced `/tmp/verify_edp001_*.sh` scripts do not exist on disk). The WIKI line "kverify strict → READY (4/4)" is non-reproducible.

## Scope

Independent QA review of the repair commit proposed by t_4d284a3d against the CHANGES_REQUIRED verdict issued in t_7db887d6. Repair target: false-positive EDP-001 issues on AAPL 2026-06-12, AAPL 2026-06-04, GOOGL 2026-05-31 (alt).

Source files reviewed:
- `backend/earnings_deep_dive/deep_dive_validator.py` (diff, +184/-1 line, wiring at step 6)
- `tests/spec_v27_fiscal_period_consistency.py` (574 lines, 34 tests)
- `.ced-agent-kernel/specs/t_4d284a3d.json` (4 checks, 2 of which FAIL on re-run)
- `WIKI.md` (entry 2026-06-17 claims "kverify strict → READY (4/4)")

## Evidence collected

### Test execution (re-run by reviewer)

```
$ pytest tests/spec_v27_fiscal_period_consistency.py -q
..................................                                       [100%]
34 passed in 0.19s

$ pytest tests/spec_v27_fiscal_period_consistency.py \
         tests/spec_v27_fcf_margin_presence.py \
         tests/spec_v27_concision.py \
         tests/spec_v27_forbidden_headings.py \
         tests/spec_v27_numeric_consistency.py \
         tests/spec_v27_missing_data_leaks.py \
         tests/test_validator.py \
         tests/spec_v27_verdict_valuation_dq_segments.py \
         tests/spec_v27_period_consistency.py \
         tests/spec_v27_metrics_ledger.py \
         tests/spec_v27_source_registry.py -q
........................................................................ [ 33%]
........................................................................ [ 67%]
....................................................................     [100%]
212 passed in 0.45s
```

The 34/34 focused and 212/212 bundle claims reproduce.

### Kernel spec re-run by reviewer

```
$ kverify .ced-agent-kernel/specs/t_4d284a3d.json \
    --base-dir /home/ced/codex-projects/stock-analysis-pipeline --strict --json
{
  "verdict": "PARTIAL",
  "summary": "2 check(s) failed; claim is not fully proven.",
  "checks": [
    {"name": "changed file: deep_dive_validator.py",       "status": "PASS"},
    {"name": "changed file: spec_v27_fiscal_period_consistency.py", "status": "PASS"},
    {"name": "focused tests pass (34 tests)",
     "status": "FAIL",
     "message": "Command exited 127; expected 0.",
     "evidence": {
       "command": "bash /tmp/verify_edp001_repair.sh",
       "returncode": 127,
       "output_tail": "bash: /tmp/verify_edp001_repair.sh: No such file or directory\n"
     }},
    {"name": "bundle regression (212 tests)",
     "status": "FAIL",
     "message": "Command exited 127; expected 0.",
     "evidence": {
       "command": "bash /tmp/verify_edp001_bundle.sh",
       "returncode": 127,
       "output_tail": "bash: /tmp/verify_edp001_bundle.sh: No such file or directory\n"
     }}
  ]
}
```

The WIKI claim "kverify strict → READY (4/4)" is **not reproducible** by the current spec. The spec references two shell scripts at `/tmp/verify_edp001_repair.sh` and `/tmp/verify_edp001_bundle.sh` that do not exist on disk. The original /tmp/ directory has related scripts (`verify-edp006.sh`, `verify_edp013.sh`) but no edp001-named files. The spec was likely generated during a build session and the verifier scripts were cleaned up; the spec was never updated to use persistent commands.

The first acceptance criterion ("APPROVED only if Kernel spec t_4d284a3d exists and verifies READY") is **not satisfied**. The spec exists but does not verify READY.

### Real-report regression — re-run by reviewer

The previous review (t_7db887d6) identified 3 false positives. Re-running the validator against the actual report files:

| Report | t_7db887d6 result | t_10351a31 result | Verdict |
|---|---|---|---|
| AAPL 2026-06-12 earnings_deep_dive.md | 1 FP (flagged Q2 2025) | 0 EDP-001 | **FIXED** |
| AAPL 2026-06-04 earnings_deep_dive.md | 1 FP (flagged Q4 2025) | 0 EDP-001 | **FIXED** |
| GOOGL 2026-05-31 (alt) | 2 FPs (flagged Q4 2025 + Q4 2024) | 0 EDP-001 | **FIXED** |
| GOOGL 2026-06-14, GOOGL 2026-05-31 (main), MU 2026-05-21, MSFT 2026-06-01 | 0 EDP-001 | 0 EDP-001 | unchanged |

All 3 originally-flagged FPs are now clean. The algorithm-level repair is sound for the *false positive* problem.

## Triad evidence

### WIKI_EVIDENCE — present, with caveat

WIKI.md records the repair: section-header exclusion, widened EDP-003, deterministic tie-breaking, regex lookahead, 34 focused + 212 bundle, "kverify strict READY (4/4)", Kernel spec at `.ced-agent-kernel/specs/t_4d284a3d.json`. The "kverify strict READY" line is contradicted by the spec's current state (above).

### GRAPH_EVIDENCE — present

`validate_deep_dive` remains the only validation seam. No mapper, renderer, prompt, provider, API, or pipeline mutation. Wiring at step 6 (line 979) is between FCF margin and content-size — reasonable order.

### SYMBOL_PLAN — present and clean

Diff is scoped to `deep_dive_validator.py` (algorithm + wiring) and `tests/spec_v27_fiscal_period_consistency.py` (tests). No other files touched except `WIKI.md` and the cache file (informational).

## Findings

### 1. The 3 named FPs are fixed — PASS (but the test fixtures are weak)

The algorithm change addresses all three FP reports. Confirmed by direct run of `_check_fiscal_period_consistency` on the actual report files. **However**, the "real-report regression tests" in the new test file do not exercise the real report content — they use **hand-rolled minimal fixtures** designed to mimic the FP scenarios. The named tests are:

- `test_aapl_20260612_prior_year_column_allowed` — synthesized content with 4× FY2026 Q1 + 1× Q2 2026 + 1× Q2 2025
- `test_aapl_20260604_section_header_excluded` — synthesized content with `# Q4 2025 Earnings Report` header + 2× FY2026 Q1 body
- `test_googl_20260531_ttm_multi_year_allowed` — synthesized content with table columns Q2 2026 / Q1 2026 / Q4 2025 / Q4 2024 + 3× FY2026 Q2

These test the algorithm, not the actual report. The *real* reports have not been snapshotted into fixtures. The previous review's recommendation (item 5: "Snapshot their content into `tests/fixtures/fiscal_period_consistency_real_reports/` and assert zero EDP-001 issues") was not followed. Severity: minor — the algorithm works on the real reports when run directly, but the regression suite is not a true regression suite.

### 2. Determinism under reorder — PASS

The deterministic tie-breaking is implemented correctly:
```python
def _canonical_sort_key(k):
    return (period_counts[k], k[0], k[1])  # count asc, year asc, quarter asc
canonical_key = max(period_counts, key=_canonical_sort_key)
```

`max()` selects the key with the highest tuple. With identical counts, the higher (year, quarter) wins. Identical content always produces the same canonical regardless of insertion order. Confirmed by code inspection and the existing `test_matches_mapper_parse` parity check.

### 3. Section-header exclusion — PASS

`_get_heading_line_ranges()` correctly identifies heading positions. The Q4 2025 Recap header is detected by `test_heading_line_range_helper` (3 ranges asserted). AAPL 2026-06-04's "Q4 2025" header is no longer counted toward canonical.

### 4. Q([1-4])(?!\d) lookahead — PASS

`test_regex_no_q10_false_positive` confirms `2026Q10` no longer matches as Q1. The lookahead `(?!\\d)` is correctly placed in all three alternative patterns of `_FISCAL_PERIOD_RE`.

### 5. **EDP-001 IS EFFECTIVELY TOOTHLESS — FAIL (blocking)**

This is the critical finding. The widened EDP-003 now covers **every** realistic (year, quarter) combination relative to the canonical period:

| Label relation to canonical | Allowed? | Code path |
|---|---|---|
| year < canonical_year (any quarter, ANY year past) | YES | `if lbl["year"] <= canonical_year - 2: continue` (also covers year == canonical_year - 1) |
| year == canonical_year - 1 (any quarter) | YES | `if lbl["year"] == canonical_year - 1: continue` |
| year == canonical_year, quarter < canonical_q (prior quarter) | YES | `if lbl["year"] == canonical_year and lbl["quarter"] < canonical_q: continue` |
| year == canonical_year, quarter > canonical_q (guidance) | YES | `if lbl["year"] == canonical_year and lbl["quarter"] > canonical_q: continue` |
| year == canonical_year, quarter == canonical_q (canonical) | YES | `if key == canonical_key: continue` |
| year > canonical_year (any quarter) | YES | `if lbl["year"] > canonical_year: continue` |

**The 6 branches cover every possible (year, quarter) pair except the canonical itself.** The flag-emit path (`flagged_periods.add(key); issues.append(...)`) is unreachable for any label with a parseable year and quarter.

**Proof — 31 hand-crafted test cases, all silent:**

```python
from backend.earnings_deep_dive.deep_dive_validator import _check_fiscal_period_consistency
from itertools import product

canonical = (2026, 2)
test_years = [2020, 2022, 2024, 2025, 2026, 2027, 2028, 2099]
test_qs = [1, 2, 3, 4]
count_fired = 0
for y, q in product(test_years, test_qs):
    if (y, q) == canonical: continue
    content = f'FY{canonical[0]} Q{canonical[1]} results were strong. FY{canonical[0]} Q{canonical[1]} EPS beat. Also FY{y} Q{q} was mentioned.'
    issues = _check_fiscal_period_consistency(content)
    if issues:
        count_fired += 1
# Result: count_fired = 0 of 31 cases
```

**The acceptance criterion "CHANGES_REQUIRED if the widened allowance makes EDP-001 effectively toothless" is triggered.** The WIKI's "Trade-off" entry acknowledges this:

> EDP-001 now allows all common MD&A period references (prior year, prior quarter, TTM, trend analysis). False-positive prevention is prioritized over comprehensive detection. Genuine report-period mismatches (e.g., report about wrong quarter) are caught at the pipeline level against the resolved_quarter.

This is an explicit decision, not a hidden bug. The validator has become a pure no-op. The check still runs (compute cost is small), but it will never emit an EDP-001 issue on any parseable input. The signal has been reduced to zero.

**Question for the orchestrator / Ced:** Is a 0% detection-rate validator worth keeping in the validation chain? The trade-off WIKI documents is reasonable, but the validator's contribution to the bundle's 212 tests is now zero — it cannot fail.

This is a **blocking** finding per the task's own acceptance criteria. The author should either:
- (a) **Tighten the EDP-003 allow-list** to a meaningful subset (e.g., prior year same quarter + same year prior quarter + 2-year prior same quarter only — not "any year-1 any q" and not "any year-2+ any q")
- (b) **Remove the EDP-001 check from `validate_deep_dive`** if the team agrees it's no longer useful, and update WIKI accordingly
- (c) **Document explicitly that EDP-001 is intentionally a no-op** and obtain sign-off that this is the desired steady state

### 6. Kernel spec t_4d284a3d — FAIL (blocking)

See evidence above. The spec exists but does not verify READY because it references two nonexistent shell scripts. The acceptance criterion "APPROVED only if Kernel spec t_4d284a3d exists and verifies READY" is not satisfied.

Recommended fix: replace the `command_succeeds` checks with direct pytest invocations (which are reproducible across runs):

```json
{
  "kind": "command_succeeds",
  "name": "focused tests pass (34 tests)",
  "command": "python3 -m pytest tests/spec_v27_fiscal_period_consistency.py -q",
  "stdout_pattern": "34 passed"
},
{
  "kind": "command_succeeds",
  "name": "bundle regression (212 tests)",
  "command": "python3 -m pytest tests/spec_v27_fiscal_period_consistency.py tests/spec_v27_fcf_margin_presence.py tests/spec_v27_concision.py tests/spec_v27_forbidden_headings.py tests/spec_v27_numeric_consistency.py tests/spec_v27_missing_data_leaks.py tests/test_validator.py tests/spec_v27_verdict_valuation_dq_segments.py tests/spec_v27_period_consistency.py tests/spec_v27_metrics_ledger.py tests/spec_v27_source_registry.py -q",
  "stdout_pattern": "212 passed"
}
```

This makes the spec reproducible across runs, machines, and /tmp cleanups. The current spec will continue to FAIL kverify on any machine that doesn't have those /tmp scripts.

### 7. WIKI entry overstates kverify status — minor

WIKI says "kverify strict → READY (4/4)". The spec has 4 checks; the count matches. But the strict run shows 2/4 PASS. The WIKI should say "kverify PARTIAL (2/4: file paths OK; /tmp script refs FAIL)" until the spec is fixed. Severity: minor, fixed by fixing the spec.

### 8. Cache file is still dirty — informational

```
$ git status --short .wiki_builder_cache/
M .wiki_builder_cache/stock-analysis-pipeline/file_hashes.json
```

The cache file was dirtied by the wiki_builder run during the parent task. The parent task's handoff explicitly noted "cache_artifact: .wiki_builder_cache/stock-analysis-pipeline/file_hashes.json (unstaged, per instructions)". The orchestrator commit should restore this file before merging.

## What is GOOD

- The 3 named false positives are fixed at the algorithm level. Re-running on the actual report files confirms 0 EDP-001 issues where there used to be 1-2.
- The 4 sub-fixes (section-header exclusion, widened EDP-003, deterministic tie-break, regex lookahead) are all implemented correctly.
- The wiring point in `validate_deep_dive` (step 6) is reasonable and matches the task brief.
- The 34 focused tests are correct for the algorithm as written and pass cleanly.
- The 212 bundle test count is reproducible.
- `_try_parse_quarter` remains a clean parity mirror of the mapper.
- The WIKI's "Trade-off" section is honest about the design choice (even though it triggers the toothless-validator concern).

## What is WRONG

- EDP-001 is now mathematically guaranteed to be silent on any parseable input. 0 of 31 hand-crafted test cases fire. The acceptance criterion explicitly states CHANGES_REQUIRED in this case.
- The Kernel spec t_4d284a3d does not actually verify READY. Two of four checks FAIL because referenced `/tmp/verify_edp001_*.sh` scripts do not exist. The WIKI's "kverify strict → READY (4/4)" line is not reproducible.
- The "real-report regression tests" use synthesized content, not snapshots of the actual report files. The test suite is a fixture test, not a true regression test.
- The cache file is dirty (informational; expected to be restored by orchestrator).

## Minimal fix scope

To turn CHANGES_REQUIRED into APPROVED, address (5) and (6) at minimum. Items (7) and (8) are smaller and can be folded in.

1. **Tighten the EDP-003 allow-list** so EDP-001 has meaningful detection power. Recommended subset:
   - `(canonical_year - 1, canonical_q)` — exact prior-year same-quarter
   - `(canonical_year, q)` for `q < canonical_q` — prior quarter same year
   - Optionally: `(canonical_year - 2, canonical_q)` for 2-year-prior trend
   - Forward-looking: keep as-is (any future period)
   - Drop: "any year-1, any quarter" (too broad)
   - Drop: "any year ≤ year-2, any quarter" (way too broad)
   
   Concretely, in `_check_fiscal_period_consistency`:
   ```python
   # Tightened EDP-003
   if lbl["year"] == canonical_year - 1 and lbl["quarter"] == canonical_q:
       continue  # exact prior year, same quarter
   if lbl["year"] == canonical_year and lbl["quarter"] < canonical_q:
       continue  # prior quarter, same year
   if lbl["year"] > canonical_year:
       continue  # forward-looking
   if lbl["year"] == canonical_year and lbl["quarter"] > canonical_q:
       continue  # future quarter same year
   # Optional: 2-year prior same quarter for trend
   if lbl["year"] == canonical_year - 2 and lbl["quarter"] == canonical_q:
       continue
   ```
   
   This preserves the 3 named FP fixes (AAPL 2026-06-12 Q2 2025 prior-year exact match, AAPL 2026-06-04 Q4 2025 → only fires if it's NOT a heading; section-header exclusion handles it before this point) and GOOGL 2026-05-31 TTM (Q4 2025 = prior year same quarter, allowed; Q4 2024 = year-2, would need the optional trend allowance) and gives EDP-001 actual detection power.

2. **Fix the Kernel spec** to use persistent commands (pytest invocations) instead of /tmp scripts. See Finding 6 for the exact replacement.

3. **Update WIKI** to reflect actual kverify status. After fixing the spec, "READY (4/4)" will be accurate; until then it should say "PARTIAL (2/4)".

4. **Add 3 fixture snapshots** of the actual AAPL 2026-06-12, AAPL 2026-06-04, GOOGL 2026-05-31 (alt) report content under `tests/fixtures/fiscal_period_consistency_real_reports/` and have the regression tests load from those snapshots instead of inline strings. This is the previously-recommended item that was skipped.

5. **Restore `.wiki_builder_cache/stock-analysis-pipeline/file_hashes.json`** in the orchestrator commit.

After items 1, 2 are addressed, the algorithm will:
- Have meaningful EDP-001 detection power (no longer toothless)
- Pass kverify strictly (4/4 READY)
- Keep the 3 named FP reports clean

Items 3, 4, 5 are smaller and can be folded into the same patch.

## Verdict

**CHANGES_REQUIRED.** The 3 named false positives are fixed at the algorithm level (good), the tests pass (good), and the wiring is clean (good). But two acceptance criteria are not met:

1. EDP-001 is provably toothless (0/31 hand-crafted cases fire). The acceptance criterion "CHANGES_REQUIRED if the widened allowance makes EDP-001 effectively toothless" is triggered.
2. Kernel spec t_4d284a3d does not verify READY. The WIKI's "kverify strict → READY (4/4)" claim is non-reproducible. The acceptance criterion "APPROVED only if Kernel spec t_4d284a3d exists and verifies READY" is not satisfied.

The author made a deliberate trade-off (documented in WIKI: "False-positive prevention is prioritized over comprehensive detection"), but the result is a validator that can never emit a finding. Either tighten the allow-list so EDP-001 has detection power, or remove EDP-001 from `validate_deep_dive` and document the removal. Fix the Kernel spec to use persistent pytest invocations. Re-submit for re-review.
