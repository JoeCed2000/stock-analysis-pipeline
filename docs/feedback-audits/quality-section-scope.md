# Quality section scope decision — NVDA Earnings Deep-Dive

Date: 2026-06-16
Task: t_e4cbec09
Project: stock-analysis-pipeline
Scope type: architecture/spec decision only — no runtime implementation in this card.

## Decision

Remove the client-visible `Quality` block only from Earnings Deep-Dive PDF output, and only where it is rendered as the `Quality` dimension inside the late-report `Peer Benchmark` block.

Do not remove or rename these separate concepts:

- `Data Quality` — source freshness/completeness audit section; keep it.
- `Backlog Quality` — canonical Backlog section title/field label; keep it.
- `Capital Efficiency` — ROE / ROTCE / ROA / ROIC analysis; keep it for now, but the later child card may shorten its prose under the separate Profitability/Capital Efficiency concision task.
- `Earnings quality` wording inside prose/verdict when it is sentence-level analysis, not a standalone section heading.
- Company Overview PDF quality gates or generic PDFQA quality checks.

## Why this scope

The reviewed PDF section map shows the exact offending client-visible block:

```text
Page 19
Peer Benchmark
  Valuation
  Growth
  Quality
    In Line with Peers total_debt above peer median ...
```

The annotation in the source plan says the client targeted `Quality` on page 13 and judged it useless for an earnings-result analysis. In the current generated PDF, the standalone `Quality` label appears as a peer-benchmark dimension, not as the core ROE/ROIC table heading. Removing the whole capital-efficiency stack would be broader than the client request and would collide with other accepted Deep-Dive contracts that still require capital efficiency / returns evidence.

## Shared-scope confirmation

Evidence from the current repository:

- `backend/earnings_deep_dive/prompts.py` defines the Earnings Deep-Dive section order and does not include a canonical standalone `Quality` section. It includes `Capital Efficiency`, `Backlog` rendered as `Backlog Quality`, and `Verdict`.
- `backend/earnings_deep_dive/template.py` also has no standalone `Quality` section in `TEMPLATE_SECTION_KEYS`; `Capital Efficiency` is a normal template section for both EN and JP.
- `backend/earnings_deep_dive/pdf_renderer.py` renders `Quality` only inside `render_peer_benchmark()` as the third relative peer dimension: Valuation / Growth / Quality.
- `backend/earnings_deep_dive/pdf_renderer.py` separately renders `Data Quality` through `render_data_quality()`; that is a source-audit section and not in scope.
- `backend/earnings_deep_dive/deep_dive_validator.py` already has EDP-011 logic flagging standalone generic `Quality` headings while explicitly excluding canonical required sections such as `Backlog Quality` and ticker-specific `Earnings Quality`.
- `backend/earnings_deep_dive/pdf_quality_gate.py` currently expects old generic deep sections (`Financial Metrics`, `Valuation`, `Capital Efficiency`, `Sources`, etc.) and does not make a standalone `Quality` section required.

Conclusion: the label is shared semantically across several mechanisms, but the removable client-facing artifact is narrow: the Peer Benchmark `Quality` dimension in Earnings Deep-Dive PDF rendering. The implementation child must not remove every string named `Quality`.

## WIKI_EVIDENCE

Read:

- `/home/ced/codex-projects/stock-analysis-pipeline/WIKI.md`
- `/home/ced/codex-projects/docs/llm-wiki/projects/stock-analysis-pipeline.md`
- `/mnt/c/Users/cedon/Desktop/SA/PLAN_conseil_kanban_NVDA_feedback_2026-06-16.md`
- `/mnt/c/Users/cedon/Desktop/SA/REVUE_ecarts_NVDA_deepdive_2026-06-16.md`
- `docs/specs/sa-pdf-structural-quality-v1.md`

Extracted constraints:

- Deep-Dive output is client-facing; PDF wording must be scoped to earnings analysis, not generic company-background material.
- The plan explicitly asks for a micro-decision before implementation: conditional removal for the report type so other reports are not broken.
- Renderer contracts still include capital efficiency / returns evidence; deleting all ROE/ROIC content would be a larger product decision than this card.
- Existing project rules require Wiki → CodeGraph → symbol plan evidence and Kernel/kverify for any mutation.

## GRAPH_EVIDENCE

CodeGraph status:

```text
Project: /home/ced/codex-projects/stock-analysis-pipeline
Files: 336
Nodes: 7,761
Edges: 15,151
Index is up to date
```

CodeGraph query:

```text
codegraph query "Capital Efficiency Quality Backlog Quality prompts" --limit 20
```

Relevant result anchors:

- `capital_efficiency_prompt` — `backend/earnings_deep_dive/prompts.py:1166`
- `backlog_prompt` — `backend/earnings_deep_dive/prompts.py:1264`
- `render_data_quality` — `backend/earnings_deep_dive/pdf_renderer.py:1640`
- `_build_data_quality` — `backend/earnings_deep_dive/mapper.py:3362`
- `_cash_flow_quality_note` — `backend/earnings_deep_dive/mapper.py:2081`
- `format_pdf_quality_result` / `pdf_quality_gate.py` — PDFQA, not client section content.

Fallback repository search found the exact renderer site for the removable label:

```text
backend/earnings_deep_dive/pdf_renderer.py:1601-1605
for dim_label, rel_label, rel_detail in [
    (translate("Valuation", lang), ...),
    (translate("Growth", lang), ...),
    (translate("Quality", lang), pb.relative_quality_label, pb.relative_quality_detail),
]
```

Graph confidence: high for locating the relevant renderer and adjacent data-quality paths; medium for full semantic blast radius because `Quality` is a common word and repository search was required to disambiguate.

## SYMBOL_PLAN

Serena symbol-level editing is marked degraded for this spec card: no Serena MCP tool is available in this worker toolset, and this card must not implement code. The implementation child should use this symbol plan:

1. Target only `render_peer_benchmark(report, styles, fonts)` in `backend/earnings_deep_dive/pdf_renderer.py`.
2. Remove or conditionally suppress only the third peer-benchmark display row labelled `translate("Quality", lang)`.
3. Preserve the underlying `PeerBenchmarkSection.relative_quality_*` model fields and `_build_peer_benchmark()` calculations unless a later card explicitly removes the API/model concept.
4. Keep `render_data_quality()` unchanged.
5. Keep `Capital Efficiency` prompts/templates/validator rules unchanged in this child; if prose is too long, handle it under the separate Profitability/Capital Efficiency concision card.
6. Add/adjust renderer regression coverage that proves final extracted PDF or renderer story no longer contains a standalone Peer Benchmark `Quality` row while `Data Quality`, `Backlog Quality`, and `Capital Efficiency` remain allowed.

## Child-card rule

For the implementation child:

> In Earnings Deep-Dive PDF rendering, suppress the `Peer Benchmark → Quality` display row only; do not remove `Data Quality`, `Backlog Quality`, `Capital Efficiency`, `Earnings quality` prose, PDFQA quality gates, or Company Overview quality concepts.

## Out of scope for this card

- No Python code changes.
- No prompt/template edits.
- No PDF regeneration.
- No backend restart.
- No change to peer benchmark API/model fields.
- No change to Company Overview reports.
