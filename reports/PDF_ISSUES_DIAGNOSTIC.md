# PDF Report Issues — Diagnostic for Codex Session
# Date: 2026-05-06
# Report: analyses/2026-05-06_MSFT_Microsoft_Corp/07_final_report/

## ISSUE 1: Prompt text leaks into final report [CRITICAL]
**File:** `backend/earnings_deep_dive/prompts.py` (system_prompt + _base_prompt)
**Root cause:** The system prompt instructs the LLM to include the question text in output:
  - `"start each section with the question..."` (line ~370 in system_prompt)
  - `"- Immediately after the heading, print the question line(s) exactly as shown above."` (in _base_prompt section output contract)
**Result:** The final markdown shows raw prompt text:
  - "How were operating income, operating margin, gross profit, gross margin, operating expenses, and net income? Please provide a summary..."
  - "How were ROE, ROTCE (ROTE), ROA, and ROIC?"
**Fix:** Remove "print the question" from the section output contract. The question is for the LLM's context only, NOT for output.

## ISSUE 2: Q3 2026 hallucination [CRITICAL]
**File:** Orchestrator (need to find where quarter is computed)
**Root cause:** The `{quarter}` parameter is computed as "FY2026 Q3" which hasn't happened yet. 
The latest 10-K is for FY2025 (ending June 2025). The orchestrator is projecting forward incorrectly.
**Fix:** Tie quarter to the actual latest filing date. If latest is 10-K FY2025, quarter should be "FY2025 Q4" or "FY2025 Annual". Never project into the future.

## ISSUE 3: Nami-style emoji/icon markers degraded [MEDIUM]
**File:** The system prompt has the emojis defined correctly (📊🌟⚠️🧠🎯🧩💰📈📦🏆), and the output DOES contain some (🌟⚠️).
But the user reports they "disappeared" in the PDF. 
**Possible cause:** PDF renderer (`pdf_renderer.py`) may be stripping emojis or not rendering them in the PDF version.
**Fix:** Check pdf_renderer.py for emoji support. Ensure the reportlab PDF generation preserves Unicode emoji characters or uses inline images for them.

## ISSUE 4: No link to official company website [MEDIUM]
**File:** `backend/earnings_deep_dive/prompts.py` system_prompt + `markdown.py`
**Root cause:** The system prompt doesn't instruct the LLM to include the company website. The markdown assembler doesn't add it either.
**Fix:** Add to the report header/template: `**Official Website:** https://www.microsoft.com` (fetched from company profile data, which already has this field in finnhub/yahoo data)

## ISSUE 5: Missing sections — Forward P/E and Backlog Quality [MEDIUM]
**File:** The generated report shows: "Section unavailable. Not disclosed. Reason: Bilingual output detected"
**Root cause:** The bilingual detection validator rejected the LLM output for these sections. The LLM may have output Japanese text despite being prompted for English-only. OR the "Bilingual output detected" error is a false positive.
**Check:** `backend/earnings_deep_dive/deep_dive_validator.py` or `validators.py` — find the bilingual detection logic and see if it's too aggressive.

## ISSUE 6: Template alignment with original Nami spec [LOW-MEDIUM]
**Reference:** The original Nami template expects specific formatting with ①②③ markers, "For Nami-san:" lines, "> One-line summary:" endings, and a company info header with website.
**Current state:** Some markers are present but the report.md is only 1944 chars (very short) while the deep_dive is 19531 chars. The report.md (main analysis) is separate from earnings_deep_dive.md. The PDF combines both?
**Check:** `backend/earnings_deep_dive/generator.py` and `pdf_renderer.py` — trace the full PDF assembly pipeline to ensure both report.md and earnings_deep_dive.md are combined correctly.

## FILES TO AUDIT (in order):
1. `backend/earnings_deep_dive/prompts.py` — system_prompt(), _base_prompt() — ISSUE 1, 2
2. `backend/earnings_deep_dive/generator.py` — quarter computation — ISSUE 2
3. `backend/earnings_deep_dive/pdf_renderer.py` — PDF emoji rendering — ISSUE 3
4. `backend/earnings_deep_dive/markdown.py` — assemble_final_report() — ISSUE 4
5. `backend/earnings_deep_dive/validators.py` — bilingual detection — ISSUE 5
6. `backend/pipeline.py` — main analysis flow, quarter param — ISSUE 2

## FILES DO NOT TOUCH:
- `backend/main.py` (API routes, working)
- Frontend files (working)
- `backend/orchestrator.py` (timeout fix applied, working)
