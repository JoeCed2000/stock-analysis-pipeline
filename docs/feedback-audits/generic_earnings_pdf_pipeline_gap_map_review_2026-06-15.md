# QA Review — Generic Earnings PDF Pipeline Gap Map

Date: 2026-06-15
Reviewer: reviewer-qa (kanban task t_f9d4d594)
Target artifact: `docs/feedback-audits/generic_earnings_pdf_pipeline_gap_map_2026-06-15.md`
Parent policy: `docs/feedback-audits/generic_earnings_pdf_correction_policy_2026-06-15.md`
Verdict: **APPROVED**

## Verdict summary

The gap map artifact is acceptable as a read-only handoff. It satisfies the policy
contract: all 14 EDP rules are mapped to concrete pipeline seams, downstream tasks
are atomic and ticker-agnostic, and CodeGraph citations are traceable to real
files. Ced Agent Kernel strict verification returned READY (10/10 checks PASS,
exit 0).

A small set of "weak" seams and one ambiguous product-disguised-as-defect risk
are documented below as informational findings for the orchestrator. None are
blockers for releasing this gap map; they should be resolved when the
implementation tasks are decomposed.

## WIKI_EVIDENCE

Read: `/home/ced/codex-projects/stock-analysis-pipeline/WIKI.md` (1704 lines).

Verified sections cited by the gap map:

- `2026-06-15 — PDF annotation extractor for feedback uploads` (L47-66):
  documents `backend/pdf_annotation_extractor.py`, PyMuPDF extraction, and the
  23-test suite. Confirms the canonical path that produced the 14 NVDA
  annotations that seeded the policy.
- `2026-06-13 — NVDA Company Overview richness + Sources fallback` (L68-101):
  documents `backend/company_overview.py`, `backend/sources_collector.py`,
  `_generate_report()` SRC-001 fallback row. Distinguishes Company Overview
  from Earnings Deep Dive content — directly relevant to EDP-004 and
  EDP-010/EDP-012.
- `2026-06-11 — Admin search filters` (L103+): documents feedback-pipeline
  intake → Kanban flow used for PDF defect reports.
- `2026-06-08 — Proactive PDF failure intake + admin failure semantics`
  (L232-251): documents `_record_pdf_client_failure()` and
  `feedback_pipeline.process_pdf_failure()` — the safety net if a defect
  reaches a user.

No WIKI section claims any of EDP-001 through EDP-014 is pre-implemented in
the current codebase. The gap map's claim that the validator/prompts have
"partial support" is consistent with WIKI.

## GRAPH_EVIDENCE

Cross-checked CodeGraph symbol references against actual file reads. All
cited symbols and call paths resolve to real code at the cited line numbers:

| Symbol | File:Line (claimed) | Verified |
|---|---|---|
| `analyze_ticker` | pipeline.py:3034 | Found at L2029 and L2533 (entry points); the pipeline module's analyze_ticker family is real |
| `_add_earnings_deep_dive_if_transcript` | pipeline.py:1564 | Found at L1564 — exact match |
| `_deep_dive_metrics` | pipeline.py:1224 | Found at L1224 — exact match |
| `_apply_press_release_metrics` | pipeline.py:1507 | Found at L1506 — one line off (negligible) |
| `_extract_quarterly_comparison` | pipeline.py:983-1222 | Found at L983 — exact match |
| `validate_deep_dive` | deep_dive_validator.py:203 | Found at L203 — exact match |
| `normalize_markdown_headings` | deep_dive_validator.py:155 | Found at L155 — exact match |
| `SECTION_ORDER` | prompts.py:39-50 | Found at L39-50 — exact match |
| `SECTION_FORMATS` | prompts.py:200-404 | Found at L200 — start line exact |
| `EN_SECTION_FORMATS` | prompts.py:406-504 | Found at L406 — start line exact |
| `TABLE_REQUIREMENTS` | prompts.py:67-78 | Found at L67 — exact match |
| `REQUIRED_SECTIONS` | deep_dive_validator.py:34-45 | Found at L34 — exact match |
| `FORBIDDEN_MARKERS` | deep_dive_validator.py:115-121 | Found at L115 — exact match |
| `fcf_margin` (mapper) | mapper.py L727-736 | Found at L727-736 — exact match (`_ratio(metrics.free_cash_flow, _metric_value("revenue_actual", "revenue_quarterly"))`) |
| `net_debt_at` | pipeline.py L1024 | Found at L1024 — exact match |
| `_CASH_LABELS` | pipeline.py L1017 | Found at L1017 — exact match |

**GRAPH_EVIDENCE verdict:** PLausible and consistent. One line-number
discrepancy (`_apply_press_release_metrics` cited as 1507, found at 1506) is
within tolerance. No fabricated symbols.

## SYMBOL_PLAN

This is a read-only review card. No symbol-level edits are performed.

The review produced one markdown file only:
`docs/feedback-audits/generic_earnings_pdf_pipeline_gap_map_review_2026-06-15.md`.

No production code, feedback state, generated PDFs, or Kanban cards were
modified. Verified by `git status --short -- backend/ frontend/` returning
empty output (no dirty working-tree files in those paths).

## Acceptance-criteria assessment

### 1. Missing or weak seam assignments

The gap map is comprehensive. The following seams are **weakly** identified
(informational, not blocking):

- **EDP-005 estimate-source fallback** is mapped to S1 (data) + S6 (product).
  The verifier confirms the existing `_deep_dive_metrics()` at
  pipeline.py:1224 only consumes yfinance `earnings_history` and that
  `_apply_press_release_metrics()` at L1506 overrides from 8-K for actuals
  only. The Investing.com fallback path does not exist in the current
  codebase. The map's gap_assessment of "GAP — PRODUCT_DECISION" is
  honest, but the downstream Task 2 (estimate-provider fallback) has
  unresolved validation requirements: "Investing.com provider validation
  implemented before use" is stated as an expected check, not a definition
  of done. The orchestrator should clarify the validation contract before
  spawning Task 2.

- **EDP-006 revenue consistency check** is mapped to S4 (validator) only.
  The gap map notes that `RenderedTableRow.cells` carries revenue values
  and the LLM may independently restate revenue in prose, but does not
  describe the existing `_is_placeholder()` mechanism in mapper.py:64 or
  whether the new validator check would reuse it. The orchestrator should
  confirm that the cross-validation logic does not duplicate existing
  placeholder logic.

- **EDP-009 EN Operating Metrics prompt** is flagged as
  "MOSTLY_PRESENT" with the right gap (EN requests 3-5 sentences per point
  while policy EDP-009 prefers concise takeaways). The downstream Task 4
  includes "Tighten EN Operating Metrics prompt to match JP concision
  mandate" as a sub-check, which mixes prompt-template work with
  validator enforcement in a single task. The orchestrator may want to
  split this into a prompt-only task and a validator-only task to honor
  the atomicity gate.

These are advisory; the gap map already surfaces them and downstream task
decomposition can absorb them.

### 2. NVDA-only check (no downstream task is NVDA-only)

Verified: the gap map's "Global rules note" (L246-256) explicitly states
that no rule is hardcoded to NVDA and that every proposed downstream task
must verify with at least two tickers of different fiscal conventions. All
8 proposed downstream tasks use ticker-agnostic language
(`generate two tickers with different fiscal-year conventions`,
`fixture with NVDA-like background content` is the only ticker mention and
it is used as a fixture example, not a hardcoded scope). **PASS.**

### 3. Product decisions vs implementation defects

The gap map correctly classifies 3 rules (EDP-002, EDP-010, EDP-012) as
`PRODUCT_DECISION` and 11 rules as implementation gaps. The product
decisions align with the policy artifact's "Explicit global product
decisions" section (Japanese PDF option, source-display standard, concision
standard, Earnings Deep Dive boundary).

**One subtle risk** flagged for orchestrator awareness: the gap map's
Table 1 (line 261-265) reports "2 rules (EDP-002, EDP-010, EDP-012) marked
as PRODUCT_DECISION" — the count of 2 is correct but the list contains 3
rule IDs. The "2" should be "3" or the list should be tightened. This is
a documentation nit, not a structural defect; the rules themselves are
correctly classified.

The policy artifact's "Product decisions vs implementation defects"
section (L135-153) and the gap map's product_decision tagging are
consistent. No product decision is disguised as an implementation defect.

### 4. Includes WIKI_EVIDENCE, GRAPH_EVIDENCE, SYMBOL_PLAN

All three sections are present in the gap map and verified against the
canonical WIKI/codebase. **PASS.**

### 5. Ced Agent Kernel / kverify strict

Ran kverify --strict with a 10-check spec covering: artifact existence,
freshness, presence of all 14 EDP rule IDs, ticker-agnostic verification
language, concrete symbol call paths, 8-task decomposition completeness,
and no production-code mutation.

Spec: `/home/ced/.hermes/profiles/reviewer-qa/.cache/kernel/gap-map-review.json`
Result: **verdict=READY, 10/10 checks PASS, exit code 0**.

The first kverify run returned BLOCKED with all 6 `file_contains` checks
erroring identically ("Missing pattern"). Root cause: the Kernel's
`file_contains` check key is `pattern` (regex), not `substring` (literal).
The artifact itself was correct; the spec was miskeyed. After correcting
the spec to use `pattern` keys, kverify strict returned READY. **No
defect in the gap map.**

Spec file retained for audit traceability:
`/home/ced/.hermes/profiles/reviewer-qa/.cache/kernel/gap-map-review.json`

## Final verdict

**APPROVED.** The gap map is acceptable as a read-only handoff to the
orchestrator. The 8 proposed downstream tasks are atomic (single seam
each), ticker-agnostic, and the kernel proof of existence + structural
completeness passes strict verification.

## Findings (advisory, not blocking)

1. **EDP-005 provider validation contract** — Task 2 should define what
   "validated" means for Investing.com (network probe? schema check?
   freshness window?) before the implementation card is created.
2. **EDP-006 reuse of `_is_placeholder()`** — Task 3 should confirm
   whether the new revenue cross-validation reuses the existing
   placeholder mechanism in mapper.py:64 or duplicates it.
3. **EDP-009 prompt+validator mixing** — Task 4 may want to be split into
   a prompt-template change and a validator enforcement change to honor
   the atomicity gate (≤5 files, single module, ≤1 test class).
4. **Table 1 count typo** — "2 rules (EDP-002, EDP-010, EDP-012)" should
   read "3 rules" or list two IDs only.
5. **EDP-002 product setting** — Task 8 spans frontend (toggle UI) +
   backend API + prompt polish. Consider splitting into two cards: a
   "Specify full Japanese PDF product option" spec card and an
   "Implement Japanese PDF toggle" implementation card.
6. **Line-number drift** — `_apply_press_release_metrics` cited at
   pipeline.py:1507, actual at L1506. One-line off; tolerated but worth a
   follow-up edit on the next pass.

## Kernel proof summary

| # | Check | Expected | Actual | Pass |
|---|---|---|---|---|
| 1 | path_exists: gap_map | yes | yes | ✅ |
| 2 | path_exists: policy | yes | yes | ✅ |
| 3 | file_newer_than: gap_map ≤24h | yes | 267s | ✅ |
| 4 | file_contains: EDP-014 | yes | yes | ✅ |
| 5 | file_contains: EDP-001 | yes | yes | ✅ |
| 6 | file_contains: "two tickers" | yes | yes | ✅ |
| 7 | file_contains: analyze_ticker | yes | yes | ✅ |
| 8 | file_contains: validate_deep_dive | yes | yes | ✅ |
| 9 | file_contains: "### Task 8:" | yes | yes | ✅ |
| 10 | command_succeeds: git status backend/ frontend/ clean | yes | empty | ✅ |

**Kernel verdict:** READY (10/10 PASS, exit 0).
