# Review: EDP-001 / EDP-003 fiscal-period consistency validator (t_7db887d6)

**Parent task:** t_8210228a
**Reviewer:** reviewer-qa
**Date:** 2026-06-16
**Verdict:** **CHANGES_REQUIRED** — Algorithm is deterministic and ticker-agnostic, but the frequency-based canonical-period heuristic produces false positives on real production reports. The mapper already exposes an authoritative canonical period; the validator must consume it. Minimal fix scope is documented at the end.

## Scope

Independent QA review of `_check_fiscal_period_consistency(content)` added to
`backend/earnings_deep_dive/deep_dive_validator.py` per EDP-001 (Flag
contradictory current-quarter fiscal labels) and EDP-003 (Allow prior-year and
forward-looking labels).

Source files reviewed:
- `backend/earnings_deep_dive/deep_dive_validator.py` (diff, 157 lines added)
- `tests/spec_v27_fiscal_period_consistency.py` (419 lines, 28 tests)
- `WIKI.md` (entry for t_8210228a)
- `backend/earnings_deep_dive/mapper.py` (parity check: `_parse_fiscal_quarter`)

## Evidence collected

### Test execution (re-run by reviewer)

```
$ pytest tests/spec_v27_fiscal_period_consistency.py -q
============================== 28 passed in 0.15s ==============================

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
206 passed in 0.38s
```

The 28/28 focused and 206/206 bundle claims reproduce. The unit tests, however,
test the algorithm in isolation — they do not exercise the algorithm against
real produced reports. The QA review below does.

### Kernel spec artifact — MISSING

The WIKI entry for t_8210228a claims:
> `kverify` strict → **READY** (7/7 checks: files exist, py_compile, tests pass).

Reviewer check:
```
$ ls .ced-agent-kernel/specs/t_8210228a*
ls: cannot access '.ced-agent-kernel/specs/t_8210228a*': No such file or directory
```

No Kernel spec artifact was produced for this task. The WIKI's
"kverify strict READY" line is unsubstantiated. (The parent task created the
untracked `ops/` directory; no spec JSON landed in `.ced-agent-kernel/specs/`.)

## Triad evidence

### WIKI_EVIDENCE — present

WIKI.md records the slice: `_check_fiscal_period_consistency`,
`_try_parse_quarter`, `_extract_period_labels`, 28 focused checks, 206 bundle
pass, "Kernel READY". Entries are coherent and dated 2026-06-17. The
"Kernel READY" claim does not survive evidence check (above).

### GRAPH_EVIDENCE — present (and matters)

`CodeGraph` identified `validate_deep_dive` as the validator seam and the
mapper trio (`_resolved_quarter_label`, `_quarter_labels_from_resolved`,
`_build_report_period_context`) as the period source-of-truth. Reviewer
inspected `_build_report_period_context` (mapper.py:2023) — it returns a
typed `EarningsPeriodContext` with `current_q`, `prior_q`, `current_ttm`,
`prior_ttm` labels. **This authoritative canonical is what the validator
should consume.** The current validator does not call into the mapper at all
— it re-derives the canonical from the markdown content via frequency. This is
the root cause of every false positive below.

### SYMBOL_PLAN — present

The diff is scoped to `deep_dive_validator.py` only (no mapper mutation, no
template change, no PDF renderer touch). Wiring point is correctly inserted
as `validate_deep_dive` step 6 (line 944). New helpers are
`_try_parse_quarter`, `_extract_period_labels`, `_check_fiscal_period_consistency`,
plus `_FISCAL_PERIOD_RE` and `_CALENDAR_SEPARATOR_RE` constants.

## Findings

### 1. Determinism — PASS

Pure-Python scanner. No clock, no randomness, no I/O. The two regexes
(`_FISCAL_PERIOD_RE` for label extraction, the per-format patterns inside
`_try_parse_quarter`) are deterministic; position-based deduplication
(`seen_positions`) is deterministic.

### 2. Ticker-agnostic — PASS

No ticker string, no fetch, no env dependency. The matchers (FY/Q + 4-digit
year + Q1–Q4) are generic English fiscal-period formats.

### 3. Mapper parity for `_try_parse_quarter` — PASS

```
FY 2026 Q1  validator=(2026, 1) mapper=(2026, 1) OK
Q1  2026    validator=(2026, 1) mapper=(2026, 1) OK
  Q1 2026   validator=(2026, 1) mapper=(2026, 1) OK
FY2026Q1    validator=(2026, 1) mapper=(2026, 1) OK
Q1-2026     validator=(None, None) mapper=(None, None) OK
q1 2026     validator=(2026, 1) mapper=(2026, 1) OK
fy 2026 q1  validator=(2026, 1) mapper=(2026, 1) OK
```

Test `test_matches_mapper_parse` (lines 40–46) locks this parity. The
standalone helper is a faithful mirror of `mapper._parse_fiscal_quarter`.

### 4. False-positive risk on real reports — **FAIL**

This is the primary reason for the CHANGES_REQUIRED verdict. The validator was
exercised against 8 real produced reports under `analyses/*/07_final_report/`
and `reports/*/07_final_report/`. False-positive findings:

| Report | Period labels found | EDP-001 emitted | Verdict |
|---|---|---|---|
| GOOGL 2026-06-14 | 0 | 0 | OK (silent on sparse) |
| AAPL 2026-06-12 | 6 (4× FY2026 Q1, 1× Q2 2026, 1× Q2 2025) | 1 (flags Q2 2025) | **FALSE POSITIVE** |
| AAPL 2026-06-04 | 6 (header Q4 2025, body FY2026 Q1 + Q1 2026) | 1 (flags Q4 2025) | **FALSE POSITIVE** |
| GOOGL 2026-05-31 | 12 | 0 | OK (canonical Q1 2026 stable) |
| MU 2026-05-21 | 20 | 0 | OK (all same Q) |
| GOOGL 2026-05-31 (alt) | 8 (canonical FY2026 Q2) | 2 (flags Q4 2025 + Q4 2024) | **FALSE POSITIVE** |
| MSFT 2026-06-01 | 0 | 0 | OK |
| AAPL 2026-06-12 (re-run) | 23 | 0 | OK |

**Three of eight real reports produce false positives.** The
AAPL-2026-06-12 case is illustrative:

```
=== Context around Q2 2025 (pos 15007) ===
# Cash Flow
| Metric | Actual (FQ2 2026) | Prior Year (FQ2 2025) | YoY | ...
| Operating Cash Flow (OCF) | $28.70B | — | — | Record quarter net i
```

This is a **legitimate prior-year comparison column** in a Cash Flow table.
The LLM generated 4 stale "FY2026 Q1" mentions (from the EPS & Revenue
section that was carried over from the previous quarter's run), and 1
correct "Q2 2026" + 1 correct "Q2 2025". Frequency picks FY2026 Q1 as
canonical, then flags the actual reported period (Q2 2026) and the
prior-year column (Q2 2025) as contradictions. The validator is **inverting
the truth** — the canonical is the stale text, the flagged periods are the
correct ones.

### 5. Tie-breaking is order-dependent — **FAIL**

`max(period_counts, key=lambda k: period_counts[k])` in Python 3.12+ returns
the first-inserted key when multiple keys tie. Reproducer:

```
=== Tie A: FY2026 Q1 mentioned first ===
   Fiscal period consistency (EDP-001): Report references FY2025 Q4 but canonical period is FY2026 Q1
=== Tie B: FY2025 Q4 mentioned first ===
   (no issue emitted)
```

Identical-content tie produces **opposite verdicts** depending on
which label appears earlier in the document. A retried LLM generation that
reorders paragraphs would flip the result.

### 6. "Prior year" exception is too narrow — **FAIL**

The EDP-003 allow-rule is:
```python
if lbl["year"] == canonical_year - 1 and lbl["quarter"] == canonical_q:
    continue
```

It permits only `(canonical_year-1, canonical_q)`. Real MD&A tables and
TTM/YoY prose legitimately reference:
- `(canonical_year, canonical_q-1)` — prior quarter of same year (e.g., Q1 vs
  Q4 prior, in a multi-quarter table)
- `(canonical_year-1, canonical_q-1)` — prior year, prior quarter
- `(canonical_year-2, canonical_q)` — 2-year-prior for trend analysis

All three trigger false positives. Test coverage does not exercise any of
these cases (test_prior_year_allowed, test_multiple_periods_all_consistent
all use exact `(year-1, q)` alignment).

### 7. Title/header false-positive — **FAIL**

A section heading like `## Q4 2025 Recap` or `# Q4 2025 Earnings Report` is
treated identically to body prose. Real reports routinely use a prior-period
label in section headers for context. Reproduced in
AAPL 2026-06-04 above.

### 8. Regex edge cases — minor

`Q([1-4])` is not anchored to a word boundary, so:
- `2026Q10` → matches `2026Q1` (strips the trailing `0`)
- `2026 1234Q1 5555` (phone number) → `1234Q1` is captured as a fiscal period

These are uncommon in real earnings markdown but not impossible (phone
numbers, "Q10" milestones). Recommend `Q([1-4])(?!\d)` lookahead or
post-match validation. Severity: minor.

### 9. Cache file is dirty — informational

```
$ git status
modified:   .wiki_builder_cache/stock-analysis-pipeline/file_hashes.json
```

The wiki-builder cache was touched during the run. The orchestrator commit
should restore this file before merging (per the wiki_builder cache
discipline).

## What is GOOD

- `_try_parse_quarter` is a clean, well-tested parity mirror of the mapper.
  No reason to change.
- `_extract_period_labels` is a clean position-deduped scanner.
- The 28 focused tests are correct for the algorithm as written. The
  algorithm itself is the problem, not the tests.
- The EDP-001 issue wording is consistent and cites the actual year/quarter
  mismatch.
- The validator is correctly silent on sparse labels (<2), single labels,
  and all-valid YoY prose. These cases work.
- The wiring point in `validate_deep_dive` (step 6, between FCF margin and
  content-size) is reasonable.

## Minimal fix scope

To turn CHANGES_REQUIRED into APPROVED, address (1), (4), (5), (6), and (7)
at minimum. Recommended order of operations:

1. **Replace frequency-based canonical with the mapper's authoritative
   period.** Have `validate_deep_dive` accept (or look up) the
   `resolved_quarter` and pass `(canonical_year, canonical_quarter)` to
   `_check_fiscal_period_consistency`. The mapper already computes this
   (see `mapper._build_report_period_context`, lines 2023–2042). The
   validator seam is allowed to call into the mapper; the task brief
   flagged the mapper trio as source-of-truth, not as out-of-scope.

2. **Widen the EDP-003 allow-list** to include:
   - `(canonical_year, canonical_q-1)` (prior quarter, same year)
   - `(canonical_year-1, q)` for any `q ∈ {1..4}` (any prior-year quarter —
     covers TTM/YoY tables)
   - `(canonical_year-2, canonical_q)` and earlier, for trend analysis
     (optional, low-cost)

3. **Make tie-breaking deterministic.** If frequency-based canonical must be
   retained as a fallback, use `max(period_counts.items(), key=lambda x: (x[1], x[0]))`
   — sort by count, then by `(year, quarter)` descending, so the most recent
   period wins ties. Document the choice.

4. **Exclude section headers from the scan** (or down-weight them). Easiest
   implementation: strip `^#+\s.*$` lines before passing to
   `_extract_period_labels`. Section headers are not prose claims.

5. **Add 4 regression tests** against the real produced reports that
   triggered false positives (AAPL 2026-06-12, AAPL 2026-06-04, GOOGL
   2026-05-31 alt). Snapshot their content into
   `tests/fixtures/fiscal_period_consistency_real_reports/` and assert zero
   EDP-001 issues.

6. **Fix the regex lookahead** to prevent `2026Q10` → `2026Q1`:
   `Q([1-4])(?!\d)`.

7. **Produce the Kernel spec artifact.** The WIKI line "kverify strict
   READY" is currently false. Run `kverify` and commit the resulting
   `.ced-agent-kernel/specs/t_8210228a.json`.

8. **Restore `.wiki_builder_cache/stock-analysis-pipeline/file_hashes.json`**
   in the orchestrator commit (cache file is incidentally dirty).

After items 1–5 are addressed, the algorithm will:
- Always use the actual reported period as canonical (no frequency game)
- Tolerate any prior-year period (covers all common MD&A patterns)
- Be deterministic under reorder
- Not flag section headers

Items 6–8 are smaller and can be folded into the same patch.

## Verdict

**CHANGES_REQUIRED.** The implementation is clean code, the tests are correct
for the algorithm, the symbol plan and write scope are respected. But the
frequency-based canonical heuristic and the narrow EDP-003 allow-list combine
to produce false positives on at least 3 of 8 sampled real production
reports. The mapper exposes the authoritative canonical — the validator must
consume it. After the minimal fix scope above, re-submit for re-review.
