# Claude critique — EDP-010 / EDP-012 source display policy

Date: 2026-06-16
Project: Stock Analysis Pipeline
Reviewed artifact: `docs/feedback-audits/edp010_012_source_policy_architecture_2026-06-16.md`
Review source: Claude / Anthropic CLI external critique, summarized from parent task handoff
Verdict: CHANGES_REQUIRED

## 1. Bottom-line verdict

Claude approved the core product/architecture direction: Option D, the hybrid model-level source display policy, is the right target because it improves PDF readability while preserving provenance and validator visibility.

The critique returned CHANGES_REQUIRED because several implementation details in the original spec were too loose or referenced stale symbols. The corrections below have been integrated into the architecture spec.

## 2. Required corrections integrated

1. Renderer symbol correction
   - Original issue: the spec referenced a nonexistent `_section_table_flowables(...)` symbol.
   - Correction: the active renderer symbol is `backend/earnings_deep_dive/pdf_renderer.py::_table(section, styles, fonts)`.

2. Grounding field reality check
   - Original issue: the policy relied on `RenderedTableRow.grounding` as if it were populated for current rows.
   - Correction: the spec now states that current mapper transformations often rebuild rows without grounding metadata, so Phase 1 calculated-row detection must start from known source-cell labels such as `Calculated (FCF ÷ Revenue)` / `計算値（FCF ÷ 売上高）` and only later graduate to structured `grounding`.

3. Policy application order
   - Original issue: the spec could be read as applying the display policy too early.
   - Correction: the spec now requires applying policy after deterministic enrichment, row numbering, and sanitization, because those steps can rewrite row cells and previously dropped row metadata.

4. No hardcoded Source column index
   - Original issue: source-column handling could be fragile if it assumes the last column is always `Source`.
   - Correction: the spec now requires locating the source column by normalized header label, not hardcoded index.

5. No row/cell mutation by policy
   - Original issue: the policy could be interpreted as changing table data.
   - Correction: the spec now forbids row/cell mutation by the source-display policy. It may set metadata and renderer display behavior only.

6. Operating Metrics default tightened
   - Original issue: default collapse for Operating Metrics was too broad.
   - Correction: Operating Metrics may collapse only when every expected row is present and every source cell is present, non-placeholder, and identical after conservative normalization.

7. Auditability regression criterion
   - Original issue: tests covered visual behavior but not enough auditability invariants.
   - Correction: acceptance criteria now require proving the same source evidence remains available in the structured table after renderer-level collapse.

## 3. Non-blocking observations

- Option C remains acceptable only as a tactical fallback, not as the preferred target.
- Prompt-level source removal should remain out of Phase 1.
- Mixed direct/calculated tables must retain visible row-level provenance unless a later row-exception mechanism is explicitly designed and verified.

## 4. Status after integration

All CHANGES_REQUIRED findings above are reflected in `edp010_012_source_policy_architecture_2026-06-16.md`.

Implementation remains intentionally blocked until the corrected spec is reviewed/accepted and a separate builder card is created.
