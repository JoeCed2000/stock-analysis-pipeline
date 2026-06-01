# Kanban package prepared — DO NOT LAUNCH NOW

Board target later: `sa-pipeline`
Title: `SA PDF PRO-QA — Correct Deep Dive + Company Overview data integrity, JP generation, and professional layout`

## SA-PDF-AUDIT-FIX-01 — Fix JP deep-dive generation/polling reliability
**project:** stock-analysis-pipeline `/home/ced/codex-projects/stock-analysis-pipeline`
**write_scope:** backend/main.py, backend/earnings_deep_dive/generator.py, async dossier/job-store code only if root cause proves there.
**expected_tests:** targeted pytest for JP PDF endpoint; live local curl poll for NVDA/AAPL/GOOGL `?lang=jp` until 200 or terminal error.
**acceptance_criteria:** NVDA/AAPL/GOOGL JP deep-dive PDFs return HTTP 200 within bounded polling; no infinite 202; failures are terminal and explicit.
**risk:** do not restart prod while Nami may test; implement later in maintenance window.

## SA-PDF-AUDIT-FIX-02 — Reconcile Company Overview key_financials with source ledger/Yahoo snapshot
**project:** stock-analysis-pipeline
**write_scope:** backend/company_overview.py, backend/company_overview_pdf.py, backend/pipeline.py, tests for source ledger coherence.
**expected_tests:** unit tests comparing company_overview key_financials to local yahoo_snapshot/source ledger for NVDA/AAPL/GOOGL; PDF text extraction checks.
**acceptance_criteria:** market cap/revenue/margins/FCF/P/E/52W range in Company Overview agree with canonical source ledger within explicit tolerance; missing values only allowed with coded reason.
**risk:** avoid fabricated numbers; if provider missing, show reason and source path.

## SA-PDF-AUDIT-FIX-03 — Replace stale/legacy Company Overview fallback path
**project:** stock-analysis-pipeline
**write_scope:** backend/main.py download_company_overview, artifact generation path, tests.
**expected_tests:** endpoint tests for ticker with legacy `company_profile_*.pdf` and missing current profile; browser download check.
**acceptance_criteria:** endpoint never silently serves 1-page legacy profile as if current investor profile; it either generates/serves current artifact or returns explicit actionable status.
**risk:** backwards compatibility for older artifacts; preserve intentional access but label clearly.

## SA-PDF-AUDIT-FIX-04 — Professional PDF layout pass for Deep Dive + Company Overview
**project:** stock-analysis-pipeline
**write_scope:** backend/earnings_deep_dive/pdf_renderer.py, backend/company_overview_pdf.py, visual regression assets/tests.
**expected_tests:** render first pages to PNG; visual smoke test for title hierarchy, page density, table overflow, no clipped text; text extraction placeholder scan.
**acceptance_criteria:** first-page executive summary looks client-ready/premium; tables fit; sources appendix readable; no raw markdown/internal markers.
**risk:** visual changes can regress pagination; validate with 3 tickers and EN+JP.

## SA-PDF-AUDIT-FIX-05 — Add automated PDF QA gate EN+JP
**project:** stock-analysis-pipeline
**write_scope:** tests/tools for PDF audit, CI/local test docs; no runtime feature scope unless needed.
**expected_tests:** audit script checks EN+JP existence, page counts, placeholders, internal markers, key numeric coherence, source URLs, rendered page smoke.
**acceptance_criteria:** one command produces pass/fail report for 3-ticker recipe before declaring PDF work done.
**risk:** avoid false positives on intentional Nami personalization; configure allowed audience modes.
