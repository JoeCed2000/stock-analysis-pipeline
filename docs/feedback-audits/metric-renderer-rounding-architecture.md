# Metric-based table rounding architecture — Operating Metrics + Segments

- **Task:** `t_bd23aab4`
- **Date:** 2026-06-17
- **Project:** `sa-pipeline`
- **Parent:** `t_57b6b5f2` — NVDA JP↔EN parity classification
- **Decision type:** architecture/spec only; no implementation in this card

## 1. Problem

Parent classification found four JP↔EN numeric deltas that are not hard data gaps:

| Section | EN | JP | Classification |
|---|---:|---:|---|
| Operating Metrics — Gross Profit | `$61.15B` | `$61.14B` | rounding-direction artifact |
| Operating Metrics — OpEx | `$7.61B` | `$7.60B` | derived from Gross Profit rounding |
| Segments — prior-year total | `$44.05B` | `$44.06B` | rounding-direction artifact |
| Segments — Data Center YoY | `92.4%` | `92.0%` | display precision drift |

Root cause: EN and JP language paths can independently round LLM-emitted table values. The input precision is already coarse (`$81.61B` is two decimals, i.e. $10M precision), so the deltas are below source precision but visibly confusing in side-by-side review.

## 2. Evidence gathered

### WIKI_EVIDENCE

Read `WIKI.md` top entries:

- `t_57b6b5f2`: identifies Real gap 6 as rounding-direction artifacts and creates this follow-up card.
- `t_3173af81`: Capital Efficiency was corrected by moving critical values to deterministic metric handling and preserving PDF output with Kernel proof.
- `t_527c4b2e`: source display policy already treats Segments as a policy-managed rendered table section.

### Classification evidence

Read `docs/feedback-audits/jp-en-parity-classification.md`:

- §3.3 Operating Metrics: Gross Profit and OpEx differ only by display rounding direction.
- §3.6 Segments: Data Center YoY and prior-year total differ only by display rounding/precision.
- §5 Real gap 6: recommends metric-based table rebuild for Operating Metrics + Segments.

### GRAPH_EVIDENCE

CodeGraph status for `/home/ced/codex-projects/stock-analysis-pipeline`:

- 351 files indexed, 7,997 nodes, 15,551 edges.
- Index reports pending changes, so confidence is **degraded but usable** for current symbol topology.

CodeGraph callers:

- `_rows_for_section` callers: `_enrich_codex_table`, `build_earnings_deep_dive_report`.
- `_extract_segment_rows` callers: `_rows_for_section`.

Impact chain:

```text
FinancialMetrics
  -> mapper._rows_for_section(section_key, section.table_rows, metrics, scoring)
  -> RenderedTable / RenderedTableRow
  -> mapper.build_earnings_deep_dive_report(...).sections
  -> pdf_renderer.render_earnings_deep_dive_pdf(...)
  -> pdf_renderer._table(section, styles, fonts)
  -> EN/JP PDF table cells
```

### SYMBOL_PLAN

Serena MCP tools are not available in this worker toolset, so `SYMBOL_PLAN` is **degraded** and based on CodeGraph + direct file reads.

Relevant symbols:

- `backend/earnings_deep_dive/mapper.py::_DATA_DRIVEN_SECTIONS` currently includes `Operating Metrics` and `Segments`.
- `backend/earnings_deep_dive/mapper.py::_rows_for_section()` owns deterministic rows for `Operating Metrics` and dispatches `Segments` to `_extract_segment_rows()`.
- `backend/earnings_deep_dive/mapper.py::_extract_segment_rows()` owns segment revenue, prior-year, YoY, and mix formatting.
- `backend/earnings_deep_dive/pdf_renderer.py::_table()` is presentation-only and renders the `RenderedSection.table` it receives.
- `backend/earnings_deep_dive/pdf_renderer.py::render_earnings_deep_dive_pdf()` only loops sections and calls `_table()`; it should not become a financial-computation layer.

## 3. Architecture decision

**Decision:** keep `pdf_renderer.py` presentation-only. Do not add financial calculation logic inside the ReportLab renderer.

The deterministic “metric-based renderer” behavior should be enforced at the mapper/table-construction seam:

```text
mapper builds canonical RenderedTable values from FinancialMetrics
pdf_renderer renders those values without recomputing or language-specific alteration
```

Why:

1. `mapper.py` already has the deterministic table factory (`_rows_for_section`) and the `FinancialMetrics` object.
2. `pdf_renderer.py` has no business computing Gross Profit, OpEx, YoY, or segment totals; adding that there would duplicate financial rules and make PDF output harder to audit.
3. The current data flow already marks `Operating Metrics` and `Segments` as data-driven sections. The child work should harden and prove that this path cannot fall back to language-specific LLM-rounded cells when canonical metrics exist.
4. This preserves existing Capital Efficiency behavior and avoids mixing presentation with domain calculations.

## 4. Rounding rule

Use Python default numeric formatting / `round()` behavior, i.e. banker's rounding, consistently for both EN and JP.

Acceptance rule for child tasks:

- One canonical numeric source enters `_rows_for_section()` / `_extract_segment_rows()`.
- EN and JP labels may differ, but row values must be byte-identical after formatting for the same canonical metrics.
- LLM prose may remain language-specific; table cells must not.

## 5. Split implementation plan

Created two atomic child tasks, both assigned to `python-builder` and both dependent on this architecture card:

### Child 1 — Operating Metrics

- **Task:** `t_c02f3308`
- **Title:** Harden Operating Metrics metric-based table rounding
- **Write scope:** `backend/earnings_deep_dive/mapper.py`, focused regression file `spec_v27_pdf_renderer.py`
- **Goal:** Gross Profit and OpEx are rebuilt from canonical `FinancialMetrics` values and display identically in EN and JP.
- **Main symbols:** `_rows_for_section('Operating Metrics')`, `build_earnings_deep_dive_report` data-driven flow.
- **Proof:** focused regression plus Kernel/kverify READY.

### Child 2 — Segments

- **Task:** `t_3eb11127`
- **Title:** Harden Segments metric-based table rounding
- **Write scope:** `backend/earnings_deep_dive/mapper.py`, focused regression file `spec_v27_pdf_renderer.py`
- **Goal:** Data Center YoY and prior-year total are rebuilt from canonical `FinancialMetrics.segments` values and display identically in EN and JP.
- **Main symbols:** `_extract_segment_rows()`, `_rows_for_section('Segments')`, `build_earnings_deep_dive_report` data-driven flow.
- **Proof:** focused regression plus Kernel/kverify READY.

## 6. Non-goals / stop line

- Do not regenerate the full NVDA EN/JP PDF in this spec card.
- Do not change prompt wording in this card.
- Do not change source-display policy in this card.
- Do not change Capital Efficiency behavior.
- Do not move calculation logic into `pdf_renderer.py` unless a child task proves the mapper seam cannot satisfy the acceptance criteria.

## 7. Required downstream verification

Each child task must include:

1. A focused regression in `spec_v27_pdf_renderer.py` or an equivalent focused regression file if the builder finds the project convention is different.
2. The existing EDP/source-display policy bundle relevant to renderer/mapper behavior.
3. `curl /api/health` checkpoint after validation.
4. Persistent Kernel proof:
   - `.ced-agent-kernel/specs/<task>.json`
   - `ops/kernel_checks/verify_<task>.py`
   - `kverify ... --base-dir .` returns READY.

## 8. Architect verdict

Proceed with the two-child split. The implementation should harden mapper-level deterministic table construction, not add new financial computation to the PDF renderer.
