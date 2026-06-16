# Review — Concision validator checks (EDP-007, EDP-008, EDP-009)

**Task:** t_01ac4179 (review of parent t_87366c59)
**Reviewer:** reviewer-qa
**Date:** 2026-06-16
**Verdict:** **APPROVED**

## Scope reviewed

- `backend/earnings_deep_dive/deep_dive_validator.py` — added `_check_concision` + 4 module-level constants + 2 prose counters + 1 highlights helper (~155 lines), wired at step 4.5 of `validate_deep_dive`.
- `tests/spec_v27_concision.py` — 9 new tests (EDP-007: long prose, multi-paragraph; EDP-008: prose paragraph, excessive bullets; EDP-009: long prose; plus compact negative cases).
- `WIKI.md` — documentation entry for the change.
- `.ced-agent-kernel/specs/t_87366c59.json` + `verify_concision.sh` — Kernel proof harness.

## Acceptance criteria check

| # | Criterion | Result |
|---|---|---|
| 1 | No production files outside validator seam modified | ✅ Only `deep_dive_validator.py` in `backend/earnings_deep_dive/`. No feedback store, analyses, PDFs, prompts, renderer, or pipeline touched. |
| 2 | New checks are deterministic and ticker-agnostic | ✅ All thresholds are module-level constants (120 words, 5 bullets, 1 paragraph). No ticker literals. Heading matchers use canonical substrings only. |
| 3 | `validate_deep_dive` return shape preserved | ✅ Step 4.5 uses `issues.extend(_check_concision(content))` — still returns `(bool, List[str])`. All call sites (`validate_deep_dive_or_retry`, render validation) unaffected. |
| 4 | Focused regression file covers long prose, excessive bullets, compact allowed | ✅ `tests/spec_v27_concision.py` has 9 tests across 3 EDP rules + edge case (empty body). |

## Independent verification (executed this run)

| Check | Command | Result |
|---|---|---|
| Focused regression | `pytest tests/spec_v27_concision.py -q` | **9 passed** in 0.09s |
| Full regression suite | `pytest tests/spec_v27_concision.py tests/spec_v27_forbidden_headings.py tests/spec_v27_missing_data_leaks.py tests/test_validator.py tests/spec_v27_verdict_valuation_dq_segments.py tests/spec_v27_period_consistency.py tests/spec_v27_metrics_ledger.py tests/spec_v27_source_registry.py -q` | **166 passed** in 0.31s (0 regressions) |
| Module compile | `py_compile backend/earnings_deep_dive/deep_dive_validator.py` | OK |
| Kernel strict | `kverify .ced-agent-kernel/specs/t_87366c59.json --base-dir .` | **READY** (3/3 checks passed) |

## Code-quality observations

### Determinism
All thresholds are immutable module-level constants. No time, RNG, or external state. Tests can be re-run on any ticker and the same markdown structure will always produce the same issues.

### Ticker-agnosticism
- `_check_concision` matches headings by canonical substring: `"EPS & Revenue" in heading or ("EPS" in heading and "Revenue" in heading)`, `"Highlights" in heading and "Lowlights" in heading`, `"Operating Metrics" in heading`. All match canonical names and their plain-English variants.
- No ticker names, sector names, or curated lists of company-specific words.

### Anti-bloat
- 4 small helpers, each <25 lines, with single responsibilities:
  - `_count_prose_words` — word counter with table/quote/bullet/heading skip rules
  - `_count_paragraphs` — paragraph block counter (same skip rules)
  - `_check_highlights_concision` — bullet-group counter + prose-paragraph flag
  - `_check_concision` — orchestrator that splits sections and dispatches
- No copy-paste, no leaky abstractions. The shared skip rules in `_count_prose_words` and `_count_paragraphs` are duplicated (5-line tuple), which is acceptable at this scale.

### False-positive risk
- `_VALID_SECTIONS` in tests has the line `> Beat on both top and bottom lines.` — quote prefix `>` is correctly skipped, so it doesn't add to prose word count.
- Empty/missing body: counters return 0, no false positive.
- The `**bold**` skip rule in `_count_prose_words` is correct for the canonical patterns — bold is used as a "label" in Highlights/Lowlights and rarely inside EPS/Operating Metrics prose. No real-world markdown would put 120+ words inside a `**...**` label, so the skip is safe.
- EDP-008 bullet grouping uses `**` and `>` as block separators plus blank lines. This matches the canonical Nami template and the `_VALID_SECTIONS` test fixture.

### Spec/contract alignment
- The gap map (`docs/feedback-audits/generic_earnings_pdf_pipeline_gap_map_2026-06-15.md`) classified EDP-007/008/009 as S4 Validator rules, ticker-agnostic. The implementation respects this.
- The concision issue strings use the format `Concision (EDP-NNN): ...` with explicit word/paragraph counts — actionable for the chat widget surface, consistent with other EDP issue strings.

### Defensive concerns (non-blocking, observations only)
- `_check_concision` is invoked *after* `normalize_markdown_headings()` already rewrote the file in place at step 0. This is correct — the concision check sees canonical headings.
- The bold-skip rule in `_count_prose_words` would skip a long bolded prose paragraph (e.g. `**Long paragraph...**` on one line). This is a theoretical edge case, not a real failure mode for the Nami template.

## Kernel proof

```
$ kverify .ced-agent-kernel/specs/t_87366c59.json --base-dir .
VERDICT: READY
All 3 check(s) passed.
- PASS changed file exists: deep_dive_validator.py [path_exists]
- PASS changed file exists: spec_v27_concision.py [path_exists]
- PASS test command succeeds [command_succeeds]: Command exited 0 as expected.
```

## Verdict

**APPROVED.** Concision checks are deterministic, ticker-agnostic, narrowly scoped to the validator seam, and ship with focused regression coverage (9 new tests, 0 regressions in 166-test suite). Kernel strict READY confirms all 3 claims. No production files outside the validator were modified.

Merge recommendation: proceed.
