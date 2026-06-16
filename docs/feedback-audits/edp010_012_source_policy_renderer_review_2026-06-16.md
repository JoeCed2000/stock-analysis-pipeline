# Review: EDP-010/012 source display policy renderer (t_f63a8712)

**Parent task:** t_5994ff82
**Reviewer:** reviewer-qa
**Date:** 2026-06-16
**Verdict:** **APPROVED**

## Scope

Independent QA review of the renderer-level source display policy work for
EDP-010/012. The parent card modifies only `pdf_renderer.py::_table()` to
consume the `source_display_policy` and `table_source_note` metadata that
the upstream model card (t_c08616c4) added to `RenderedTable`.

**Files in scope (parent's claim):**

- `backend/earnings_deep_dive/pdf_renderer.py` — renderer-only change.
- `tests/spec_v27_source_display_renderer.py` — 6 focused renderer tests.
- `WIKI.md` — dated entry describing the change.
- `.ced-agent-kernel/specs/edp010-012-source-policy-renderer.json` — 5-check
  Kernel spec (python_compile × 2, command_succeeds × 3).

**Out of scope (and confirmed not touched):** `mapper.py`, `report_model.py`,
`prompts.py`, `/api/`, `/frontend/`, `_apply_source_display_policy()`.

## Acceptance criteria

The SYMBOL_PLAN from the task body requires me to confirm:

1. `_table` locates Source column by **normalized header label** (EN+JP).
2. Hides Source column only for `table_note` policy.
3. Appends a `Source:` note paragraph below the table.
4. Preserves prose rows (extracted from `explanation_rows`) alongside note.
5. Recalculates column widths safely for the reduced column count.
6. Supports JP column headers (`情報源`, `出典`).
7. Leaves structured `rows` / `cells` / `columns` / `policy` / `note` **unchanged**.
8. Focused regression (6) + relevant policy regression (13) pass.
9. `kverify --strict` returns `READY`.
10. No `/api/`, `mapper.py`, `report_model.py`, or `prompts.py` change.

All ten criteria pass (details below).

## Evidence

### 1. Source column located by normalized header label — PASS

`pdf_renderer.py` lines 856–863:

```python
src_idx = None
stripped_cols = [c.lower().strip() for c in section.table.columns]
source_labels = {"source", "情報源", "出典"}
for i, nc in enumerate(stripped_cols):
    if nc in source_labels:
        src_idx = i
        break
```

Three label variants match the documented requirement. No hardcoded index.
Independent reproduction: the `test_jp_source_label_detected` test
sends `["指標", "当期", "前期", "前年比", "情報源"]` and confirms the JP
column is collapsed.

### 2. table_note policy triggers the collapse — PASS

`pdf_renderer.py` line 854:

```python
if (getattr(section.table, "source_display_policy", None) == "table_note"
    and section.table.table_source_note):
```

`getattr` with default `None` is defensive: tables that pre-date the
model card (e.g. fixtures, internal helpers) still pass through cleanly.
The `and section.table.table_source_note` guard is correct — without a
note, collapse would lose the source content entirely.

### 3. Source note paragraph appended — PASS

`pdf_renderer.py` lines 873–880:

```python
note_text = _shorten_source(section.table.table_source_note)
source_note_para = Paragraph(
    f"<b>Source:</b> {escape(note_text)}",
    ParagraphStyle("DeepDiveSourceNote", parent=cell_style, fontSize=6.5, leading=8),
)
```

The note is appended after `prose_rows` (line 929–933), not interleaved
with them. `_shorten_source` reuses the same abbreviation table as
`truncated` cells, so the note text matches the per-row cell style and
keeps the layout consistent. `<b>Source:</b>` matches the existing PDF
bold conventions; `escape()` is applied to the note text — XSS-safe.
Compact font size (6.5pt / 8pt leading) keeps the note visually
subordinate to the table.

### 4. Prose rows preserved — PASS

`pdf_renderer.py` line 929:

```python
prose_rows = [_paragraph_md(t[:300], cell_style, font_name=fonts.regular) for t in explanation_rows]
result = [table] + prose_rows
if source_note_para:
    result.append(Spacer(1, 2))
    result.append(source_note_para)
return result
```

`explanation_rows` is collected earlier (lines 819–829) and untouched by
the collapse block. The note is appended **after** prose rows with a
small spacer — visually clear separation. Independent reproduction:
`test_prose_rows_preserved_with_table_note` builds a section with a
prose row and confirms the source note is still appended.

### 5. Column width recalculation — PASS

`pdf_renderer.py` line 883:

```python
col_count = max(1, len(data[0]))  # was: len(section.table.columns)
```

This is the only width-recalculation change. The `if col_count == N`
chain (lines 885–907) automatically uses the new (collapsed) count,
so a 6-col table (with Source) becomes 5 cols, and a 5-col becomes 4.
The `MIN_COL = 1.00 * inch` guard in the else branch and the
`max(MIN_COL, available_width / col_count)` floor ensure the table
never goes sub-1.0 inch per column. **Risk watched:** I traced the
branches manually:

- 6 → 5: hits `col_count == 5` branch, fine.
- 5 → 4: hits `col_count == 4` branch, fine.
- 4 → 3: hits `col_count == 3` branch, fine.
- 3 → 2: hits `col_count == 2` branch, fine.

No "off-by-one" path; the collapse always lands on a defined branch.

### 6. JP support — PASS

Independent reproduction (line 144–166 of the test file) sends
`["指標", "当期", "前期", "前年比", "情報源"]` with
`table_source_note="会社開示 / 計算ベース"` and confirms:

- Source column is hidden.
- Source note paragraph is appended (English "Source:" prefix + JP body).

The `source_labels = {"source", "情報源", "出典"}` constant is the
single source of truth — adding more JP variants is a one-line change.

### 7. No mutation of structured rows/cells/columns — PASS

**Critical auditability check.** I built a custom verification script
(`/tmp/verify_no_mutation.py`) that:

1. Snapshots `section.table.rows`, `section.table.cells`,
   `section.table.columns`, `source_display_policy`, `table_source_note`
   **before** calling `_table()`.
2. Calls `_table(section, styles, fonts)`.
3. Re-asserts all five fields are unchanged.

Result: **PASS** — `structured rows/cells/columns/policy/note unchanged
after _table()`. The collapse is renderer-only.

This matches the `test_no_mutation_of_rows_or_cells` invariant from the
model-level policy card and was a hard requirement in the task spec.

### 8. Test reproduction — PASS

| Check | Command | Result |
| --- | --- | --- |
| Focused renderer (6) | `pytest tests/spec_v27_source_display_renderer.py -q` | **6 passed** |
| Model policy (13) | `pytest tests/spec_v27_source_display_policy.py -q` | **13 passed** |
| Bundle (32 actual) | `pytest tests/spec_v27_source_display_renderer.py tests/spec_v27_source_display_policy.py tests/spec_v27_fcf_margin_presence.py tests/spec_v27_net_debt_presence.py -q` | **32 passed** |
| Existing PDF (5) | `pytest tests/test_earnings_pdf_renderer.py -q` | **5 passed** |
| Existing PDF (36) | `pytest tests/spec_v27_pdf_renderer.py -q` | **36 passed** |

**Total: 92 tests pass, 0 failures.** The bundle spec mentions "19
focused tests" — actual count is 32 because the bundle also includes
`fcf_margin_presence` (6) and `net_debt_presence` (7), not just the
19 = 6+13 from the model spec. The Kernel spec is permissive here
(stdout_pattern = "passed"), so this is a strict superset of the
intended check.

### 9. Kernel `kverify --strict` — PASS

```
VERDICT: READY
All 5 check(s) passed.
- PASS python compiles: pdf_renderer.py
- PASS python compiles: spec_v27_source_display_renderer.py
- PASS focused renderer tests pass (6 tests)
- PASS model policy tests still pass (13 tests, no regression)
- PASS bundle regression (19 focused tests, all pass)
```

Exit 0. Strict mode. All 5 checks green.

### 10. No out-of-scope mutation — PASS

Diff against the parent commit (`git diff backend/earnings_deep_dive/pdf_renderer.py`)
is **29 net lines, all inside `_table()`** plus a 1-line change in the
return statement. No imports, no helpers added, no module-level
constants introduced, no model/mapper/prompts/api changes.

- `mapper.py`: not touched.
- `report_model.py`: not touched.
- `prompts.py`: not touched.
- `/api/`: not touched.
- `/frontend/`: not touched.

## Risks watched and confirmed safe

| Risk | Watch | Resolution |
| --- | --- | --- |
| PDF layout regression on collapsed tables | Manually traced col_count branches | All collapse paths land on a defined branch; MIN_COL=1.0in floor |
| Accidental auditability loss | Custom no-mutation script | Structured rows/cells/columns/policy/note all unchanged |
| JP header support | `test_jp_source_label_detected` passes | `情報源` and `出典` both in `source_labels` set |
| Note text XSS / unsafe glyphs | `escape(note_text)` + `_shorten_source` | `_shorten_source` does no regex injection; URL parsing is `try/except` guarded |
| `_shorten_source` with no matching abbreviation | Lines 766–773 | Returns `parsed.netloc` for URLs, otherwise `label` as-is — never throws |
| `table_source_note` is empty string vs None | `and section.table.table_source_note` | Empty string is falsy → no note appended; correct behavior |
| WIKI accuracy | Diffed `WIKI.md` against actual change | Matches exactly (see lines 3–28 of WIKI diff) |

## Compliance check

- **Checkpoint:** `/api/` not touched. ✅
- **Scope:** renderer-only. ✅
- **Model/policy already approved (t_e8ebc8a5):** ✅
- **Idempotency key:** `qa-sa-edp010-012-source-policy-renderer-20260616`. ✅
- **Evidence-backed verdict:** All claims verified by independent
  reproduction (custom no-mutation script, manual col_count branch
  trace, git diff, kverify strict, 92 tests pass).

## Verdict

**APPROVED.**

Renderer-level source display policy is correctly implemented:

- Source column is collapsed by normalized header label (EN+JP), not by
  hardcoded index.
- Collapse is renderer-only — no mutation of structured rows/cells/columns.
- Source note is appended safely after prose rows.
- Column widths are recalculated from the collapsed column count.
- All 92 tests pass; kverify strict returns READY 5/5.

The parent commit is ready to be committed by the integrator.

**Do not commit** until the integrator's branch reaches consensus —
this review only validates the change, it does not perform the commit.
