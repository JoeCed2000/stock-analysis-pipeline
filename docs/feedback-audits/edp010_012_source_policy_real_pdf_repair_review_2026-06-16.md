# QA Review — EDP-010/012 source display renderer real-PDF repair (t_4519502c)

**Verdict:** APPROVED
**Reviewer:** reviewer-qa
**Parent task:** t_b46c2953 (fix commit 7a686fa)
**Date:** 2026-06-16

## Acceptance criteria verification

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Fix #1 (src_idx off-by-one) removes per-row source cells in Capital Efficiency table_note | PASS | Real PDF `/tmp/edp01012_pdf_recette/NVDA_earnings_deep_dive_edp01012_recette.txt` lines 238–280 show Capital Efficiency with 5 columns (Metric / TTM FY2027 Q1 / TTM FY2026 Q1 / YoY / Comment). No per-row source values. Each row has exactly 4 data cells after the label. |
| 2 | Fix #2 (label dedup) prevents "Source: Source:" duplication | PASS | Real PDF text line 280 = `Source: SEC Filings (10-Q/10-K) via EDGAR` (single "Source:" prefix). Counted `Source:` = 1 in the rendered note. |
| 3 | Cash Flow table retains Source header and per-row source cells (row policy) | PASS | Real PDF text lines 130–166: 5-column header (Metric / FY2027 Q1 / FY2026 Q1 / YoY / Source) preserved. Per-row source values `SEC 10-Q/K` visible. FCF Margin row keeps `Calculated (FCF ÷ Revenue)` source. |
| 4 | Focused renderer file rerun via backend venv | PASS | `backend/.venv/bin/python -m pytest tests/spec_v27_source_display_renderer.py -v` → 8/8 pass (6 existing + 2 new regression guards). |
| 5 | Real NVDA PDF recette rerun, Capital Efficiency excerpt clean | PASS | Post-fix PDF (`mtime 2026-06-16 10:38:23`, after fix commit at 10:37:41) confirmed clean via text inspection of `/tmp/edp01012_pdf_recette/NVDA_earnings_deep_dive_edp01012_recette.txt`. |
| 6 | kverify strict | PASS | `kverify .ced-agent-kernel/specs/edp010-012-source-policy-renderer.json --base-dir .` → `VERDICT: READY` (6/6 checks: python_compile x2, 8 renderer tests, 13 policy tests, bundle regression, recette verification). |
| 7 | `/api/` untouched; renderer-only | PASS | `git show 7a686fa --stat` shows only `backend/earnings_deep_dive/pdf_renderer.py` + tests + WIKI + kernel spec changed. No `api/`, `mapper`, `model`, or `prompts` paths in the diff. |
| 8 | Branch is on the review path | PASS | `git log --oneline -5` shows 7a686fa on top of `kanban/spec-fonctionnelle-sa` (active review branch). |

## Code review of the diff

### Fix #1 — `k != src_idx+1` → `k != src_idx` (line 870)

**Correctness:** ✓ PASS

The `src_idx` is computed by enumerating `section.table.columns` (line 858–863). At line 830, the renderer builds `row_values = [row.label, *row.cells]`. So `row_data` (= the rows appended to `data`) has `len(columns)` items, with column index 0 = label. The Source cell therefore sits at `row_data[src_idx]`, not `row_data[src_idx+1]`. The `+1` was a genuine off-by-one and would have left the source cell visible (e.g. `SEC 10-Q/K`) in every data row of table_note tables. The fix aligns the row filter with the header filter on line 866 (`j != src_idx`).

**Consistency check:** the header filter on line 866 was already correct (`j != src_idx`); the data-row filter on line 870 is now consistent with it. Both reference the same `src_idx` derived from `section.table.columns`.

**Caveat on commit message wording (MINOR, non-blocking):** the commit message and WIKI say *"row.cells has len(columns)-1 items (column[0]=label), so source cell in row_data is at src_idx"*. This is **functionally correct in its conclusion** but **slightly imprecise about the intermediate step** — `row.cells` itself has `len(columns)-1` items, but `row_data` (= `[row.label, *row.cells]`) has `len(columns)` items. The invariant that holds is: `len(row_data) == len(section.table.columns) == len(stripped_cols)`, so the same `src_idx` indexes both. Future readers may find the intermediate phrasing confusing. **Not blocking** — the code is correct, and a casual reader can verify it from the file.

### Fix #2 — strip leading "Source:" from note (lines 874–878)

**Correctness:** ✓ PASS

```python
note_raw = section.table.table_source_note
NOTE_PREFIX = "source:"
if note_raw.lower().strip().startswith(NOTE_PREFIX):
    note_raw = note_raw.strip()[len(NOTE_PREFIX):].lstrip(":")
```

For the real-world data `"Source: SEC Filings (10-Q/10-K) via EDGAR"`:
- `note_raw.lower().strip()` = `"source: sec filings (10-q/10-k) via edgar"` → starts with `"source:"` ✓
- `note_raw.strip()` = `"Source: SEC Filings (10-Q/10-K) via EDGAR"`
- `note_raw.strip()[7:]` = `" SEC Filings (10-Q/10-K) via EDGAR"` (note the leading space)
- `.lstrip(":")` = `" SEC Filings (10-Q/10-K) via EDGAR"` (no leading colons to strip)
- `_shorten_source(" SEC Filings (10-Q/10-K) via EDGAR".strip())` = `SEC Filings (10-Q/10-K) via EDGAR`
- Final render: `<b>Source:</b> SEC Filings (10-Q/10-K) via EDGAR` ✓

**Edge case note (MINOR, non-blocking):** `lstrip(":")` strips *all* leading colons. For pathological inputs like `"Source:: double colon foo"`, it would strip both. For the real data shape ("Source: SEC Filings...") it's fine. The data model contract enforces a single colon prefix, so this is acceptable.

## Test evidence

- `tests/spec_v27_source_display_renderer.py` — 8/8 pass (2 new regression guards):
  - `test_table_note_removes_row_source_cells` — guards Fix #1, plus asserts Cash Flow row policy still keeps source cells.
  - `test_table_source_note_no_duplicate_label` — guards Fix #2.
- `tests/spec_v27_source_display_policy.py` — 13/13 pass (no model regression).
- `tests/spec_v27_fcf_margin_presence.py` — 6/6 pass.
- `tests/spec_v27_net_debt_presence.py` — 7/7 pass.
- `tests/spec_v27_pdf_renderer.py` — 36/36 pass.
- `tests/test_earnings_pdf_renderer.py` — 5/5 pass.
- **Total: 75/75** (parent claimed 70; actual count is 75 across the 6 listed files — minor count discrepancy in the parent summary, not a substantive issue).

## Real PDF evidence (post-fix)

PDF generated 2026-06-16 10:38:23, fix committed 10:37:41. The PDF is the **post-fix artifact**.

Capital Efficiency (table_note policy) — `/tmp/edp01012_pdf_recette/NVDA_earnings_deep_dive_edp01012_recette.txt` lines 238–280:
- Header: `Metric | TTM Ending FY2027 Q1 | TTM Ending FY2026 Q1 | YoY | Comment` (5 columns, Source column removed) ✓
- 6 data rows × 4 cells (label + 4 data), no per-row source values ✓
- Single trailing line: `Source: SEC Filings (10-Q/10-K) via EDGAR` (one "Source:" prefix) ✓

Cash Flow & Liquidity (row policy) — same file lines 130–166:
- Header: `Metric | FY2027 Q1 | FY2026 Q1 | YoY | Source` (5 columns, Source header preserved) ✓
- 6 data rows × 5 cells including source ✓
- `Operating cash flow` row: `$50.3B | $27.4B | +83.6% | SEC 10-Q/K` (shortened source) ✓
- `FCF Margin` row: `+59.5% | +59.4% | +0.0 pts | Calculated (FCF ÷ Revenue)` ✓

## Risks / observations (non-blocking)

1. **Documentation wording on row.cells length (MINOR):** WIKI.md and commit message phrase the off-by-one reasoning as "row.cells has len(columns)-1 items (column[0]=label)". The accurate invariant is "row_data has len(columns) items, with index 0 = label, and src_idx indexes both row_data and section.table.columns". The code is correct; the narrative could mislead a future reader. Not blocking — the new regression tests pin the behavior.

2. **Test count discrepancy (MINOR):** Parent summary says "70 tests" — actual is 75 across the 6 listed files. Doesn't affect the verdict (all pass), but the parent metadata under-reports by 5.

3. **No /api/ changes confirmed:** verified via `git show 7a686fa --stat` — only renderer, tests, WIKI, kernel spec.

## Decision

**APPROVED.** Both bugs are correctly fixed at the algorithm level, the regression tests pin the behavior, the real NVDA PDF (post-fix) shows the expected output, and kverify strict returns READY 6/6. The parent task is reviewer-ready.
