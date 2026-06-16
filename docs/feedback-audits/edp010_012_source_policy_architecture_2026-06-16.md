# EDP-010 / EDP-012 — Source Column Display Policy Architecture

Date: 2026-06-16
Project: Stock Analysis Pipeline
Task: t_c6ffc957; repair task: t_e7846d85
Status: architecture spec only — Claude CHANGES_REQUIRED corrections integrated; no implementation performed
Owner lane: architect-spec

## 1. Executive decision

EDP-010 and EDP-012 are not validator-only fixes. They are a shared source-display policy problem across the Earnings Deep Dive prompt contract, structured report model, mapper, and PDF renderer.

Recommended implementation path: HYBRID COLLAPSE AT RENDER/MODEL BOUNDARY.

- Keep machine-level row provenance in the structured model so auditability and validator checks remain possible.
- Collapse the visible PDF `Source` column only when every row in a table has the same non-placeholder source.
- Keep visible row-level source provenance when rows differ, when calculated rows are mixed with direct metrics, or when the table contains missing/unavailable provenance.
- Prefer changing `RenderedTable` metadata and `pdf_renderer.py` display logic before changing LLM prompt headers. Prompt-level removal is riskier because it can reduce source discipline in LLM output.

This produces the user-facing improvement requested by EDP-010/012 without weakening the current source traceability architecture.

## 2. Scope and stop line

### In scope for this spec

- Compare source-display policy options.
- Identify exact future implementation files and symbols.
- Define acceptance criteria and false-positive risks.
- Define migration, validation, and rollback plan.
- Preserve current source/claim auditability.
- Integrate Claude critique corrections from task `t_e7846d85`.
- Persist a separate Claude critique summary artifact.

### Out of scope for this card

- No code edits.
- No `/api/` endpoint changes.
- No PDF regeneration.
- No prompt rewrite beyond future recommendations.
- No source provider changes.

## 3. Evidence gathered

### 3.1 WIKI_EVIDENCE

Read: `WIKI.md`.

Current state relevant to this spec:

- Validator-only EDP slices are already implemented and verified for EDP-004/011, EDP-007/008/009, EDP-006, EDP-013, EDP-001/003, and EDP-014.
- WIKI records a strong pattern: deterministic validators are used where the defect can be proven from rendered content.
- WIKI line set around recent EDP work confirms EDP-013 and EDP-014 now focus on Capital Efficiency / Cash Flow table rows, and those validators must not be broken by a presentation-only source display change.

### 3.2 GAP_MAP_EVIDENCE

Read: `docs/feedback-audits/generic_earnings_pdf_pipeline_gap_map_2026-06-15.md`.

Important mapped seams:

- EDP-010: profitability source-column repetition is mapped to prompt schema + renderer + product decision.
- EDP-012: cash-flow and balance-sheet source-column repetition shares the same policy problem.
- Existing Task 6 recommendation already names future write scope: `prompts.py`, `pdf_renderer.py`, `report_model.py`, and possibly `mapper.py`.
- The prior gap map states the acceptance shape: common-source table renders with a single table-level source note; mixed-source table keeps row-level provenance.

### 3.3 GRAPH_EVIDENCE

CodeGraph status:

- Project index: 325 files, 7,566 nodes, 15,197 edges; index up to date.
- `RenderedTableRow` impact: `report_model.py`, `mapper.py`, `_extract_markdown_table`, `_enrich_codex_table`, `_number_highlights_rows`, `_sanitize_table`, `build_earnings_deep_dive_report`.
- `RenderedTable` query identifies the same model/mapper integration points plus tests importing the model.
- `_source_descriptor` exists in `mapper.py` but CodeGraph reports no callers. This is a useful future seam for richer row provenance, but adopting it is an implementation task, not part of this spec.

### 3.4 SYMBOL_PLAN_EVIDENCE

Current exact symbols/lines observed:

- `backend/earnings_deep_dive/prompts.py`
  - `TABLE_REQUIREMENTS`: `Operating Metrics`, `Cash Flow`, and `Capital Efficiency` all include visible `Source` in the required table header.
  - `_period_table_header(section, quarter)`: rewrites period columns for `Operating Metrics` and `Cash Flow` while preserving `Source`.
  - `_base_prompt(...)`: injects the section-specific `table_header` into `SECTION_FORMATS` / `EN_SECTION_FORMATS`.
- `backend/earnings_deep_dive/report_model.py`
  - `RenderedTableRow`: currently stores `label`, `cells`, optional `source_field`, `source_value_raw`, and `grounding`.
  - `RenderedTable`: currently stores only `columns` and `rows`.
- `backend/earnings_deep_dive/mapper.py`
  - `_rows_for_section(...)`: constructs row lists with final `Source` cells for `Operating Metrics`, `Cash Flow`, and `Capital Efficiency`.
  - `_source(...)` and `_localized_source(...)`: produce display labels such as company/SEC/yfinance/calculated labels.
  - `_source_descriptor(...)`: richer source metadata helper exists but is currently unused.
  - `_enrich_codex_table(...)`, `_number_highlights_rows(...)`, `_sanitize_table(...)`: preserve `RenderedTable` through downstream transformations.
- `backend/earnings_deep_dive/pdf_renderer.py`
  - `_table(section, styles, fonts)`: builds the visible PDF table, detects columns containing `source`, shortens source labels, and sets column widths based on column count.
  - Current renderer has no table-level source-note path inside `_table(...)`.
  - Claude correction: do not reference `_section_table_flowables(...)`; it is not present in the active renderer.

## 4. Problem statement

The current system treats source provenance as a visible row-level table column for nearly every Earnings Deep Dive table. This is safe for auditability but creates repetitive PDF output when all rows in a table share the same provenance.

The defect is presentation-level, not data-level:

- Data provenance must remain available.
- Claim/source auditability must remain available.
- The visible PDF should not waste a full column repeating the same source label five or six times.

This affects:

- EDP-010: Operating Metrics / profitability tables.
- EDP-012: Cash Flow and Capital Efficiency / balance-sheet-adjacent tables.

## 5. Options compared

### Option A — Keep row-level Source columns everywhere

Description:
Keep existing prompt, model, mapper, and renderer behavior.

Pros:

- Lowest implementation risk.
- Maximum visible provenance per row.
- No prompt/model/test migration.
- Existing validators and tests remain stable.

Cons:

- Does not solve EDP-010/012.
- Keeps PDF visual noise and unnecessary column width pressure.
- Repeated source labels make financial tables harder to read.

Verdict: rejected. Safe but fails the requirement.

### Option B — Remove Source columns from prompt contracts and always render table-level notes

Description:
Change `TABLE_REQUIREMENTS` and section prompt formats so affected tables no longer request a `Source` column. Add a table-level note such as `Source: Company filings / Yahoo Finance`.

Pros:

- Cleanest visible tables when provenance is homogeneous.
- Reduces PDF table width pressure.
- Makes source note explicit at table level.

Cons:

- Highest auditability risk: LLM output may stop attaching source evidence per row.
- Mixed-source rows become ambiguous unless a new row-footnote mechanism is designed immediately.
- Requires broad prompt contract changes in both EN and JP formats.
- Breaks tests that expect prompt/table schemas with `Source`.
- Makes calculated rows such as `FCF Margin` harder to distinguish from direct metric rows.

Verdict: rejected as first implementation. It may be considered later after model-level provenance is fully normalized.

### Option C — Renderer-only collapse based on homogeneous visible Source cells

Description:
Keep prompt and mapper output unchanged. In `pdf_renderer.py`, inspect the rendered table. If the last column is `Source` and all non-placeholder source cells are identical, remove that visible column and append a note below the table.

Pros:

- Smallest code change.
- Preserves prompt discipline and row source values upstream.
- Solves the common-source visual repetition case.
- Easy rollback: remove renderer helper.

Cons:

- Renderer must infer policy from strings, which is fragile across JP/EN labels.
- No explicit model contract says the collapse happened.
- Test coverage must be careful to avoid false collapses on mixed `Calculated` / `Company` / `Yahoo` rows.

Verdict: acceptable as a minimal first slice, but not the preferred long-term shape.

### Option D — Hybrid model-level source display policy (recommended)

Description:
Add explicit source-display metadata to `RenderedTable` while preserving row-level data. Mapper computes whether the visible table source policy is homogeneous, mixed, or unavailable. Renderer consumes that metadata.

Suggested model fields:

```python
class RenderedTable(BaseModel):
    columns: list[str]
    rows: list[RenderedTableRow] = Field(default_factory=list)
    source_display_policy: Literal["row", "table_note", "none"] = "row"
    table_source_note: str | None = None
```

Claude correction: these fields define display intent only. They must not mutate `rows`, `cells`, or source values. The renderer may hide a visible Source column only at render time when `source_display_policy == "table_note"`; structured row data must remain intact for audits and future validators.

Policy semantics:

- `row`: keep visible Source column.
- `table_note`: hide visible Source column and render `Source: <label>` below the table.
- `none`: no source note; only for tables with no source column and no source requirement.

Pros:

- Preserves auditability in the model and mapper.
- Makes renderer behavior deterministic and testable.
- Lets future validators inspect intended policy without parsing PDF layout.
- Supports phased migration: mapper can compute metadata while prompt contract stays unchanged.

Cons:

- Touches model, mapper, renderer, and tests.
- Requires migration of helper functions that copy `RenderedTable` so metadata is not dropped.

Verdict: recommended target architecture.

## 6. Recommended policy rules

### 6.1 Collapse rules

A table may render a table-level source note only when all conditions are true:

1. The table has a visible `Source` column.
2. Every data row has a non-empty, non-placeholder source value.
3. After normalization, all source values are identical.
4. No row is calculated unless every row is calculated from the same formula family. Phase 1 must detect calculated rows from conservative source-cell labels such as `Calculated`, `Calculated (FCF ÷ Revenue)`, `計算値`, and `計算値（FCF ÷ 売上高）`, because current `RenderedTableRow.grounding` is optional and is not reliably populated through mapper transformations.
5. No row contains a missing-data source label such as `Not disclosed`, `Unavailable from reviewed sources`, `開示なし`, `計算不可`, `Not available`, or dash-only placeholders.
6. The section is in the allow-list for this policy: `Operating Metrics`, `Cash Flow`, `Capital Efficiency`.
7. The source column is located by normalized header label, not by a hardcoded last-column index.
8. The policy helper has run after deterministic enrichment, row numbering, and table sanitization, so it evaluates final display cells.

### 6.2 Keep row-level source rules

Keep the visible Source column when any condition is true:

- Sources differ by row.
- At least one row is calculated and another row is direct-provider sourced.
- Any row has missing/unavailable provenance.
- The source label is a generic placeholder.
- The table comes from LLM markdown extraction and cannot be trusted as structured metric rows.
- The section is not explicitly allow-listed.

### 6.3 Section-specific recommendations

#### Operating Metrics — EDP-010

Conservative default: table-level source note only when all expected Operating Metrics rows are present and all source cells are present, non-placeholder, and identical after conservative normalization.

Reason:
Most profitability rows (`Revenue`, `Gross Profit`, `Gross Margin`, `OpEx`, `Operating Income`, `Operating Margin`, `Net Income`) are built from the same financial metric source family in `_rows_for_section(...)`, but the PDF must not collapse a partial or mixed table just because the visible subset happens to share one source.

Exception:
If rows are missing, if source cells are unavailable/placeholders, or if future rows mix transcript/commentary, consensus, or calculated values, keep row-level source.

#### Cash Flow — EDP-012

Likely default: row-level source unless homogeneous.

Reason:
Current Cash Flow rows include direct metrics (`OCF`, `CapEx`, `FCF`, cash/marketable securities, net cash/debt) plus a calculated `FCF Margin` row whose source is explicitly `Calculated (FCF ÷ Revenue)`. That is mixed provenance and should not be collapsed into a single company-source note.

Optional future refinement:
Support `Source: Company filings unless noted; FCF Margin calculated as FCF ÷ Revenue` as a table note plus row exception markers. This is more complex and should not be first slice.

#### Capital Efficiency — EDP-012

Likely default: table-level source note when all direct ratio/allocation rows share the same source.

Reason:
`ROE`, `ROTCE`, `ROA`, `ROIC`, buybacks, and dividends are usually from the same company/financial metrics source family.

Exception:
If all metrics are unavailable and the fallback row says `Finnhub free tier limit`, do not collapse; keep visible row-level explanation.

## 7. Future implementation plan

### Phase 1 — Low-risk model/renderer policy

Files:

- `backend/earnings_deep_dive/report_model.py`
- `backend/earnings_deep_dive/mapper.py`
- `backend/earnings_deep_dive/pdf_renderer.py`
- focused tests under `tests/`

Implementation outline:

1. Add `source_display_policy` and `table_source_note` to `RenderedTable`.
2. Add mapper helper, proposed name: `_apply_source_display_policy(section_key: str, table: RenderedTable) -> RenderedTable`.
3. Preserve existing deterministic transformations first: `_enrich_codex_table(...)`, `_number_highlights_rows(...)`, then `_sanitize_table(...)`.
4. Add mapper helper, proposed name: `_apply_source_display_policy(section_key: str, table: RenderedTable) -> RenderedTable`, and call it only after enrichment, row numbering, and sanitize have produced final display cells.
5. Helper locates the source column by normalized header label, normalizes labels, detects calculated/unavailable labels conservatively, and sets policy to `table_note` only for homogeneous allow-listed tables. It must not mutate row labels or cell values.
6. Ensure all table-copying helpers preserve `source_display_policy` and `table_source_note`.
7. Update `_table(section, styles, fonts)` to hide the visible Source column when `section.table.source_display_policy == "table_note"`, then append a small note paragraph below the table.
8. Keep prompt `TABLE_REQUIREMENTS` unchanged in Phase 1.

### Phase 2 — Optional prompt/schema cleanup after validation

Files:

- `backend/earnings_deep_dive/prompts.py`
- `backend/earnings_deep_dive/mapper.py`
- validator tests if needed

Only consider after Phase 1 proves stable on generated PDFs.

Potential change:
Keep `Source` in prompt contracts for LLM discipline, but add a language rule: `If all rows share the same source, still populate row sources; the PDF renderer may collapse them into a table note.`

Do not remove `Source` from prompt headers until row provenance is fully represented in structured metadata independent of LLM table cells.

## 8. Acceptance criteria for the future builder card

Functional acceptance:

- Homogeneous-source `Operating Metrics` table renders without a visible repeated `Source` column and includes one table-level source note.
- Homogeneous-source `Capital Efficiency` table renders without a visible repeated `Source` column and includes one table-level source note.
- Mixed-source `Cash Flow` table keeps visible row-level provenance when `FCF Margin` is calculated but other rows are direct metrics.
- Mixed `Company / Yahoo / Calculated / Unavailable` source labels never collapse into a single source note.
- JP and EN source labels both work.
- Source legend / claim-source appendix remains unchanged.
- Source-column collapse is presentation-only: structured `RenderedTable.rows[*].cells` and row-level source values remain available after rendering.
- No `/api/` endpoint behavior changes.

Audit acceptance:

- Structured table row provenance remains available after rendering policy is applied; renderer-level column hiding must not delete model data.
- `claim_sources` and `source_registry` remain unchanged.
- The PDF visibly preserves provenance either as a row-level source or as a table-level note.
- The generated PDF must not contain a table with neither row-level source nor table-level source note when source data exists.

## 9. False-positive / false-collapse risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| `Calculated` row collapsed under `Company disclosure` | Misrepresents formula-derived metrics as direct source facts | Treat calculated rows as mixed unless every row is calculated from same formula family |
| Placeholder source collapsed | Hides missing provenance | Block collapse on `Not disclosed`, `Unavailable`, `開示なし`, `計算不可`, `N/A`, dash variants |
| JP labels normalize incorrectly | May collapse unrelated source labels | Use conservative normalization; only collapse exact normalized matches after known translation mapping |
| Renderer-only string parsing hides a column incorrectly | PDF loses visible evidence | Prefer explicit `RenderedTable` metadata; tests must inspect generated PDF text |
| LLM markdown table has hallucinated source cells | Table note could amplify hallucination | Only apply policy to mapper-built structured tables or sections with trusted rows; keep row policy for uncertain extraction |
| Helper drops metadata during table transformations | Policy silently disappears or applies inconsistently | Add tests around `_enrich_codex_table`, `_number_highlights_rows`, `_sanitize_table` preservation |
| Policy relies on unpopulated `grounding` | Calculated rows may be misclassified as direct-provider rows | Phase 1 uses source-cell calculated labels; structured grounding can become a later enhancement |
| Hardcoded Source column index | Future prompt/table changes may hide the wrong column | Locate source column by normalized header label and test non-last-column fixtures |

## 10. Validation command plan for future implementation

Focused unit tests to add:

- `tests/spec_v27_source_display_policy.py`
  - homogeneous Operating Metrics collapses to table note.
  - mixed Cash Flow with calculated FCF Margin keeps row Source column.
  - homogeneous Capital Efficiency collapses.
  - missing/unavailable source does not collapse.
  - JP source labels do not false-collapse unless exact normalized labels match.
  - table transformations preserve `source_display_policy` and `table_source_note`.
  - source column detection works when `Source` is not the final column.
  - source-display policy does not mutate row labels or cell values.
  - calculated labels block collapse even when `RenderedTableRow.grounding` is not populated.
  - Operating Metrics collapses only when the expected row set is complete and source-identical.

Renderer/PDF validation:

```bash
cd /home/ced/codex-projects/stock-analysis-pipeline
PYTHONPATH=. backend/.venv/bin/python -m pytest tests/spec_v27_source_display_policy.py -q
PYTHONPATH=. backend/.venv/bin/python -m pytest tests/spec_v27_pdf_renderer.py tests/test_source_granularity.py tests/test_source_granularity_integration.py -q
PYTHONPATH=. backend/.venv/bin/python -m py_compile backend/earnings_deep_dive/report_model.py backend/earnings_deep_dive/mapper.py backend/earnings_deep_dive/pdf_renderer.py
```

PDF text extraction check:

```bash
PYTHONPATH=. backend/.venv/bin/python <repo-persistent-script>  # generate fixture PDF and extract with PyMuPDF
```

Expected assertions for extracted PDF text:

- Homogeneous fixture: `Source:` note exists once below the table; repeated source cell text does not appear once per row.
- Mixed fixture: `Source` column remains visible; `Calculated (FCF ÷ Revenue)` remains tied to FCF Margin row.
- Auditability fixture: model-level row cells still contain source values after renderer-level collapse; only the PDF display hides the repeated column.

Bundle regression recommendation:

```bash
PYTHONPATH=. backend/.venv/bin/python -m pytest \
  tests/spec_v27_source_display_policy.py \
  tests/spec_v27_pdf_renderer.py \
  tests/test_source_granularity.py \
  tests/test_source_granularity_integration.py \
  tests/spec_v27_fcf_margin_presence.py \
  tests/spec_v27_net_debt_presence.py -q
```

Kernel gate recommendation:

```bash
kverify .ced-agent-kernel/specs/<future-task-id>.json --base-dir /home/ced/codex-projects/stock-analysis-pipeline
```

## 11. Rollback plan

If PDF output loses provenance or tests reveal false-collapse:

1. Revert renderer collapse behavior first; this restores visible row-level Source columns.
2. Leave model fields in place only if backward-compatible and unused; otherwise revert model + mapper metadata together.
3. Keep prompt `TABLE_REQUIREMENTS` unchanged during Phase 1 so rollback does not require prompt migration.
4. Re-run PDF renderer tests and source granularity tests.
5. Regenerate the affected PDF and verify extracted text includes row-level Source again.

Expected rollback blast radius is small if Phase 1 avoids prompt header changes.

## 12. Builder card template

Suggested future title:

`Implement EDP-010/012 hybrid source display policy for Earnings Deep Dive tables`

Suggested assignee:

`python-builder`

Suggested write scope:

- `backend/earnings_deep_dive/report_model.py`
- `backend/earnings_deep_dive/mapper.py`
- `backend/earnings_deep_dive/pdf_renderer.py`
- `tests/spec_v27_source_display_policy.py`
- existing focused tests only if they need expected-output updates

Suggested reviewer:

`reviewer-qa`, with explicit requirement to generate/extract a fixture PDF.

Suggested risk:

Medium. The code change is not large, but provenance semantics are client-facing and must be verified in both model and final PDF text.

## 13. Claude critique integration

Status: CHANGES_REQUIRED from Claude critique; corrections integrated by task `t_e7846d85`.

Critique artifact: `docs/feedback-audits/edp010_012_source_policy_claude_review_2026-06-16.md`.

Substance approved:

- Option D remains the recommended target.
- Prompt-level source removal remains out of Phase 1.
- Mixed direct/calculated rows must keep visible row-level provenance.

Corrections integrated into this spec:

- Renderer target is `_table(section, styles, fonts)`, not `_section_table_flowables(...)`.
- Phase 1 calculated-row detection cannot depend on `RenderedTableRow.grounding` being populated; use conservative source-cell labels first.
- Apply policy after enrichment, row numbering/highlight numbering, and sanitization.
- Locate Source column by normalized header label, not hardcoded index.
- Source-display policy must never mutate rows/cells.
- Operating Metrics collapse only when expected rows are complete and source-identical.
- Add auditability regression coverage proving model-level source data survives renderer collapse.

## 14. Final recommendation

Implement Option D in Phase 1: explicit model-level source display policy with renderer consumption, while keeping prompt row-source contracts unchanged.

This is the safest path because it improves PDF readability while preserving row-level source provenance, source registry behavior, and future validator visibility.
