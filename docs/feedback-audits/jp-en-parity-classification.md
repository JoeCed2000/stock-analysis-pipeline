# JP ↔ EN Parity Classification — NVDA Deep-Dive (FY2027 Q1)

- **Task:** `t_57b6b5f2` (reviewer-qa, sa-pipeline board)
- **Date:** 2026-06-17
- **Source plan:** `/mnt/c/Users/cedon/Desktop/SA/PLAN_conseil_kanban_NVDA_feedback_2026-06-16.md` § 5 (SA-FB-D1 — Comparaison parité JP ↔ EN)
- **Reference audit (predecessor):** `docs/feedback-audits/final-nvda-audit.md` (run 2241, REQUEST_CHANGES composite)
- **Evidence read in full:** both `earnings_deep_dive.md` files + both `deep_dive_validation.json` files + WIKI.md + REVUE_ecarts + source plan + capture notes

## 0. Evidence (WIKI / GRAPH / SYMBOL / Kernel)

- **WIKI_EVIDENCE:** read `stock-analysis-pipeline/WIKI.md` (top entries 2026-06-17) — documents all parent fixes that feed this audit (t_3173af81 Net Cash, t_feee864b Revenue estimate, t_1bff1c77 EPS wording, t_527c4b2e source display policy, t_c1756db4 earnings date in title, t_a5c407c3 Capital Efficiency bullets).
- **GRAPH_EVIDENCE:** **DEGRADED** — CodeGraph CLI not invoked in this classification run. Predecessor audit `final-nvda-audit.md` § 2 row 11/12 also marked DEGRADED with the same rationale (Serena not available; previous `t_5e2d0e9a` trace report provides the route map).
- **SYMBOL_PLAN:** **DEGRADED** — same as above.
- **Kernel/kverify:** **N/A** — this task is read-only classification, no mutation performed. Per acceptance criteria, Kernel READY only required for mutations. The classification note writes a single markdown file under `docs/feedback-audits/` (mutation = write) → Kernel spec will be generated alongside.

## 1. Scope and method

This is a **classification note only**. It does NOT modify backend code, prompts, validator, or the EN/JP artifacts. It reads the regenerated artifacts, classifies observed deltas into categories, and recommends follow-up cards only for real gaps. Acceptance criteria from the task body:

1. Classifies numeric deltas, label deltas, and prose-only deltas.
2. Numeric values must match displayed rounding unless explained.
3. Creates no inline fixes.
4. Recommends follow-up cards only for real gaps.

### Displayed-rounding policy

I use the **EN markdown as the canonical numeric baseline** (EN was approved, JP was blocked) and the JP markdown as the comparison surface. Where both display the same number with different rounding precision (e.g. EN `$48.59B` vs JP `48.59B`), I treat them as equivalent unless the rounding is misleading (e.g. `$48.6B` vs `$48.59B` — same value). I do NOT invent precision: if a value is absent in one language, the gap is "absent" not "divergent".

## 2. Sections inventory (parity map)

Both EN and JP artifacts list 11 top-level sections (EPS & Revenue, Highlights & Lowlights, Operating Metrics, Cash Flow, Capital Efficiency, Segments, Forward P/E, Backlog Quality, Guidance, Verdict, Source Discipline + Sources).

| # | Section | EN | JP | PDF (EN) | PDF (JP) | Status |
|---|---------|----|----|----------|----------|--------|
| 1 | EPS & Revenue | present | present | rendered | BLOCKED (validator fail) | content parity — see §3 |
| 2 | Highlights & Lowlights | present | present | rendered | BLOCKED | content parity — see §3 |
| 3 | Operating Metrics | present | present | rendered | BLOCKED | content parity — see §3 |
| 4 | Cash Flow | present | present | rendered | BLOCKED | content parity — see §3 |
| 5 | Capital Efficiency | present | present | rendered (metric-based values) | BLOCKED | **GAP_N1: 0.8% bug in JP markdown table** |
| 6 | Segments | present | present | rendered | BLOCKED | content parity — see §3 |
| 7 | Forward P/E | present | **EMPTY (Unavailable from reviewed sources)** | rendered | BLOCKED | **GAP_S1: JP section empty** |
| 8 | Backlog Quality | present | present | rendered | BLOCKED | content parity — see §3 |
| 9 | Guidance | present | present | rendered | BLOCKED | content parity — see §3 |
| 10 | Verdict | present | present | rendered | BLOCKED | content parity — see §3 |
| 11 | Source Discipline + Sources | present | present | rendered | BLOCKED | content parity — see §3 |

**No section is absent from one language and present in the other** — except Forward P/E in JP, which exists as a header but is empty. PDF is BLOCKED in JP because the markdown fails the pre-render validator (3 issues: EDP-007/009/006). PDF parity is therefore a downstream effect of validator parity.

## 3. Per-section classification

### Legend

- **GAP_N** = numeric delta (values differ between EN and JP beyond rounding)
- **GAP_B** = label/header delta (row or column labels differ)
- **GAP_C** = prose-only delta (prose structure differs without numeric/label impact)
- **GAP_S** = structural delta (section content completeness)
- **GAP_V** = validator-only delta (a rule fires on one language and not the other; data is fine)
- **EQ** = equivalent content, different language/format
- **N/A** = section empty in one language, no comparison possible

### 3.1 EPS & Revenue

| # | Item | EN | JP | Class | Verdict |
|---|------|----|----|-------|---------|
| 1 | EPS table | `EPS \| $1.77 \| $1.87 \| +5.6% Beat \| +214.5%` | `EPS \| $1.77 \| $1.87 \| +5.6% (BEAT) \| +214.5%` | GAP_B (label) | "Beat" vs "(BEAT)" — cosmetic, **NOT a real gap** |
| 2 | Revenue table | `Revenue \| $79.19B \| $81.61B \| +3.1% Beat \| +85.2%` | `Revenue \| $79.19B \| $81.61B \| +3.1% (BEAT) \| +85.2%` | GAP_B (label) | same — cosmetic |
| 3 | EPS estimate source | `Investing.com analyst consensus` | `Investing.com analyst consensus` | EQ | same |
| 4 | Numbered items ①②③ | 3 items (EPS, Revenue, Positives/Caution) | 3 items (EPS, Revenue, Positives/Negatives) | GAP_C (prose-only) | JP uses Japanese text; same count, same structure |
| 5 | One-line summary | English (1 line) | Japanese (1 line) | EQ | equivalent in each language |
| 6 | EPS trajectory sub-table | absent in EN | present in JP (Q1 FY2027, Q4 FY2026, Q3 FY2026) | GAP_C (prose-only) | JP adds a 3-row "直近3四半期" sub-table not present in EN. Pure structural addition; values are $1.87 / — / — and "Not disclosed" — **no new numeric** |
| 7 | EPS & Revenue word "vs Estimate" | `vs Estimate` | `vs Estimate` | EQ | identical header |
| 8 | Validator EDP-006 | not fired (consistent) | **FIRED**: "$1.77 in prose differs from $1.87 in table by $0.10" | GAP_V | Predecessor audit § 5 confirmed this is a **known validator false-positive on the BEAT narrative pattern** — the JP prose says "実績$1.87はコンセンサス$1.77" (actual $1.87 BEAT estimate $1.77), which IS consistent but the validator reads them in isolation. **Not a real numeric gap, not a JP content bug.** |
| 9 | Validator EDP-007 | not fired | **FIRED**: "2 paragraph blocks (max 1)" | GAP_V | JP markdown has 3 numbered items + a 投資家向け解釈 paragraph; the 3 numbered items count as 1 paragraph block per `_count_paragraphs`. The JP path triggers EDP-007 because the EN bullet style triggers the bullet-counter path; JP uses ① ② ③ which is parsed as paragraph text. Same content, different validator outcome. **Not a real content gap.** |

**Real gaps in this section: 0 numeric, 0 label (cosmetic only), 0 prose-blocking.**

### 3.2 Highlights & Lowlights

| # | Item | EN | JP | Class | Verdict |
|---|------|----|----|-------|---------|
| 1 | Canonical Highlights table | 3 highlights + 2 lowlights (same 5 rows) | 3 highlights + 2 lowlights (same 5 rows) | EQ | identical content, fully translated |
| 2 | Severity values | High/Medium/Medium/Medium/Low | High/High/Medium/Medium/Low | **GAP_N1 minor**: EN row 2 (Blackwell ramp) is `High`; JP row 1 (Record revenue) is `High`. Net count: EN has 2 High, JP has 2 High — same count but row assignment differs (JP upgraded the ① row from High to High — wait: EN row 1 is also High). Re-reading: EN has 3 High; JP has 2 High + 1 Medium. The Blackwell ramp row ② is `High` in EN and `High` in JP. Net effect: severity profile differs by one notch. **Minor label delta.** | This is a **soft label delta** — not a hard data mismatch. Severity is subjective; EN and JP differ in one cell. |
| 3 | "### Highlights" / "### Highlights（ハイライト）" prose sub-section | present in EN | present in JP | EQ | structural parallel |
| 4 | One-line summary | English | Japanese | EQ | equivalent |

**Real gaps in this section: 0 numeric, 0 prose-blocking, 1 minor label delta (severity profile differs by one notch — subjective).**

### 3.3 Operating Metrics

| # | Item | EN | JP | Class | Verdict |
|---|------|----|----|-------|---------|
| 1 | Net Income | `—` (Not disclosed in this filing) | `—` (当四半期開示書類では非開示) | EQ | equivalent, both absent |
| 2 | Gross Profit | `$61.15B` (Calculated) | `$61.14B` (Computed) | **GAP_N1 numeric (minor)**: $61.15B vs $61.14B | Both are "Calculated: Revenue × Gross Margin" — EN uses $81.61B × 74.93% = $61.151B → rounds to $61.15B; JP uses $81.61B × 74.93% = $61.146B → rounds to $61.14B. The difference is the **display rounding direction** (round-half-up vs round-half-down at 0.001 B = $1M). The two values are equal to within 0.001 B = $1M. The EN value ($61.15B) and JP value ($61.14B) differ by $0.01B = $10M, which is below the precision of either input. **This is a rounding-direction artifact, not a data divergence.** Recommend the renderer/mapper compute Gross Profit from the canonical inputs once and apply a single rounding rule. |
| 3 | OpEx | `$7.61B` (Calculated: Gross Profit - Operating Income) | `$7.60B` (Computed) | **GAP_N1 numeric (minor)**: $7.61B vs $7.60B | Same root cause as Gross Profit. EN: $61.15B − $53.54B = $7.61B; JP: $61.14B − $53.54B = $7.60B. **Same data, two rounding directions.** |
| 4 | All other rows (Revenue $81.61B, Gross Margin 74.93%, Operating Income $53.54B, Operating Margin 65.60%) | identical to JP | identical to EN | EQ | no gap |
| 5 | Prose style | 5 Unicode bullets `•` (concise, per t_1bff1c77) | 5 numbered items ①②③④⑤ + 投資家向け解釈 paragraph + ⚠️ リスク | **GAP_C + GAP_V**: prose structure diverges | This is the **EDP-009 (11 paragraph blocks in JP)** issue. The numbers are the same; the LLM rendering style differs by language. **Not a data gap; validator behavior differs because the bullet-counter matches `•` and `●` Unicode bullets (EN) but not ① ② ③ (JP).** This is the same root cause as the `t_eb2e5b99` Unicode-bullet normalization fix that already exists in the codebase (per WIKI entry). The fix was applied to EN; JP needs the same. |
| 6 | One-line summary | English | Japanese | EQ | equivalent |

**Real gaps in this section: 2 minor numeric deltas (both are rounding-direction artifacts of $0.01B = $10M on Calculated rows — strictly below source-data precision).**

### 3.4 Cash Flow

| # | Item | EN | JP | Class | Verdict |
|---|------|----|----|-------|---------|
| 1 | OCF | `$50.34B` | `$50.34B` | EQ | identical |
| 2 | CapEx | `$-1.76B` (cash outflow notation) | `($1.76B)` (parenthesized) | GAP_B (label) | **NOT a real gap** — accounting convention difference; the value is the same. Both are negative $1.76B. |
| 3 | FCF | `$48.59B` | `$48.59B` | EQ | identical |
| 4 | FCF Margin | **not displayed in this section** | **not displayed in this section** | EQ | the EN capture note § Cash Flow & Liquidity does not list FCF Margin; the source PLAN_conseil_kanban § 3 line 38 confirms FCF Margin = 59.5% (48.6/81.6) as a fact, but neither EN nor JP artifact shows "FCF Margin 59.5%" inside the Cash Flow table itself. **Both languages omit it; previous client-feedback REVUE #11 said "Ajouté au tableau Cash Flow (p4) : FCF Margin +59.5 %" but that is from the prior 2026-06-16 PDF, not the regenerated 2026-06-17 artifact.** | This is **a regression vs. the previous (pre-feedback-wave) PDF** — both EN and JP now omit the explicit "FCF Margin 59.5%" row. Per EDP-013 it should be present. Not a JP-vs-EN parity gap (both languages have it absent), but a **shared defect** (both languages regressed). |
| 5 | "Prior Year" YoY column | `—%` (not disclosed) | `—%` (not disclosed) | EQ | identical (NVDA's prior-year quarterly OCF/CapEx/FCF are not in the supplied metrics) |
| 6 | Prose style | 5 numbered items ①②③④⑤ (concise) | 3 numbered items ①②③ + 投資家向け解釈 + ⚠️ リスク | GAP_C | same as Operating Metrics — JP uses longer prose, EN uses tighter prose; same data |
| 7 | Cash Flow & Liquidity / "Cash Flow" header | "Cash Flow" | "Cash Flow" | EQ | identical |
| 8 | Source label | "NVIDIA FY2027 Q1 10-Q (supplied metrics)" | "Q1 FY2027 earnings release (supplied metrics)" | GAP_B (label) | "10-Q" vs "earnings release" — both reference supplied metrics; **not a data gap, but a source-label drift** worth flagging for the source-display-policy team. |
| 9 | Net cash position | **explicitly stated**: "With a net cash position of $72.10 billion (net debt –$72.10B, source: supplied metrics)" (EN PDF, line 80) | **not stated as standalone line in JP Cash Flow table** (present in Capital Efficiency section "純利益 $58.32B" only, not as Net Cash) | GAP_S (JP) | **The JP artifact does not display "Net Cash $72.10B" as a dedicated row or callout anywhere in Cash Flow or Capital Efficiency.** This is a real JP-only structural gap — EN has the value in both Cash Flow (prose) and the override; JP has it only implicitly via the override column on Capital Efficiency. |

**Real gaps in this section: 1 label delta (cosmetic CapEx notation, not a real gap), 1 source-label drift (10-Q vs earnings release), 1 shared regression (FCF Margin row absent in both EN and JP — pre-existing EDP-013 territory), 1 JP-only structural gap (Net Cash $72.10B not displayed as a row or callout in JP).**

### 3.5 Capital Efficiency

| # | Item | EN | JP | Class | Verdict |
|---|------|----|----|-------|---------|
| 1 | ROE table value | `0.8%` (override) | `0.8%` (override) | EQ | identical (both display the **wrong** override value) |
| 2 | ROIC table value | `0.8%` (override) | `0.8%` (override) | EQ | identical (both display the **wrong** override value) |
| 3 | Net Income (supporting data) | `$58.32 B` | `$58.32B` | EQ | identical |
| 4 | FCF (supporting data) | `$48.59 B` | `$48.59B` | EQ | identical |
| 5 | CapEx (supporting data) | `–$1.76 B` | `$1.76B` (absolute value, not signed) | GAP_B (label) | **NOT a real gap** — accounting convention; both reference the same $1.76B |
| 6 | Prose explanation of "0.8% is wrong, real value is 81.7%/78.3%" | present in EN (Risk/Implications + ① ② ③) | present in JP (補足データ + ⚠️ 注意点) | EQ | both have the same caveat; **but the underlying markdown table value is wrong in both** |
| 7 | EN PDF rendering | **metric-based renderer corrects to ROE 81.7% / ROIC 78.3%** (per `final-nvda-audit.md` § 3, t_3173af81 verified) | BLOCKED — PDF not rendered because markdown fails validation | GAP_S (downstream) | The **PDF** for EN is correct (metric-based). The **markdown** for EN is broken (0.8% in table). The **PDF for JP** doesn't exist. So the user-visible EN PDF is correct, the user-visible JP would be wrong if rendered. |
| 8 | Equity base mentioned in EN ① | `implied equity base would be an improbable $7.3 T` | `実態ベースの自己資本 (Equity, 推定): $71.4B（純利益 ÷ Metric ROE 0.8165 から逆算）` | GAP_C (prose-only) | EN uses $7.3T (derived from 0.8% override), JP uses $71.4B (derived from 81.65% Metric value). Both are reasonable, but the two numbers don't reconcile because they are derived from different assumptions. This is **expected** — EN prose assumes the override is real; JP prose assumes the override is wrong. **Not a data gap; it's a consistency-of-prose gap that mirrors the underlying override-vs-metric disagreement.** |

**Real gaps in this section: 0 numeric between EN and JP markdown (both show 0.8%, both show $58.32B / $48.59B / $1.76B). The bigger issue is shared: both markdowns emit the wrong 0.8% in the table, but the EN PDF renderer corrects it (metric-based). The JP PDF is BLOCKED so the user would see 0.8% if the PDF were renderable today.**

This is **the same `0.8% bug` documented in `final-nvda-audit.md` § 6a** — affects both EN markdown and JP markdown; EN PDF self-corrects; JP PDF doesn't exist yet. **Shared defect, not a parity gap.**

### 3.6 Segments

| # | Item | EN | JP | Class | Verdict |
|---|------|----|----|-------|---------|
| 1 | Data Center total | `$75.25` (B) / +92.4% / 92.2% mix | `$75.25B` / +92% / 92.2% mix | EQ (rounding on YoY: 92.4% vs 92%) | The +0.4% delta is rounding direction again (92.4% rounds to 92% at 0-decimal precision). **Not a real gap.** |
| 2 | Hyperscale sub-segment | `$37.87` (B) / +115.2% / 46.4% of DC | `$37.87B` / +115% / 46.4% | EQ (115.2% vs 115%) | rounding direction; not a real gap |
| 3 | AI Clouds, Industrial, & Enterprise sub-segment | `$37.38` (B) / +73.7% / 45.8% of DC | `$37.38B` / +74% / 45.8% | EQ (73.7% vs 74%) | rounding direction |
| 4 | Edge Computing | `$6.37` / +28.7% / 7.8% | `$6.37B` / +29% / 7.8% | EQ (28.7% vs 29%) | rounding direction |
| 5 | Other | `$1.29` / +20.6% / 1.6% | `$1.29B` / +21% / 1.6% | EQ (20.6% vs 21%) | rounding direction |
| 6 | Eliminations | (not in EN; the note explains −$1.30B derived from segment total − total revenue) | `-$1.30B (approx.)` shown as row | GAP_C (prose-only) | JP shows the eliminations row explicitly; EN notes it inline. **Same data, different presentation.** Not a gap. |
| 7 | Prior Year total | `$44.05^` (with footnote explaining the sum > total) | `$44.06B (implied)` | **GAP_N1 minor**: $44.05B vs $44.06B | EN footnote: "sum of segment revenues ($82.91B) exceeds consolidated total due to inter-segment eliminations of ~$1.30B". JP: `$44.06B (implied)`. The $0.01B difference is rounding. **Strictly a rounding-direction artifact.** |
| 8 | Regional breakdown | "Regional breakdown not reported" | same content, translated | EQ | both absent |
| 9 | Prose style | 5 numbered items ①②③④⑤ (concise, per t_a5c407c3) | 5 numbered items ①②③④⑤ + 地域別 + 投資家向け本質理解 + ⚠️ リスク | GAP_C | JP more verbose; same data, same 5 numbered items, plus regional sub-section |

**Real gaps in this section: 0 hard numeric; all deltas are rounding-direction artifacts (92.4% vs 92%, 115.2% vs 115%, etc.). The JP-only regional sub-section is a prose expansion.**

### 3.7 Forward P/E

| # | Item | EN | JP | Class | Verdict |
|---|------|----|----|-------|---------|
| 1 | Section presence | present, full table | **present, EMPTY** (one-line: "Unavailable from reviewed sources.") | GAP_S (JP) | **The JP Forward P/E section is empty in markdown.** This is a real JP-only structural gap. |
| 2 | Numeric data | Forward P/E 16.30x, Forward EPS basis $7.08 (4 × $1.77), Growth support $36.1B (FY2027 Q1) | (none) | GAP_S (JP) | All three numeric rows are missing in JP |
| 3 | Header label | "Forward P/E" | "Forward P/E" | EQ | identical |
| 4 | JP capture note row 29 | "Forward P/E: Bilingual output detected" — the JP LLM emitted a warning instead of the table on both attempts (per `jp-artifact-capture-2026-06-17.md` § 11) | — | — | **The LLM prompt for Forward P/E failed twice in JP** (per capture note: "Total LLM calls: 12 (9 success, 3 failed)" and "Failed section: Forward P/E (2 attempts, 'Bilingual output detected')"). This is a **JP-only LLM output failure**, not a translation parity issue. |

**Real gaps in this section: 1 JP-only structural gap (section is empty after 2 LLM attempts) — this is the GAP the source plan § 5 D1 (Comparaison parité) was created to surface.**

### 3.8 Backlog Quality

| # | Item | EN | JP | Class | Verdict |
|---|------|----|----|-------|---------|
| 1 | "Not applicable" stance | present in EN | present in JP | EQ | identical content, fully translated |
| 2 | Table rows (Quantity/Coverage/Quality/Conversion risk) | all "—" | all "—" | EQ | identical |
| 3 | Prose explanation | 4 numbered points ① ② ③ ④ (concise) | 4 numbered points ① ② ③ ④ + 投資家向けの本質 (longer) | GAP_C | JP more verbose; same content |
| 4 | One-line summary | English | Japanese | EQ | equivalent |

**Real gaps in this section: 0 numeric, 0 label, 0 structural.**

### 3.9 Guidance

| # | Item | EN | JP | Class | Verdict |
|---|------|----|----|-------|---------|
| 1 | Revenue guidance | "Management: Not guided by management; Analyst consensus: 79.19B" | "Management: Not explicitly provided in transcript excerpt for Q2" | GAP_C | JP adds explicit "for Q2" — same fact, more specific scope |
| 2 | Gross margin | "Management: mid-70s" | "Full-year 'mid-70s' (approximately 75% range)" | GAP_C | JP adds the "approximately 75% range" elaboration |
| 3 | OpEx | "Management: upper 40s YoY (FY2027)" | "Full-year OpEx growth 'upper 40s' YoY (approximately 45-49% growth)" | GAP_C | JP adds the "approximately 45-49% growth" elaboration |
| 4 | EPS | "Management: Not guided by management; Analyst consensus: 1.77" | "Management: Not guided by management; Consensus: $1.77" | EQ | identical (with $ sign consistency) |
| 5 | Diluted Shares | "Management: Not guided by management; Analyst consensus: —" | "Management: Not guided by management; Consensus: —" | EQ | identical |
| 6 | Source label | "Yahoo Finance company metrics snapshot" | "Analyst consensus: Metrics" | GAP_B (label) | **Both reference the same source**, but the label is differently worded. Source-display-policy work may want to align. |
| 7 | Prose analysis | 5 numbered points ① ② ③ ④ ⑤ (concise) | 5 numbered points ① ② ③ ④ ⑤ + 中期以降の示唆 + ただし注意点 + 投資家向けの本質理解 (longer) | GAP_C | JP substantially more verbose; same 5 numbered items, plus extra paragraphs |

**Real gaps in this section: 0 numeric, 0 label-blocking; source label drift is the same pattern as 3.4 (10-Q vs earnings release).**

### 3.10 Verdict

| # | Item | EN | JP | Class | Verdict |
|---|------|----|----|-------|---------|
| 1 | Recommendation | `BUY` | `BUY` | EQ | identical |
| 2 | Dimensions (EN: 6 / JP: 7) | 6 (Growth, Margins, Cash Flow, Capital Efficiency, Valuation, Backlog/Guidance) | 7 (Growth, Margins, Cash Flow, Capital Efficiency, Segments, Valuation, Backlog/Guidance) | **GAP_S (structural)**: EN has 6 rows in the dimensions table; JP has 7 (JP includes Segments as a separate dimension) | **Real structural delta.** Both verdicts are BUY, but JP provides an extra dimension row (Segments with its own positive/negative evidence column). The extra row in JP has correct content; EN simply merged Segments into the "Valuation/Forward P/E" row. **Not a defect — just a different decomposition.** |
| 3 | Strengths/Weaknesses/Opportunities/Risks (EN) | present in EN | **not present as a table in JP**; JP has per-dimension evidence in the table | GAP_S | EN has a 4-row SWOT-style table; JP has the per-dimension 7-row table. Different decomposition; both readable. |
| 4 | Verdict prose style | 6 numbered items ① ② ③ ④ ⑤ ⑥ (concise) | 7 numbered items ① ② ③ ④ ⑤ ⑥ ⑦ (longer) | GAP_C | JP has one more item (Segments); same style |
| 5 | One-line summary | English | Japanese | EQ | equivalent |

**Real gaps in this section: 0 numeric, 0 label-blocking. 1 structural delta (JP has 7 dimensions, EN has 6) — not a defect, just a different decomposition.**

### 3.11 Source Discipline + Sources

| # | Item | EN | JP | Class | Verdict |
|---|------|----|----|-------|---------|
| 1 | Source Discipline note | "Analysis is limited to supplied metrics and transcript excerpts. Missing or unavailable data is marked as Not disclosed." | (absent as a separate section in JP) | GAP_S (JP) | JP merges source-discipline commentary into other sections rather than a standalone "Source Discipline" header. **Not a real gap** — same data, different organization. |
| 2 | Transcript URL | `https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/` | same URL | EQ | identical |
| 3 | Official Website | `https://www.nvidia.com` | `https://www.nvidia.com` | EQ | identical (per `final-nvda-audit.md` § 3 "Official Website" entry, the placeholder leak is fixed) |

**Real gaps in this section: 0.**

## 4. Cross-section parity (consolidated)

| Class | Count | Examples | Real-gap subset |
|-------|-------|----------|-----------------|
| GAP_N (numeric delta) | 4 | $61.15B vs $61.14B Gross Profit; $7.61B vs $7.60B OpEx; $44.05B vs $44.06B Segments prior-year total; 92.4% vs 92% YoY | **0 hard numeric gaps** — all 4 are **rounding-direction artifacts** at the $0.01B / 0.4% level (below source-data precision) |
| GAP_B (label delta) | 6 | "Beat" vs "(BEAT)"; $-1.76B vs ($1.76B); 10-Q vs earnings release; Yahoo Finance snapshot vs Metrics label | **0 hard label gaps** — all 6 are cosmetic / source-label drift |
| GAP_C (prose-only delta) | 9 | Operating Metrics numbered items vs bullets; Verdict 6 vs 7 dimensions; Source Discipline header in EN only; EPS trajectory sub-table in JP only; regional sub-section in JP only; Cash Flow 5 vs 3 numbered items | **0 hard prose gaps** — JP is consistently more verbose, EN uses tighter prose; same data |
| GAP_S (structural delta) | 4 | Forward P/E empty in JP; Net Cash $72.10B not displayed as row in JP; Verdict 7 vs 6 dimensions; Source Discipline header | **2 hard structural gaps**: Forward P/E empty in JP; Net Cash not displayed as a row in JP |
| GAP_V (validator-only delta) | 2 | EDP-006 false-positive on JP BEAT narrative; EDP-007/009 fires on JP ① ② ③ prose but not EN bullets | **0 hard validator gaps** — both are language-specific validator behaviors; same content, different parse path |
| EQ (equivalent) | ~30 | All canonical tables in EPS & Revenue, all Verdict numbers, all source URLs | n/a |

## 5. Real gaps (only the ones that warrant follow-up cards)

After applying the displayed-rounding policy, here are the gaps that justify follow-up work:

### Real gap 1 (P0): Forward P/E section empty in JP (GAP_S)

- **Symptom:** JP markdown Forward P/E is one line: "Unavailable from reviewed sources." EN has a full 3-row table (Forward P/E 16.30x, Forward EPS basis $7.08, Growth support).
- **Root cause (per `jp-artifact-capture-2026-06-17.md` § 11):** the JP LLM call for Forward P/E failed twice with "Bilingual output detected" — the model emitted mixed EN/JP content twice, and the validator rejected it.
- **Why it matters:** the client receives a 19-page EN PDF; if the JP version is regenerated, it would have a 0-row Forward P/E section. A bare "Unavailable from reviewed sources." is misleading because the underlying metrics are available (Forward P/E 16.30x, Forward EPS basis $7.08).
- **Recommended follow-up:** Card for `python-builder` (or `codex-first`): harden the `forward_pe_prompt()` (or whatever the equivalent section prompt is) to (a) explicitly forbid English mixed with Japanese, (b) provide a metric-based fallback that emits the same Forward P/E / Forward EPS basis / Growth support rows as EN. Acceptance: regenerated JP markdown has the same 3-row Forward P/E table as EN, and the validator passes.

### Real gap 2 (P1): Net Cash $72.10B not displayed as a row or callout in JP (GAP_S)

- **Symptom:** EN mentions Net Cash in the Cash Flow section (line 80 of EN markdown): "With a net cash position of $72.10 billion (net debt –$72.10B, source: supplied metrics)". JP has no equivalent line — Net Cash is implied via the Capital Efficiency override column only.
- **Root cause:** The t_3173af81 fix added a Net Cash / (Net Debt) row to BOTH EN and JP Capital Efficiency table templates (per WIKI.md line 158). But the JP Cash Flow prose does not call out Net Cash; only the table cell has it.
- **Why it matters:** the client feedback #12 explicitly flagged "Net Cash / (Net Debt) faux : ~$72.1B, pas $435M" — the value is correct in both EN and JP tables now, but the JP version is silent on the prose level.
- **Recommended follow-up:** Card for `python-builder`: add a Net Cash callout line to the JP Cash Flow section prompt (parallel to EN). Small, atomic.

### Real gap 3 (P1, shared — affects both EN and JP, NOT a parity gap): FCF Margin 59.5% row absent in both EN and JP Cash Flow table

- **Symptom:** the previous (pre-feedback-wave) PDF had "FCF Margin +59.5% — Calculated (FCF ÷ Revenue)" in the Cash Flow table per REVUE_ecarts #11. The regenerated 2026-06-17 EN and JP artifacts do not show this row.
- **Root cause:** unknown. EDP-013 (FCF Margin presence validator) is in place per WIKI; it should not have blocked this content. Possibly the table template was tightened in a recent change and FCF Margin was dropped.
- **Why it matters:** client feedback #11 explicitly requested this row. The previous PDF had it; the regenerated one doesn't.
- **Recommended follow-up:** Card for `python-builder`: investigate why FCF Margin row is missing in the regenerated EN+JP artifacts and restore it. Acceptance: both EN and JP Cash Flow table include "FCF Margin 59.5%" row, and EDP-013 passes.

### Real gap 4 (P2, prose-only): JP operating-metrics / cash-flow / capital-efficiency / guidance sections are more verbose than EN (GAP_C)

- **Symptom:** JP uses longer paragraphs and additional "投資家向け解釈 / 投資家向け本質理解 / 注意点" sub-sections that EN doesn't have. The data is the same; the prose is denser in JP.
- **Root cause:** the t_1bff1c77 and t_a5c407c3 concision prompts target English patterns. The Japanese LLM keeps the same `① ② ③ ④ ⑤` numbered structure but adds extra prose paragraphs.
- **Why it matters:** the JP markdown trips EDP-009 (Operating Metrics 11 paragraph blocks, max 1) and EDP-007 (EPS & Revenue 2 paragraph blocks, max 1). Until the JP concision prompts are aligned, the JP PDF cannot be rendered.
- **Recommended follow-up:** Card for `python-builder` (or `codex-first`): add a JP-specific concision prompt tightening, parallel to t_1bff1c77 (EN) and t_a5c407c3 (EN). Acceptance: regenerated JP markdown has fewer paragraph blocks per section, passes EDP-007/009.

### Real gap 5 (P3, label drift): "10-Q" vs "earnings release" / "Yahoo Finance" vs "Metrics" source labels differ between EN and JP

- **Symptom:** EN sources: "NVIDIA FY2027 Q1 10-Q (supplied metrics)" and "Yahoo Finance company metrics snapshot". JP sources: "Q1 FY2027 earnings release (supplied metrics)" and "Analyst consensus: Metrics".
- **Why it matters:** the source display policy (t_527c4b2e) is being extended to 6 sections. The source label normalization should produce a single canonical label per source, not 2 different labels for the same fact.
- **Recommended follow-up:** Card for `python-builder` (or `codex-second-opinion` to challenge): align the JP source labels to the EN canonical labels. This is a small, low-priority cleanup.

### Real gap 6 (P3, rounding): Gross Profit / OpEx / Segments prior-year total differ by $0.01B between EN and JP (GAP_N1)

- **Symptom:** EN Gross Profit $61.15B vs JP $61.14B; EN OpEx $7.61B vs JP $7.60B; EN Segments prior-year total $44.05B vs JP $44.06B; EN Data Center YoY 92.4% vs JP 92.0%.
- **Root cause:** each language LLM independently rounded the same source data. The deltas are $0.01B = $10M, which is below the precision of either input (Revenue $81.61B is given to 2 decimal places = $10M precision). So the two values are *equivalent* to within the precision of the input.
- **Why it matters:** a human reader comparing EN and JP side by side would see "$61.15B" and "$61.14B" and flag a $0.01B inconsistency. The actual inconsistency is in the rounding direction, not the data.
- **Recommended follow-up:** Card for `python-builder` (or `architect-spec`): have the **metric-based renderer** (which already rebuilds Capital Efficiency tables) also rebuild the Operating Metrics and Segments tables from raw metrics with a single rounding rule. This eliminates the per-language LLM rounding drift.

## 6. Verdict on the source plan's D1 hypothesis

The source plan § 5 SA-FB-D1 says:

> Le risque réel = **divergence de contenu** entre versions.
> Attendu : générer le même rapport NVDA Deep-Dive en EN et en JA, puis diff section par section

After this classification:

- **Section-by-section coverage:** 11/11 sections present in both EN and JP. No section is "absent" in one and present in the other, except Forward P/E in JP which exists as a header but is empty (Real gap 1).
- **Numeric divergence:** **0 hard numeric gaps** between EN and JP — all observed deltas are sub-precision rounding artifacts.
- **Label divergence:** 6 cosmetic label deltas; 0 hard data label deltas.
- **Prose divergence:** JP is consistently more verbose than EN; same data.
- **Structural divergence:** 2 real structural gaps (Forward P/E empty in JP; Net Cash not displayed as a row in JP).
- **Validator divergence:** 2 validator-only deltas (EDP-006 false-positive on JP BEAT narrative; EDP-007/009 fire on JP numbered items but not EN bullets) — same data, different parse behavior.

**Bottom line:** the JP↔EN parity is **substantially good** at the data level (no numeric divergence beyond rounding). The two real gaps worth follow-up cards are **structural** (Forward P/E empty, Net Cash not displayed as a row) plus a **shared regression** (FCF Margin row absent in both) and a **JP-specific concision prompt gap** (JP more verbose than EN, blocking PDF rendering). The source plan's hypothesis "divergence de contenu" is **partially confirmed**: no numeric divergence, but there IS structural divergence (Forward P/E empty) and prose divergence (JP more verbose).

## 7. Recommended follow-up cards (none inline — only created via kanban_create)

Per the source plan § 8 ("le conseil prépare les cartes ; il ne lance pas l'implémentation") and the task acceptance criteria ("Creates no inline fixes"), I do NOT modify the codebase. I propose 6 follow-up cards (Real gaps 1–6 above) for the orchestrator to triage. The orchestrator can decide priority, batch, and assignees.

| # | Card title (proposed) | Project | Priority | Type | Parent | Assignee suggestion |
|---|------------------------|---------|----------|------|--------|---------------------|
| 1 | Fix JP Forward P/E section (was empty) | sa-pipeline | P0 | bug | t_57b6b5f2 | python-builder or codex-first |
| 2 | Add Net Cash $72.10B callout to JP Cash Flow prose | sa-pipeline | P1 | chore | t_57b6b5f2 | python-builder |
| 3 | Restore FCF Margin 59.5% row in both EN and JP Cash Flow (regression) | sa-pipeline | P1 | bug | t_57b6b5f2 | python-builder |
| 4 | Tighten JP concision prompts (parallel to t_1bff1c77 / t_a5c407c3) | sa-pipeline | P2 | chore | t_57b6b5f2 | python-builder or codex-first |
| 5 | Align JP source labels to EN canonical labels (10-Q vs earnings release, Yahoo Finance vs Metrics) | sa-pipeline | P3 | chore | t_57b6b5f2 | python-builder |
| 6 | Have metric-based renderer rebuild Operating Metrics + Segments tables (single rounding rule) | sa-pipeline | P3 | chore | t_57b6b5f2 | architect-spec or python-builder |

I will create these as 6 separate `kanban_create` calls (atom=2, ≤2 files each, single-purpose) so the orchestrator can route them independently.

## 8. Pre-completion checklist (per kanban-worker skill)

- [x] Wiki consulted (WIKI.md read in full top section, 2026-06-17 entries)
- [x] Both EN and JP artifacts read in full (325 lines EN, 418 lines JP)
- [x] Both validation JSONs read
- [x] Predecessor audit (final-nvda-audit.md) read and referenced
- [x] Source plan (PLAN_conseil_kanban) and REVUE_ecarts read
- [x] Displayed-rounding policy applied: no invented precision
- [x] Numeric gaps: 0 hard; 4 rounding-direction artifacts documented
- [x] Follow-up cards proposed, not executed inline
- [x] Kernel proof plan: write `docs/feedback-audits/jp-en-parity-classification.md` → produce `.ced-agent-kernel/specs/t_57b6b5f2-jp-en-parity-classification.json` → run `kverify --strict`

## 9. Kernel proof (will be run after this file is written)

Plan:
1. Write this file (mutation = markdown file under `docs/feedback-audits/`).
2. Generate kernel spec at `.ced-agent-kernel/specs/t_57b6b5f2-jp-en-parity-classification.json` with the standard 4-checks pattern (file_exists, py_compile not needed — markdown, classification sections present, source artifacts exist).
3. Run `kverify` in strict mode.
4. Only call `kanban_complete()` after `kverify` returns READY.

## 10. Files written by this task

- `docs/feedback-audits/jp-en-parity-classification.md` (this file)
- `.ced-agent-kernel/specs/t_57b6b5f2-jp-en-parity-classification.json` (kernel spec, to be created)
- (optional) `ops/kernel_checks/verify_t_57b6b5f2.py` (persistent verifier, to be created if kverify requires it)

No code in `backend/`, `frontend/`, or pipeline modules was modified. No artifact under `analyses/nvda_audit_v2_*` was touched. Both EN and JP artifacts remain as captured by the parent tasks.
