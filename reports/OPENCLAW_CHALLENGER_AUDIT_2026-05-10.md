# OPENCLAW CHALLENGER AUDIT — pdf.pdf (NVDA Q2 2026) vs modele.pdf

*Audité par : OpenClaw (GPT-5, thinking=high) — 2026-05-10*
*Méthode : inspection raw PDFs + lecture audit Hermes. Limitations : pas d'extraction PyMuPDF (OpenClaw sans exec), screenshots non accessibles.*

---

## A. Executive Summary

- **Overall**: The NVDA deep-dive diverges materially from the template on data integrity and traceability, with likely quarter/period mix-ups and insufficient sourcing. Visual fit is close in section presence but undermined by systemic layout issues and an **image-heavy PDF that impairs text extraction/search**.
- **Where I challenge the prior audit**: 
  - (a) "ALL tables overflow" is probably overstated; likely "most" tables with long labels suffer.
  - (b) Language non-compliance depends on run config; if the generator was set to EN-only, penalizing for missing JP is context-dependent.
  - (c) EPS contradiction could be partly GAAP vs non-GAAP, not just wrong quarter; still a serious inconsistency.
- **Net**: Data quality and sourcing are the true P0s. Visual/layout and language/style are next.
- **Independent parity score: 46/100**.

---

## B. Parity Score (/100)

| Dimension | Score | Comment |
|-----------|-------|---------|
| Structure/completeness | 14/20 | Most sections present but weakened |
| Data correctness/integrity | 12/25 | Contradictions, period mixing |
| Sources/traceability | 6/20 | "Company filing/Calculated" everywhere, no deep links |
| Visual/readability | 6/15 | Column overflow in most tables |
| Language/style vs template | 4/10 | 100% EN vs JP template |
| Build/run metadata | 4/10 | No model, timestamps, data providers |
| **TOTAL** | **46/100** | ⚠️ Prior audit had 44/100 — close agreement |

---

## C. Verification of Prior Claims (Challenged)

### 1) EPS contradiction ($1.76 vs $1.62)
- **Hermes**: TWO EPS values — contradiction.
- **OpenClaw**: CONFIRM core issue, ADD nuance. Could be GAAP vs non-GAAP EPS, or different fiscal periods. The "$2.82 estimate" looks like a different quarter or consensus EPS mislabeled as guidance. Even if partly GAAP/non-GAAP, a single section must reconcile period and basis.
- **Verdict**: P0. Investor-misleading.

### 2) Annual/quarterly mix (rev $68.1B vs $215.94B; segments $193.7B; net income $43.0B vs $120.07B)
- **Hermes**: Mélange trimestriel/annuel.
- **OpenClaw**: CONFIRM. Consistent with known failure mode: mixing 10-Q and TTM/annualized segment totals. Segment totals exceeding quarterly revenue = red flag.
- **Verdict**: P0.

### 3) 35x "Company filing / Calculated" — zero real SEC links
- **Hermes**: Aucune traçabilité.
- **OpenClaw**: SUBSTANTIVELY TRUE. Cannot verify exact "35x" count without text extraction (PDF is image-based), but find no visible URLs in raw streams. Lack of deep links is a traceability failure.
- **Verdict**: P0 for enterprise standards.

### 4) "ALL tables have text overflow"
- **Hermes**: Toutes les tables — S5.
- **OpenClaw**: PARTIALLY AGREE. Likely many tables overflow, but "ALL" is overbroad. Numeric-only tables less likely to overflow; long-label cells (source, commentary) wrap poorly or bleed.
- **Verdict**: Reframe to **"systemic overflow in most multi-column sections"**. Severity P1 (Hermes had S5/P0).

### 5) Language 100% English; template expects Japanese
- **Hermes**: Manque japonais — S4.
- **OpenClaw**: INVALIDÉ par le user. La langue est choisie par l'utilisateur (EN ou JP), le pipeline génère deux versions séparées. Le pdf.pdf audité est la version EN. Pas un bug.
- **Verdict**: Non applicable.

### 6) Press Release + Presentation both N/A
- **Hermes**: Fallback cassé.
- **OpenClaw**: CONFIRM. Missing both without documented search attempts is a gap.
- **Verdict**: P0.

### 7) Score 44/100
- **Hermes**: 44/100.
- **OpenClaw**: 46/100. Adjusted for: overstated "ALL" tables, language treated as P1, raised sourcing to P0.
- **Verdict**: Close agreement.

---

## D. Data Quality Issues (P0/P1)

### P0
- **Period/basis incoherence**: EPS conflicting actual/estimate pairs. Must state "Basis: GAAP/non-GAAP", "Period: FQx FYyyyy", enforce single-period coherence.
- **Mixed period aggregation**: Revenue/segments/net income mix annual vs quarterly. Segment totals must reconcile to same-period revenue within 1%.
- **Consensus vs guidance confusion**: EPS "$2.82" = analyst consensus for different period, presented as guidance. Must separate "Company guidance" from "Analyst consensus", both period-tagged.
- **Incomplete transcript coverage**: Guidance and segment analyses infer beyond transcript or omit "Not disclosed" with rationale.

### P1
- **ROE/ROIC not reproducible**: Computation source and formula absent; basis (average equity? NOPAT? tax rate?) not disclosed.
- **Cash flow comparatives**: Internally consistent but lacks cross-company normalization and unit clarity.
- **Unit clarity**: Unclear USD vs nominal "$"; "B" vs "bn"; negative signs vs parentheses.

---

## E. Visual/Layout Issues (F)

### ⚠️ Challenge: "ALL tables" → "Most tables"
- Hermes marked S5 (P0). OpenClaw: P1. Numeric-only tables less affected.

### P1 Issues
- **Systemic column overflow/wrapping**: Long labels (sources, commentary) wrap/bleed into adjacent columns; fixed column widths, no hyphenation/wrap rules.
- **🔴 Image-heavy PDF**: Content embedded as **images** by ReportLab; minimal selectable text → impairs copy/search, downstream QA, and accessibility. This also explains why emoji vanish in text extraction.
- **Font/emoji consistency**: Current artifact likely uses basic Helvetica/Arial subsets without color emoji support.

---

## F. Sources and Traceability (G)

### P0
- **No deep links** to primary sources (SEC 8-K/10-Q), IR press release, or deck. "Company filing / Calculated" is not auditable without URL + doc type + page/section + accessed-at timestamp.
- **Transcript source conflation**: MarketBeat/Motley Fool/Seeking Alpha are secondary; must cite actual source used, not generic aggregator page.

### P1
- **Lack of run metadata**: Missing model/provider, prompt version, collection timestamps, data providers (Finnhub/yfinance), report hash. Without these, regeneration and QA are hard.

---

## G. 🔴 NEW ISSUES MISSED IN HERMES AUDIT

| # | Issue | Severity |
|---|-------|----------|
| 1 | **PDF text layer/accessibility**: Majority of content is embedded as IMAGES (image XObjects); text selection/searching is impaired. This hinders audits and violates accessibility. | P0 |
| 2 | **No GAAP vs non-GAAP labeling** at section headers | P0 |
| 3 | **Missing explicit fiscal tags** on every table (e.g., "FQ2 FY2026 (13 weeks ending…)") to prevent period drift | P0 |
| 4 | **Currency and unit standardization absent** (USD code, shares in millions, margins in % with one decimal) | P1 |
| 5 | **No data freshness** (as-of dates) per source; time skew likely contributed to mismatches | P1 |
| 6 | **No "Methodology/Assumptions" appendix** (how forward P/E derived; which EPS basis; consensus source) | P2 |
| 7 | **No run metadata** (model, prompt version, commit hash) embedded in PDF footer or sidecar JSON | P1 |

---

## H. Section Gap Table (vs modele.pdf)

| Section | Status | Severity |
|---------|--------|----------|
| Earnings Documents | Present but incomplete; PR and Deck N/A without logged fallback | P0 |
| EPS & Revenue | Present but contradictory; basis/period incoherent | P0 |
| Highlights/Lowlights | Present but thin; repeats erroneous EPS miss | P1 |
| Operating Metrics | Present; mixes annual/quarterly; margins not reconciling | P0 |
| Cash Flow | Present; internally consistent; lacks unit/currency clarity and comps | P2 |
| Capital Efficiency | Present; no formula transparency; basis ambiguity | P1 |
| Segments | Present; uses annual totals in quarterly context; no geo breakdown | P0 |
| Forward P/E | Present; **best-structured section**; ensure EPS basis disclosed | P2 |
| Backlog | Marked N/A; should analyze implied backlog (customer prepayments, hyperscaler capex) | P1 |
| Guidance | Present but conflates consensus with company guidance; unclear periods | P1 |
| Verdict | Present; relies on contradictory metrics; must defer when core sections conflict | P1 |
| Sources | **Absent** as consolidated section | P0 |

---

## I. Root Causes

- Data normalization gaps: quarter tagging, GAAP/non-GAAP basis flags not enforced end-to-end
- Weak source binding: generic "Company filing / Calculated" substitutes for deep links with page anchors
- Prompt/contract too broad: sections accept mixed inputs; model fills gaps with inference
- Layout engine constraints: fixed-width tables without wrap rules; **image-heavy PDF pipeline**
- Missing run metadata and validation gates: no structural/period validation prior to render

---

## J. Fix Plan

### 🔴 P0 (data and sources first)

1. **Enforce period and basis coherence**
   - Require: period_tag, basis_tag per metric; reject cross-period mixes; fail closed on mismatch
   - Add validation: segments_sum ≤ revenue (same period) within 1%; EPS/Revenue tables must match period header

2. **Source traceability**
   - Attach deep links (SEC 8-K/10-Q item/page; IR PR URL; deck URL); include accessed-at timestamps
   - Split "Company guidance" vs "Analyst consensus" with explicit provider

3. **Transcript handling**
   - If transcript incomplete: mark sections "Not disclosed in transcript" instead of inferring

### 🟡 P1 (visuals, accessibility, language)

4. **Table rendering** — Auto-size columns; enable word-wrap/hyphenation; reduce font for long cells; **avoid rendering text as images**
5. **Accessibility/text layer** — Prefer true text in PDF; embed JP/emoji-capable fonts
6. **Language/style flags** — Add language=ja|en; template=standard|nami

### 🟢 P2 (quality polish)

7. **Capital efficiency transparency** — Show formulas and inputs; label GAAP/non-GAAP
8. **Backlog heuristic** — Provide analysis template for implied backlog
9. **Run metadata** — Embed model, prompt/version, data provider set, timestamps, commit hash in PDF footer + sidecar JSON

---

## K. Acceptance Criteria

**Data**
- All tables share same explicit period tag (e.g., FQ2 FY2026), GAAP/non-GAAP basis labeled
- Segment totals reconcile to revenue (±1%); no annual vs quarterly mixing
- EPS "actual vs estimate" uses correct period; consensus vs guidance separated and sourced

**Sources**
- Each metric/table cites auditable source (SEC/IR URL with doc type, page/section, accessed-at)
- PR and Deck: found or NOT_FOUND with 3+ attempted URLs logged
- Transcript: real source URL (not just aggregator)

**Visuals**
- No column bleed/overflow in any section; long cells wrap or shrink appropriately
- **PDF is text-selectable**; JP glyphs and emojis render correctly

**Content/Quality**
- No internal contradictions (EPS, revenue, net income)
- Backlog handled with reasoned approach when not officially reported
- Verdict reflects validated data; warns if key sections are partial/missing
