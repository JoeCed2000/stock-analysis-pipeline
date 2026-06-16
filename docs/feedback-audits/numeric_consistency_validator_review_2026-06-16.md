# EDP-006 Numeric Consistency Validator Checks — Review

**Task:** t_4bf72590 (review of parent t_07932668)
**Reviewed by:** reviewer-qa
**Date:** 2026-06-16
**Verdict:** ✅ **APPROVED**

---

## 1. Scope verification

| File | Status | Role |
|---|---|---|
| `backend/earnings_deep_dive/deep_dive_validator.py` | modified | validator seam — added EDP-006 checks |
| `tests/spec_v27_numeric_consistency.py` | new | focused regression |
| `WIKI.md` | modified | documentation update only |

Out-of-scope files checked, **all clean** (no changes):
- `prompts/`, `analyses/`, `batches/`, `dist/`, `logs/`
- `backend/pipeline.py`, `backend/main.py`, `scripts/render_deep_dive_from_md.py`
- No secrets, no feedback state, no generated PDFs touched.

`.wiki_builder_cache/stock-analysis-pipeline/file_hashes.json` is dirty but is a build cache, not a source artifact — out of approval scope.

## 2. Code review

### 2.1 Wiring
- `_check_numeric_consistency(content)` is called from `validate_deep_dive` as step 5 (between concision and content size), which is the right position — early enough to surface contradictions before structural checks, late enough to avoid noise.
- Return shape of `validate_deep_dive` is preserved (`Tuple[bool, List[str]]`); no caller breaks (`backend/main.py`, `backend/pipeline.py` are the only consumers).
- Module-level constants `EPS_TOLERANCE = 0.03` and `REVENUE_TOLERANCE_RATIO = 0.005` are documented and explicit.

### 2.2 Determinism & ticker-agnosticism
- All parsing is regex-based on the markdown text — no LLM, no network, no environment-dependent lookups. ✅ Deterministic.
- The function only inspects the markdown content passed in. No ticker symbols, no hard-coded company names, no model-specific assumptions. ✅ Ticker-agnostic.
- Regex `\$(\d+(?:\.\d+)?)\s*(B|Billion|billion|M|Million|million)?` and the `\d+...billion/million` fallback are pure string operations. ✅ Ticker-agnostic.

### 2.3 False-positive risk
- Section heading match is a loose substring (`"EPS" in heading and "Revenue" in heading`). I verified empirically that a heading like "EPS Growth & Revenue Quality Commentary" with no table produces **zero** issues because the function returns early when `prose_amounts` is empty AND when the table is absent. Looseness is benign in this direction.
- Comparison references are correctly blocked: phrases `"above the"`, `"below the"`, `"beat the"`, `"surpassed the"` cause the amount to be skipped (verified via `test_consistent_values_in_compact_section_pass` which includes `"above the $12.0B estimate"` and `"topped consensus by $0.14"`).
- Deltas blocked: `"by "` in the 25-char pre-text causes the amount to be skipped.
- Context window for metric classification (20 chars before + 10 chars after) is tight enough to avoid spillover between adjacent dollar amounts on the same line. Verified by inspection against the test fixtures.
- "Revenue minimum tolerance floor" `max(table_rev * 0.005, 5_000_000)` — sensible; a $1B revenue company has $5M absolute floor which is well above typical rounding.

### 2.4 Edge cases I would have liked to see tested
- A second `## EPS & Revenue` section in the same document (parent claims "checks ALL sections, not just first"). Not covered in the focused test, but the loop is straightforward enough that the claim is credible.
- Negative / loss values (e.g. `-$0.05`). The regex does not match a leading `-` — would be silently dropped from prose, which is conservative (a missing value won't be flagged as inconsistent). Acceptable, but worth noting.
- Revenue in millions (e.g. `$650M`) when the table uses billions. The parser scales both forms identically to absolute dollars, so a table `$650M` vs prose `$650M` matches; `$0.65B` vs `$650M` also matches. ✅
- `n/a`, `N/M`, `TBD` placeholders in the table. `_parse_dollar_amount` returns `(None, None)` for cells without `$` or a number+suffix, so such cells produce no table value and prose amounts with no table to compare against are silently ignored (the loop only checks `if table_eps is not None`). ✅ Conservative behaviour.

### 2.5 Code quality
- 4 helper functions, each with a single responsibility (parse table, parse prose, classify context, cross-check). ✅ No bloat.
- A redundant `assert m is not None` after an early `return None, None` is harmless and reads as defensive documentation.
- No copy-paste, no over-abstraction, no leaky magic numbers beyond the documented tolerance constants.

## 3. Verification (independently re-run by reviewer)

| Check | Command | Result |
|---|---|---|
| Focused test | `pytest tests/spec_v27_numeric_consistency.py -q` | 6 passed |
| Full validator regression | `pytest tests/spec_v27_numeric_consistency.py tests/spec_v27_concision.py tests/spec_v27_forbidden_headings.py tests/spec_v27_missing_data_leaks.py tests/test_validator.py tests/spec_v27_verdict_valuation_dq_segments.py tests/spec_v27_period_consistency.py tests/spec_v27_metrics_ledger.py tests/spec_v27_source_registry.py -q` | **172 passed**, 0 failed |
| Module compile | `python_compile backend/earnings_deep_dive/deep_dive_validator.py` | OK |
| Adversarial prose | hand-built EPS=$1.99 vs table $1.23 | flagged with correct message |
| Adversarial heading | heading "EPS Growth & Revenue Quality" with no table | 0 issues (conservative) |
| Kernel | `kverify .ced-agent-kernel/specs/t_4bf72590_code_change_verified.json --base-dir .` | **READY** (4/4) |

## 4. Acceptance criteria

- [x] No production files outside the validator seam were modified.
- [x] New checks are deterministic and ticker-agnostic.
- [x] No secrets / feedback state / analyses / PDFs / prompts / renderer / pipeline files touched.
- [x] Kernel READY proof produced.

## 5. Verdict

**APPROVED.** EDP-006 numeric consistency checks are correctly scoped to the validator seam, deterministic, ticker-agnostic, and ship with 6 focused tests covering the required cases. Independent re-run confirms 172/172 regression and Kernel READY (4/4). Two minor coverage gaps noted (multi-section iteration, negative-EPS) are conservative in the safe direction and do not block merge.

No follow-up tasks created.
