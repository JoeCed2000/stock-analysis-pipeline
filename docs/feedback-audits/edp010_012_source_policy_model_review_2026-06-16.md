# Review: EDP-010/012 source display policy model (t_e8ebc8a5)

**Parent task:** t_c08616c4
**Reviewer:** reviewer-qa
**Date:** 2026-06-16
**Verdict:** **APPROVED**

## Scope

Independent QA review of the model-level source display policy work for
EDP-010/012. The parent card implemented Option D (hybrid, model-level)
as corrected in the Claude-reviewed spec (t_e7846d85):

- `backend/earnings_deep_dive/report_model.py`: added `SourceDisplayPolicy`
  literal type, plus `source_display_policy` and `table_source_note` fields
  to `RenderedTable`.
- `backend/earnings_deep_dive/mapper.py`: added `_apply_source_display_policy()`
  helper with conservative calculated/unavailable detection, plus
  `_normalize_source_label()` and `_restore_source_display()`. Fixed
  `_enrich_codex_table`, `_number_highlights_rows`, `_sanitize_table` to
  preserve metadata through copies. Wired into `build_earnings_deep_dive_report`
  at line 2930, after all table transformations.
- `tests/spec_v27_source_display_policy.py`: 13 focused tests.
- `.ced-agent-kernel/specs/edp010-012-source-policy-model.json`: 4-check
  Kernel spec (python_compile × 2, command_succeeds × 2).

No `pdf_renderer.py` change. No `/api/` change. No commit performed by the
builder (awaiting independent QA approval).

## Acceptance criteria

The SYMBOL_PLAN requires me to confirm:

1. `source_display_policy` and `table_source_note` are present on `RenderedTable`.
2. `_apply_source_display_policy` locates the Source column by **normalized
   header label**, not by hardcoded index.
3. Calculated / unavailable labels are handled **conservatively** (any
   presence blocks collapse).
4. **No mutation** of rows / cells / source values.
5. Called **after** final table transformations.
6. Focused regression + small relevant bundle pass.
7. `kverify --strict` returns `READY`.
8. No `/api/` or `pdf_renderer` change.

All eight criteria pass (details below).

## Evidence

### 1. Model fields — PASS

`backend/earnings_deep_dive/report_model.py` lines 99 + 111-119:

```python
SourceDisplayPolicy = Literal["row", "table_note", "none"]
...
class RenderedTable(BaseModel):
    columns: list[str]
    rows: list[RenderedTableRow] = Field(default_factory=list)
    # Source display policy — controls how the renderer shows source info.
    # "row": keep visible Source column (default).
    # "table_note": hide visible Source column, render table-level note below.
    # "none": no source note needed.
    source_display_policy: SourceDisplayPolicy = "row"
    table_source_note: str | None = None
```

`Literal` is enforced by Pydantic. Default `"row"` preserves backward
compatibility for callers that don't set the fields. Comment block
documents the contract.

### 2. Source column located by header label, not index — PASS

`mapper.py` lines 1224-1230:

```python
source_col_idx: int | None = None
for i, col in enumerate(table.columns):
    col_lower = col.strip().lower()
    if col_lower in ("source", "sources", "情報源", "出典"):
        source_col_idx = i
        break
```

Header label set is the **normalized** canonical set: EN `source`/`sources`
+ JP `情報源`/`出典`. No hardcoded index. Test `test_no_source_column_keeps_default`
proves the missing-source-column path stays at default `row`.

The cell offset `cell_idx = source_col_idx - 1` (line 1254) is correct
because `_extract_markdown_table` (line 343) builds `RenderedTableRow`
with `label=cells[0]` and `cells=cells[1:]` — i.e. columns[0] is the
row label, columns[1:] are the cell values. Guarded with `if cell_idx < 0:
continue` and `if cell_idx >= len(row.cells): continue` to handle edge
cases (Source as label, or missing trailing cells).

### 3. Conservative calculated / unavailable detection — PASS

`_CALCULATED_LABELS_RAW` and `_UNAVAILABLE_LABELS_RAW` are conservative
string sets. Both EN and JP variants are listed. **Any** match in **any**
row flips `has_calculated` or `has_unavailable` to `True`; either flag
blocks collapse (`has_no_issues = not has_calculated and not has_unavailable`).

Placeholders (`—`, `""`, `n/a`, `?`, `na`) and explicit unavailable
strings ("not disclosed", "unavailable from reviewed sources", "not
applicable", "not calculable", "開示なし", "該当なし", "計算不可",
"データ未取得") all block collapse.

This matches the Claude-review correction that calculated/unavailable
detection should be conservative and based on source-cell labels, not on
grounding. Tests covering this:

- `test_mixed_cash_flow_keeps_row_source` — direct + calculated mix → `row`.
- `test_unavailable_source_does_not_collapse` — unavailable labels → `row`.
- `test_calculated_label_blocks_collapse` — single calculated row blocks.
- `test_missing_source_cell_does_not_collapse` — empty/dash blocks.

### 4. No mutation of rows / cells / source values — PASS

`_apply_source_display_policy` only assigns to two attributes on the
passed-in `table` object: `source_display_policy` and `table_source_note`.
It never reassigns `row.label`, never replaces `row.cells`, never
overwrites `row.cells[cell_idx]`. Test `test_no_mutation_of_rows_or_cells`
enumerates every row and asserts `result_row.label == orig_row[0]` and
`list(result_row.cells) == list(orig_row[1:])`.

The three `RenderedTable` copy helpers (`_enrich_codex_table`,
`_number_highlights_rows`, `_sanitize_table`) were updated to carry the
metadata fields through copies. Tests
`test_sanitize_preserves_metadata` and
`test_number_highlights_preserves_metadata` confirm the metadata round-trips
through the copy chain.

### 5. Wiring — applied after all table transformations — PASS

`mapper.py` line 2930 (inside `build_earnings_deep_dive_report`):

```python
# Apply source display policy after all table transformations complete
table = _apply_source_display_policy(section.key, table)
sections.append(
    RenderedSection(
        key=section.key,
        ...
        table=table,
        ...
    )
)
```

Located **after** every `_sanitize_table`, `_enrich_codex_table`, and
`_number_highlights_rows` call (lines 2754, 2777, 2821, 2847, 2851, 2862)
and after the forward P/E post-processing block (lines 2875-2928). The
resulting `table` is then frozen into the `RenderedSection` and flows to
the PDF renderer untouched.

This matches the Claude-review correction: "policy runs after enrichment /
row numbering / sanitization".

### 6. Allow-list: Operating Metrics, Cash Flow, Capital Efficiency — PASS

`mapper.py` line 1218:

```python
_ALLOW_LIST = {"Operating Metrics", "Cash Flow", "Capital Efficiency"}
```

Non-allow-listed sections short-circuit at line 1220-1221 (return table
unchanged → default `source_display_policy="row"`). Test
`test_non_allowlisted_section_keeps_row` confirms `EPS & Revenue` is not
collapsed.

### 7. Operating Metrics completeness guard — PASS

`mapper.py` lines 1293-1296:

```python
# Operating Metrics: also require that all cells are present (row_count >= 6 typical)
if section_key == "Operating Metrics":
    if row_count < 6:
        return table
```

This prevents a 2-row Operating Metrics stub from accidentally collapsing
on identical source. Combined with the "no calculated, no unavailable"
check, the result is conservative: Operating Metrics collapse requires
≥ 6 rows of identical, clean source. Tests
`test_operating_metrics_collapses_when_complete_and_identical` and
`test_operating_metrics_mixed_source_keeps_row` cover both branches.

### 8. JP / EN label support — PASS

The header label set and both raw-label sets are explicitly bilingual.
Test `test_homogeneous_japanese_labels_collapse` proves
`会社開示 / 計算ベース` source strings with `指標`/`情報源` columns
collapse to `table_note` for the Capital Efficiency section.

### 9. Focused regression — PASS

```
$ PYTHONPATH=. backend/.venv/bin/python -m pytest tests/spec_v27_source_display_policy.py -q
.............                                                            [100%]
13 passed in 0.13s
```

13/13 pass in 0.13s. Coverage spans: homogeneous collapse, mixed
calculated+direct, unavailable blocks, non-allow-listed sections,
missing Source column, calculated label blocks, no-mutation guarantee,
Operating Metrics complete/mixed, JP labels, missing source cell,
metadata preservation through sanitize and number_highlights.

### 10. Bundle regression (small relevant) — PASS

```
$ PYTHONPATH=. backend/.venv/bin/python -m pytest \
    tests/spec_v27_source_display_policy.py \
    tests/spec_v27_fcf_margin_presence.py \
    tests/spec_v27_net_debt_presence.py -q
..........................                                               [100%]
26 passed in 0.18s
```

26/26 pass (13 source policy + 6 FCF margin + 7 net debt). 0 regressions.

### 11. Kernel strict — PASS

```
$ kverify .ced-agent-kernel/specs/edp010-012-source-policy-model.json \
    --base-dir /home/ced/codex-projects/stock-analysis-pipeline
VERDICT: READY
All 4 check(s) passed.
- PASS python compiles: report_model.py [python_compile]
- PASS python compiles: mapper.py [python_compile]
- PASS focused source display tests pass (13 tests) [command_succeeds]
- PASS bundle regression (26 tests, including FCF margin and net debt) [command_succeeds]
```

All 4/4 Kernel checks pass with the persistent pytest commands (no
`/tmp/` scripts).

### 12. Independent normalization round-trip verification — PASS

Ran a one-shot Python check against `_normalize_source_label` and
`_restore_source_display` to confirm the EN/JP mapping is bijective and
complete (8 normalize cases + 6 display-restore cases). All 14 cases
match expected values. This catches drift between the two helpers and
proves the table-note string is human-readable, not the raw normalized
form.

### 13. No `/api/` or `pdf_renderer` change — PASS

```
$ git diff --stat backend/earnings_deep_dive/report_model.py \
    backend/earnings_deep_dive/mapper.py \
    tests/spec_v27_source_display_policy.py
 backend/earnings_deep_dive/mapper.py       | 169 ++++++++++++++++++++++++++++-
 backend/earnings_deep_dive/report_model.py |   9 ++
 tests/spec_v27_source_display_policy.py    | 262 ++++++++++++++ (new)
```

`pdf_renderer.py` and any `api/` or `routers/` paths are not in the diff.
Confirmed by `grep` for `source_display_policy` across the codebase:
only `mapper.py` and `report_model.py` (plus the test file) reference
the new fields. The renderer card is a separate downstream task that
will read the metadata.

## Risks and trade-offs

1. **`_normalize_source_label` and `_restore_source_display` are not
   exhaustive.** A new source label that matches none of the normalize
   branches will fall through to the raw string. The `set` length check
   in step 3 then requires ALL rows to share that exact raw string for
   collapse to happen. This is conservative (over-keep on the Source
   column is safer than under-keep), but it means new source-label
   patterns added by upstream tools will not collapse until the helpers
   are updated. Acceptable for v1; document the extension point in the
   renderer card.

2. **Wiring is at the section loop inside `build_earnings_deep_dive_report`.**
   If a future path constructs `RenderedTable` outside this function
   (e.g. an alternative code path for stub reports), the policy will
   default to `row` (safe). No silent `table_note` without explicit
   allow-list hit.

3. **The cell offset `source_col_idx - 1` is a documented coupling to
   `_extract_markdown_table`'s `cells[1:]` convention.** If that
   convention ever changes (label moved into `cells[0]` rather than
   `label=`), the offset breaks silently. A focused test
   (`test_no_source_column_keeps_default` and the metadata-preservation
   tests) only catches part of this. Future-proof: an integration test
   that runs an end-to-end report and checks the policy fields on every
   table would catch it. The renderer card should add that test.

4. **Operating Metrics `row_count >= 6` guard is heuristic.** A
   genuine 3-row Operating Metrics table would not collapse. This is
   the conservative choice; the alternative is "always allow collapse
   if all 3 rows share a source". Recommend keeping the ≥ 6 guard
   unless a real-world report surfaces a 3-row case.

## Conclusion

The implementation matches the corrected Claude-reviewed spec exactly:

- Model-level fields (Option D).
- Conservative calculated / unavailable detection (not grounding-based).
- Source column located by normalized header label (not hardcoded index).
- No row/cell mutation.
- Applied after enrichment / numbering / sanitization.
- Allow-list respected, with the `row_count >= 6` Operating Metrics guard.
- Bilingual JP/EN support.
- No `/api/` or `pdf_renderer` mutation.

All evidence is reproducible: 13/13 focused tests, 26/26 bundle tests,
4/4 Kernel checks, and 14/14 independent normalization round-trip
verifications. The builder correctly stopped at this gate pending
independent QA — `pdf_renderer.py` changes are out of scope for this
card and will be a separate downstream task that consumes the new
metadata.

**APPROVED.** The parent commit can proceed.
