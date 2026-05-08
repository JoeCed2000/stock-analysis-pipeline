# Gap Analysis — AAPL Deep Dive PDF vs Nami Model

## Summary
- **76 placeholders** found (15 "Not available", 8 "N/A", 48 "?", 2 "Not disclosed", 2 "Not guided", 1 "—")
- **8 artifact types** (::, *, !!, >>, ^^, **, [], ? numbering)
- **5 data pipeline gaps** (data exists but not flowing to PDF)
- **2 formatting bugs** (decimal instead of %, inconsistent EPS)

---

## P0 — CRITICAL (visual quality destroyers)

### P0.1 Markdown syntax leaking into PDF
| Artifact | Found in section | Expected |
|----------|-----------------|----------|
| `::` | EPS & Revenue header | Clean "EPS & Revenue" |
| `*` | Highlights/Lowlights bullets | Clean bullet or dash |
| `!!` | Lowlight header | Clean "Lowlight" label |
| `>>` | Verdict, Segment, Guidance headers | Clean section title |
| `^^` | Forward P/E header | Clean "Forward P/E" |
| `**` | Overall assessment | Clean text or bold |
| `[]` | Backlog header | Clean "Backlog" |
| `?` numbering | Highlights table (all items) | Sequential 1, 2, 3... |

**Root cause**: PDF renderer passes markdown-formatted text directly without stripping markdown syntax. The LLM outputs markdown, the renderer should convert it.

**Fix location**: `backend/earnings_deep_dive/pdf_renderer.py` — add markdown-to-clean-text conversion before rendering.

### P0.2 "Not available" for Severity in Highlights/Lowlights table
- Every Highlight/Lowlight row has "Not available" in the Severity column
- The LLM prompt should request Severity (High/Medium/Low) explicitly

**Fix location**: `backend/earnings_deep_dive/prompts.py` — add Severity requirement to Highlights prompt.

---

## P1 — IMPORTANT (data pipeline gaps)

### P1.1 Revenue estimate = "Not available"
- EPS estimate ($2.39) is correctly extracted but Revenue estimate shows "Not available"
- yfinance has `revenueEstimate` — needs to be extracted and passed through

**Fix location**: `backend/sources_collector.py` — add revenue estimate extraction.

### P1.2 Forward EPS basis = "Not available"
- Consensus EPS estimate ($2.39) exists but Forward EPS basis field is empty
- Should compute from `eps_estimate * 4` or use `forwardEps`

**Fix location**: `backend/earnings_deep_dive/mapper.py` — compute Forward EPS basis.

### P1.3 "Not available" in Verdict Strengths/Opportunities/Risks
- Strengths column has data but also "Not available" in some rows
- Negative evidence for Strengths should be "—" not "Not available"
- Template should use "—" for intentionally empty cells

**Fix location**: `backend/earnings_deep_dive/prompts.py` + `mapper.py`.

### P1.4 "N/A" for Press Release/Earning Call Presentation
- Acceptable if truly not available, but should say "Not found on investor.apple.com" not bare "N/A"
- Could auto-search for these documents on the IR page

---

## P2 — MINOR (formatting)

### P2.1 Revenue guidance = "0.1276" instead of "12.76%"
- `_to_pct_num()` should format as percentage, not raw decimal

**Fix location**: `backend/earnings_deep_dive/mapper.py` — `_to_pct_num()`.

### P2.2 EPS data inconsistency
- Line 34: EPS Actual = $2.10
- Line 62: EPS = $2.01
- Two different values for the same metric in the same PDF

**Root cause**: EPS from different sources (yfinance vs supplied metrics vs transcript) not reconciled.

---

## FIX ORDER

| Priority | Issue | File | Lines |
|----------|-------|------|-------|
| P0.1 | Markdown artifacts | `pdf_renderer.py` | Section rendering |
| P0.1 | ? numbering | `prompts.py` | Highlights template |
| P0.2 | Severity "Not available" | `prompts.py` | Highlights prompt |
| P1.1 | Revenue estimate | `sources_collector.py` | Yahoo extraction |
| P1.2 | Forward EPS basis | `mapper.py` | `_compute_forward_pe` |
| P1.3 | Verdict gaps | `mapper.py` | Verdict rows |
| P2.1 | Decimal → % | `mapper.py` | `_to_pct_num()` |
| P2.2 | EPS inconsistency | `mapper.py` | EPS reconciliation |
