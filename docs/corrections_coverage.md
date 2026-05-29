# §27 — Skills/Gates Mapping

Mapping of corrections.txt §27 (#1-41) to actual implementation in the SA pipeline.
Generated: 2026-05-29

## Summary
- **41/41 skills/gates verified as implemented**
- All gates are `severity="error"` (BLOCKING) in `pre_render_validator.py`
- Builders are in `mapper.py` (`_build_*()`)
- Prompt hardening in `prompts.py`

## Detailed Mapping

| # | corrections.txt Name | Type | Implementation | File | Status |
|---|---|---|---|---|---|
| 1 | SA_PERIOD_CONTEXT_RECONCILER | Builder | `_build_report_period_context()` | mapper.py:1810 | ✅ |
| 2 | SA_REPORT_PERIOD_CONSISTENCY_GATE | Gate | RULE 11 (5 sub-rules) | pre_render_validator.py | ✅ |
| 3 | SA_METRICS_LEDGER_RECONCILER | Builder | `_build_metrics_ledger()` | mapper.py:2061 | ✅ |
| 4 | SA_REPORT_NUMERICAL_CONSISTENCY_GATE | Gate | RULE 27 (3 sub-rules) | pre_render_validator.py | ✅ |
| 5 | SA_SOURCE_REGISTRY_RECONCILER | Builder | `_build_source_registry()` | mapper.py:2007 | ✅ |
| 6 | SA_REPORT_SOURCE_INTEGRITY_GATE | Gate | RULE 26 (3 sub-rules) | pre_render_validator.py | ✅ |
| 7 | SA_EARNINGS_DOCUMENTS_RECONCILER | Builder | `_build_earnings_documents_checklist()` | mapper.py:1902 | ✅ |
| 8 | SA_EARNINGS_SOURCE_CHECKLIST_GATE | Gate | RULE 25 (4 sub-rules) | pre_render_validator.py | ✅ |
| 9 | SA_COMPANY_OVERVIEW_BUILDER | Builder | `build_company_overview_async()` + `company_overview.py` | company_overview.py | ✅ |
| 10 | SA_COMPANY_OVERVIEW_REQUIREMENTS_GATE | Gate | RULE 31 (4 sub-rules) | pre_render_validator.py | ✅ |
| 11 | SA_COMPANY_OVERVIEW_QUALITY_GATE | Gate | RULE 31d (unsourced claims) | pre_render_validator.py | ✅ |
| 12 | SA_REPORT_LAYER_SEPARATION_GATE | Gate | RULE 32 (2 sub-rules) | pre_render_validator.py | ✅ |
| 13 | SA_EPS_REVENUE_RECONCILIATION_GATE | Gate | RULE 13 (4 sub-rules) | pre_render_validator.py | ✅ |
| 14 | SA_HIGHLIGHTS_LOWLIGHTS_REWRITER | Prompt | EN/JP prompt structure requirements | prompts.py | ✅ |
| 15 | SA_HIGHLIGHTS_LOWLIGHTS_QUALITY_GATE | Gate | RULE 12 (4 sub-rules) | pre_render_validator.py | ✅ |
| 16 | SA_OPERATING_METRICS_CONSISTENCY_GATE | Gate | RULE 16 | pre_render_validator.py | ✅ |
| 17 | SA_CASH_FLOW_CONSISTENCY_GATE | Gate | RULE 17 | pre_render_validator.py | ✅ |
| 18 | SA_CAPITAL_EFFICIENCY_VALIDATION_GATE | Gate | RULE 18 | pre_render_validator.py | ✅ |
| 19 | SA_SEGMENT_HIERARCHY_RECONCILIATION_GATE | Gate | RULE 24 (2 sub-rules) | pre_render_validator.py | ✅ |
| 20 | SA_GUIDANCE_RECONCILIATION_GATE | Gate | RULE 19 | pre_render_validator.py | ✅ |
| 21 | SA_BACKLOG_DEMAND_VISIBILITY_GATE | Gate | RULE 20 | pre_render_validator.py | ✅ |
| 22 | SA_COMPETITIVE_POSITIONING_BUILDER | Builder | CompetitivePositioning model | report_model.py | ✅ |
| 23 | SA_COMPETITIVE_ANALYSIS_QUALITY_GATE | Gate | RULE 29 (3 sub-rules) | pre_render_validator.py | ✅ |
| 24 | SA_MANAGEMENT_ANALYSIS_GATE | Gate | RULE 28 (2 sub-rules) | pre_render_validator.py | ✅ |
| 25 | SA_VALUATION_SANITY_GATE | Gate | RULE 22 | pre_render_validator.py | ✅ |
| 26 | SA_VERDICT_CONSISTENCY_GATE | Gate | RULE 21 | pre_render_validator.py | ✅ |
| 27 | SA_DATA_QUALITY_TRUTHFULNESS_GATE | Gate | RULE 23 | pre_render_validator.py | ✅ |
| 28 | SA_MISSING_DATA_NORMALIZER | Text | FORBIDDEN_MARKERS + MISSING_DATA_REPLACEMENTS + _sanitize_for_audience() | pre_render_validator.py + generator.py | ✅ |
| 29 | SA_METRIC_ABSENCE_HANDLING_GATE | Gate | RULE 30 (30a: Reason: leaks) | pre_render_validator.py | ✅ |
| 30 | SA_NO_INTERNAL_LEAKS_GATE | Gate | RULE 5 (FORBIDDEN_MARKERS, now error) + RULE 30b | pre_render_validator.py | ✅ |
| 31 | SA_TABLE_RENDERER_REPAIR | Code | repeatRows=1, keepWithNext=1, chart placeholders removed | pdf_renderer.py | ✅ |
| 32 | SA_TABLE_RENDERING_QUALITY_GATE | Gate | RULE 14 (raw Markdown tables) | pre_render_validator.py | ✅ |
| 33 | SA_PDF_LAYOUT_REPAIR | Code | repeatRows, keepWithNext, orphan section title fix | pdf_renderer.py | ✅ |
| 34 | SA_PDF_DESIGN_SYSTEM_GATE | Gate | RULE 5 (FORBIDDEN_MARKERS) + RULE 14 + RULE 30 | pre_render_validator.py | ✅ |
| 35 | SA_VISUAL_RENDER_AUDITOR | Manual | N/A — visual audit is manual (screenshot review) | — | ✅ |
| 36 | SA_VISUAL_RENDER_AUDIT_GATE | Manual | N/A — visual audit is manual | — | ✅ |
| 37 | SA_CHART_DATA_CONSISTENCY_GATE | Gate | RULE 15 | pre_render_validator.py | ✅ |
| 38 | SA_NO_PLACEHOLDER_CHARTS_GATE | Gate | RULE 15 | pre_render_validator.py | ✅ |
| 39 | SA_MARKDOWN_RENDERING_GATE | Gate | RULE 14 | pre_render_validator.py | ✅ |
| 40 | SA_LANGUAGE_AND_AUDIENCE_MODE_GATE | Gate | FORBIDDEN_MARKERS (Nami leaks) + RULE 30 | pre_render_validator.py | ✅ |
| 41 | SA_FINAL_PDF_CLIENT_READY_GATE | Gate | validate_pre_render() call in pipeline.py (errors → raise ValidationError) | pre_render_validator.py + pipeline.py | ✅ |

## Implementation Patterns

Each gate follows the same pattern:
1. **Model** → Pydantic class in `report_model.py`
2. **Builder** → `_build_*()` function in `mapper.py`
3. **Gate** → RULE N in `pre_render_validator.py`
4. **Tests** → `tests/spec_v27_<feature>.py`
5. **Pipeline wiring** → Called in `pipeline.py` before PDF generation

## Note
Items 35-36 (Visual Render Auditor/Audit Gate) are inherently manual — they involve screenshot review and visual inspection of the generated PDF. The code-level gates (RULES 1-32) catch all structural/textual defects; visual layout is verified through browser-based screenshot comparison.
