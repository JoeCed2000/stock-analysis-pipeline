# PDF Model Alignment Diagnosis And Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** align the generated earnings deep-dive PDF with `docs/specs/modele.pdf` so the output uses the same official template structure, language variant, sourcing discipline, figures, visual hierarchy, and pagination behavior.

**Architecture:** keep the current dedicated earnings deep-dive renderer, but make it model-driven from an extracted template contract instead of an approximate section renderer. The pipeline must fail validation and block download when sourced data, transcript URL, required numbers, or visual/template invariants are missing.

**Tech Stack:** Python 3.12 in WSL venv, FastAPI backend, ReportLab PDF renderer, PyMuPDF/Pillow for PDF inspection and visual validation, pytest for regression tests, React/Vite frontend for download gating.

---

## 1. Current Diagnosis

### PDFs compared

| Role | Path | Bytes | Pages | Page size | Extracted chars |
|---|---:|---:|---:|---|---:|
| Model/reference | `docs/specs/modele.pdf` | 421287 | 14 | 612 x 792 pt Letter | 10069 |
| Latest generated deep-dive | `docs/specs/earnings_deep_dive.pdf` | 190505 | 10 | 612 x 792 pt Letter | 22208 |
| Old generated report | `docs/specs/genere.pdf` | 5257 | 2 | A4 | already obsolete for alignment |

The generated deep-dive has improved versus the old `genere.pdf`: it now uses Letter and has the earnings structure. It is still not aligned with the model because its content flow is much denser, page count differs by 4 pages, and the rendered document does not reproduce the model's block-level rhythm.

### Root causes

1. **Template contract is still approximate**
   - `backend/earnings_deep_dive/template.py` captures section order and table shapes, but not enough physical layout information from the model: question blocks, source instruction blocks, spacing, page break intent, bilingual prompt/example structure, and section-specific density.
   - The model must be treated as a block template, not just a list of 10 section names.

2. **Generated content is too verbose**
   - The generated deep-dive has more than twice the extracted text of the model while using fewer pages.
   - This means the renderer packs too much text per page and allows section analysis to dominate the visual output.

3. **Tables are not calibrated to the model**
   - Tables exist, but their widths, row heights, font sizes, borders, and spacing do not yet match the reference.
   - Codex-generated Markdown tables can now be preserved, but they still need normalization into fixed model table specs.

4. **Data validation is stricter but not complete**
   - The pipeline can block placeholders in the PDF render model.
   - It still needs a model-specific required-number matrix for every section, with explicit allowed exceptions for metrics that truly do not exist for a ticker.

5. **Transcript discovery depends on configured providers**
   - The code now supports RapidAPI, Alpha Vantage, Motley Fool, legacy public search, and Google Custom Search.
   - In the current environment the required API/search keys are absent, so a real ticker smoke cannot prove full numeric completeness.

6. **Visual validation is generated but not yet blocking**
   - `reports/pdf-visual-diff/` contains rendered PNGs and diffs.
   - There is no automated pass/fail threshold for page count, page geometry, font families, text density, or key block positions.

7. **Download gating is correct but downstream compliance still fails**
   - The frontend/backend now block download unless `download_enabled=true`.
   - The real alignment work must make the validator pass, not loosen the gate.

## 2. Implementation Plan

### Task 1: Extract A Model Block Contract

**Files:**
- Create: `scripts/extract_pdf_template_contract.py`
- Create: `docs/pdf-template-contract.md`
- Create: `reports/pdf-template-contract/model-contract.json`

- [ ] **Step 1: Write a script that extracts model blocks**

Create `scripts/extract_pdf_template_contract.py` with a PyMuPDF pass that records, per page: page size, text blocks, bounding boxes, font names, sizes, colors, and normalized text.

- [ ] **Step 2: Run the extractor**

Run:

```powershell
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && .venv/bin/python scripts/extract_pdf_template_contract.py"
```

Expected:

- `reports/pdf-template-contract/model-contract.json` exists.
- It reports 14 pages and Letter page size.
- It lists recurring font/color/spacing patterns.

- [ ] **Step 3: Document the block contract**

Create `docs/pdf-template-contract.md` with:

- page count target: 14 pages for the reference fixture;
- per-section page span;
- expected block order;
- table column count per section;
- question block style;
- source/instruction block style;
- summary block style;
- allowed visual tolerances.

### Task 2: Add Alignment Tests Before Renderer Changes

**Files:**
- Modify: `tests/test_earnings_pdf_renderer.py`
- Create: `tests/test_pdf_model_alignment.py`

- [ ] **Step 1: Add page-count and text-density tests**

Add tests for deterministic fixture output:

```python
def test_generated_fixture_matches_model_page_shape(tmp_path):
    pdf_path = build_fixture_pdf(tmp_path)
    doc = fitz.open(pdf_path)
    assert len(doc) == 14
    assert round(doc[0].rect.width) == 612
    assert round(doc[0].rect.height) == 792
```

- [ ] **Step 2: Add forbidden-example and forbidden-placeholder tests**

Assert:

- no `GEV`, `GE Vernova`, `SanDisk`, or model example-only values remain for non-example tickers;
- no `DONNÉE NON DISPONIBLE`, `DATA NOT AVAILABLE`, `Not disclosed`, or `Section unavailable` remains in a validated final PDF.

- [ ] **Step 3: Add required-section text tests**

Assert extracted text contains every model section title in order:

- EPS & Revenue;
- Highlights & Lowlights;
- Operating Metrics;
- Cash Flow;
- Capital Efficiency;
- Segments;
- Forward P/E;
- Backlog;
- Guidance;
- Verdict / Overall Assessment.

### Task 3: Convert Template From Section List To Block Template

**Files:**
- Modify: `backend/earnings_deep_dive/template.py`
- Modify: `backend/earnings_deep_dive/report_model.py`
- Modify: `tests/test_earnings_pdf_template.py`

- [ ] **Step 1: Add block-level template objects**

Introduce render block types:

- `question`;
- `source_instruction`;
- `section_heading`;
- `table`;
- `analysis`;
- `summary`;
- `page_break`.

- [ ] **Step 2: Map the model into block order**

For each section, define exact block sequence and whether a page break follows. This is where the 14-page layout becomes deterministic.

- [ ] **Step 3: Keep language variants separate**

Maintain `en` and `jp` templates with shared business keys, but separate display text. Do not rely on post-PDF translation for the primary deep-dive PDF.

### Task 4: Normalize Codex Output Into Bounded Content

**Files:**
- Modify: `backend/earnings_deep_dive/generator.py`
- Modify: `backend/earnings_deep_dive/mapper.py`
- Modify: `backend/earnings_deep_dive/deep_dive_validator.py`
- Modify: `tests/test_earnings_deep_dive.py`

- [ ] **Step 1: Add per-block character budgets**

The model has lower text density than the generated PDF. Add section-specific budgets for analysis paragraphs and summaries.

- [ ] **Step 2: Reject overlong sections before PDF rendering**

If Codex returns text exceeding a block budget, retry once with a strict shortening instruction. If still too long, fail validation rather than silently packing the PDF.

- [ ] **Step 3: Preserve sourced numeric tables**

Codex may format explanatory tables, but required numeric tables must come from structured metrics or sourced transcript extraction. Tables without sources fail validation.

### Task 5: Build Required Metrics Matrix

**Files:**
- Create: `backend/earnings_deep_dive/required_metrics.py`
- Modify: `backend/earnings_deep_dive/deep_dive_validator.py`
- Create: `tests/test_earnings_required_metrics.py`

- [ ] **Step 1: Define required metrics per section**

Create a matrix with metric key, source priority, required/conditional status, and display format.

- [ ] **Step 2: Add validation for missing required metrics**

Validated PDFs must fail if required metrics are missing and no documented exception exists.

- [ ] **Step 3: Add source metadata checks**

Each required figure must carry a source label or URL. The final report must not pass validation from unsourced numeric values.

### Task 6: Improve Transcript And Source Readiness

**Files:**
- Modify: `backend/transcript_finder.py`
- Modify: `backend/transcript_web_search.py`
- Modify: `backend/pipeline.py`
- Modify: `tests/test_transcript_finder.py`

- [ ] **Step 1: Start transcript discovery immediately after ticker validation**

Ensure `/api/analyze` and batch analysis start all source searches as part of analysis, not at download time.

- [ ] **Step 2: Keep multi-ticker parallelism**

Use the existing `run_analysis_parallel` path for multiple tickers. Do not serialize transcript discovery across tickers.

- [ ] **Step 3: Make missing provider configuration explicit**

If Google CSE/RapidAPI/Alpha Vantage are not configured, write a validation issue explaining which providers were skipped.

### Task 7: Rework PDF Renderer Around The Block Contract

**Files:**
- Modify: `backend/earnings_deep_dive/pdf_renderer.py`
- Modify: `tests/test_earnings_pdf_renderer.py`
- Modify: `scripts/pdf_audit_extract.py`

- [ ] **Step 1: Implement fixed block styles**

Styles must match the model:

- Letter page;
- Arial or resolved local Arial equivalent;
- MS-PGothic for Japanese if available;
- red question text;
- black body text;
- green positive numeric values;
- compact table fonts;
- consistent row heights and borders.

- [ ] **Step 2: Implement model page breaks**

Do not let ReportLab auto-flow everything. Use template block page-break hints to target 14 pages for the fixture.

- [ ] **Step 3: Add table normalization**

Every table gets fixed column widths, repeatable headers, non-empty cells, and consistent row padding.

### Task 8: Make Visual Diff Blocking For Fixture

**Files:**
- Modify: `scripts/pdf_audit_extract.py`
- Create: `tests/test_pdf_visual_regression.py`

- [ ] **Step 1: Render model and fixture at 150 DPI**

Use PyMuPDF to render both PDFs page-by-page.

- [ ] **Step 2: Add structural thresholds**

Block regressions on:

- page count mismatch for fixture;
- page size mismatch;
- missing page images;
- text block count far outside reference range;
- first-page question/table vertical positions outside tolerance.

Pixel-perfect diff is not the first gate because generated data differs by ticker.

### Task 9: Validate End-To-End Smoke With A Real Ticker

**Files:**
- Modify: `docs/pdf-generation-final-report.md`
- Output: `reports/pipeline-smoke/<date>_<ticker>_*/07_final_report/earnings_deep_dive.pdf`

- [ ] **Step 1: Run one real ticker**

Run:

```powershell
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && .venv/bin/python -c 'from backend.pipeline import analyze_ticker; r=analyze_ticker(\"MSFT\", output_base=\"reports/pipeline-smoke\"); print(r.report_path)'"
```

- [ ] **Step 2: Extract and validate text**

Assert:

- ticker/company appear;
- no model examples remain;
- no placeholders remain after validation;
- source URL appears;
- all expected section titles appear.

- [ ] **Step 3: Confirm download remains blocked if validation fails**

If sourcing is incomplete, `download_enabled` must stay false.

## 3. Acceptance Criteria

- Generated fixture PDF has 14 Letter pages like the model.
- Real validated PDF has all model sections, titles, tables, phrases, sourced figures, and no placeholders.
- PDF text remains extractable; the PDF is not converted into a page image.
- English and Japanese outputs use distinct templates.
- Download button and endpoint only unlock after successful generation and validation.
- Visual audit artifacts are generated and attached under `reports/pdf-visual-diff/`.
- Backend tests and compile checks pass.

## 4. Current Blockers Before Implementation

- Real transcript sourcing cannot be fully validated until at least one configured provider is available: Google CSE, RapidAPI, Alpha Vantage, or equivalent approved source.
- The frontend build currently depends on a complete `node_modules`; if Rollup optional dependencies are missing, Vite validation requires a local dependency reinstall.
- The current generated deep-dive is Letter, but still 10 pages instead of 14 and too text-dense.

## 5. Execution Rule

Do not start implementation until this plan is approved or replaced by the next prompt. The next coding pass should start with tests, then renderer/template changes, then smoke validation.
