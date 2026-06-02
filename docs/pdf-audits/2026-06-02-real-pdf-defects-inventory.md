# Inventaire réel des défauts PDF SA — Company Overview + Earnings Deep Dive

Date: 2026-06-02
Scope: vrais artefacts PDF/audits sauvegardés, sans hypothèse et sans patch code.
Repo: `/home/ced/codex-projects/stock-analysis-pipeline`

## Evidence gates lus

### WIKI_EVIDENCE
- `WIKI.md` lu: derniers commits/documentation confirment le flux Company Overview `key_financials` + provenance, PDFQA gate foundation, admin recovery, prod commit `65c2bcf`.
- `docs/spec-fonctionnelle.md` lu: PDFs deep-dive et ZIP sont livrables principaux; PDF deep-dive doit contenir les sections majeures et être téléchargeable/ouvrable navigateur.
- `docs/spec-technique.md` lu: backend FastAPI + ReportLab; routes `/api/report/{ticker}/pdf`, `/api/earnings/deep-dive`, `/api/health`; tests pytest/Playwright; déploiement WSL + Cloudflare.
- Handoff lu: `/home/ced/.hermes/handoffs/ns-sa-pdf-defects-20260602-1135.md`.

### Prod/current-state evidence
- `tb status` → pre-flight `GO`.
- `tb sa-check` → `ALL OK`; backend local/prod OK; backend PID `1636704`, started 11:17, prod commit `65c2bcf`.
- Local admin API recent rows still show FAIL `Analysis timed out after 1200s` at `2026-06-02T07:45–07:46Z`.
- Commit `65c2bcf` time is `2026-06-02T11:31:31+02:00` = `09:31Z`; those FAIL rows are **historical pre-commit**, not evidence of a new post-65c2bcf false-fail.

### PDF/audit evidence sources
- Human QA report: `docs/pdf-audits/verification-t_0da449db-20260601T165622Z/qa_report.md`.
- Audit summary JSON: `docs/pdf-audits/verification-t_0da449db-20260601T165622Z/verification_summary.json`.
- Raw PDFs: `docs/pdf-audits/verification-t_0da449db-20260601T165622Z/raw/`.
- Extracted text corpus: `docs/pdf-audits/verification-t_0da449db-20260601T165622Z/text/`.
- PDFQA rules: `docs/pdf-audits/2026-06-01-sa-pdf-qa-gate-rules.md`.
- PDFQA gate map: `docs/pdf-audits/2026-06-02-pdf-quality-gates-map.md`.

## Coverage réelle auditée

- Tickers: `AAPL`, `GOOGL`, `MSFT`, `NVDA`, `TSLA`.
- Company Overview: 5/5 PDFs présents.
- Deep Dive EN: 3/5 PDFs présents (`AAPL`, `GOOGL`, `TSLA`), 2/5 endpoints sauvegardés comme `202 generating` (`NVDA`, `MSFT`).
- Deep Dive JP: 3/5 PDFs présents (`NVDA`, `AAPL`, `GOOGL`), 2/5 endpoints sauvegardés comme `202 generating` (`MSFT`, `TSLA`).
- First-page PNG proofs: 11.

## Inventaire par famille de défauts

### F1 — Deep Dive non-PDF / génération asynchrone bloquée

Client-visible: oui, téléchargement/recette impossible.

Evidence:
- `NVDA deep_en`: HTTP `202`, `is_pdf=false`, pages `0`.
- `MSFT deep_en`: HTTP `202`, `is_pdf=false`, pages `0`.
- `MSFT deep_jp`: HTTP `202`, `is_pdf=false`, pages `0`.
- `TSLA deep_jp`: HTTP `202`, `is_pdf=false`, pages `0`.

Root-cause candidate:
- endpoint/génération deep-dive peut retourner JSON `202 generating` au lieu d'un PDF final; à distinguer de la correction récente sur faux timeout batch.
- Probable famille: idempotency/polling/generation-state, pas renderer pur.

Priority: **P0**.

### F2 — Deep Dive fuite de labels internes/provider dans le PDF final

Client-visible: oui, le PDF montre des strings techniques.

Evidence extraite directement des PDFs:
- `source: yfinance`:
  - `AAPL deep_en`: 52 occurrences.
  - `AAPL deep_jp`: 32 occurrences.
  - `GOOGL deep_en`: 52 occurrences.
  - `GOOGL deep_jp`: 17 occurrences.
  - `NVDA deep_jp`: 11 occurrences.
  - `TSLA deep_en`: 8 occurrences.
- `S1`:
  - `AAPL deep_en`: 6.
  - `AAPL deep_jp`: 6.
  - `GOOGL deep_en`: 6.
  - `GOOGL deep_jp`: 6.
  - `NVDA deep_jp`: 6.
- Example snippets:
  - `... (source: yfinance eps_actual; yfinance eps_estimate; formula: ...)`.
  - `... S1 Alphabet (GOOGL) Competes in digital ecosystem layers ...`.

Root-cause candidate:
- LLM prompt/mapper sends raw source tags and competitor row IDs into final prose/table cells.
- Post-render PDFQA detects this, but runtime/pre-render sanitization or mapper normalization must remove/translate it before PDF.

Priority: **P0/P1**.

### F3 — Deep Dive personalization leakage in generic PDFs

Client-visible: yes if generic PDF, acceptable only if `nami_personalized` mode was explicit.

Evidence:
- `AAPL deep_en`: `Nami-san` 34 occurrences.
- `GOOGL deep_en`: `Nami-san` 28 occurrences.
- `TSLA deep_en`: `Nami-san` 21 occurrences.
- Prior raw audit also flagged `NVDA deep_en` and `GOOGL deep_en` generic leakage.

Root-cause candidate:
- audience/persona prompt defaults to Nami instead of generic mode, or audit artifacts were generated in Nami mode without metadata marking them as personalized.
- Needs explicit `audience_mode` propagation; generic PDF must not contain Nami tokens.

Priority: **P1** unless these exact PDFs are confirmed Nami-personalized; then becomes metadata/gate issue.

### F4 — Deep Dive placeholder/no-data wording excessive or misleading

Client-visible: yes.

Evidence:
- `Not disclosed` totals in direct PDF extraction:
  - `NVDA deep_jp`: 29.
  - `AAPL deep_jp`: 27.
  - `GOOGL deep_jp`: 27.
  - `AAPL deep_en`: 15.
  - `GOOGL deep_en`: 9.
  - `TSLA deep_en`: 5.
- `Not available`/`unavailable` visible in `TSLA deep_en` and others.
- Example: `Operating Metrics` tables show columns with `Not disclosed` for revenue/gross profit/operating profit rows even when values are present or source should be a named filing.

Root-cause candidate:
- source-label field defaults to placeholder (`Not disclosed`) even when the numeric value is present.
- Missing-data semantics are not separated from source-label semantics.

Priority: **P1**.

### F5 — Company Overview incomplete/stale/tiny artifacts

Client-visible: yes.

Evidence:
- `TSLA_company.pdf`: only 1 page, 661 extracted chars, fails company expected page range (3–12 pages). Looks like a thin metric sheet, not a professional company overview.
- `MSFT_company.pdf`: 4 pages, but prior audit identified legacy/stale company profile risk (`company_profile_MSFT.pdf`, 1-page 2.3KB fallback in older probe).
- Company PDFs have no extracted source links in the audit summary (`links=0` for all company rows).

Root-cause candidate:
- Company Overview endpoint can serve legacy/minimal fallback when generated overview JSON/prose is absent or stale.
- Need stale-artifact guard + generation completeness check before serving.

Priority: **P0 for TSLA / P1 generalized**.

### F6 — Company Overview source traceability missing

Client-visible: yes for auditability.

Evidence:
- Audit summary: all company PDFs have `links=0`.
- Spec requires auditability and source traceability; PDFQA-011 expects at least 1 URL or explicit source registry.
- Company pages show metadata labels but no source appendix/traceability section in extracted text.

Root-cause candidate:
- `company_overview_pdf.py` renderer does not surface source registry/provenance into final PDF, even after backend provenance work.

Priority: **P1**.

### F7 — Company Overview numeric coherence risk (partially addressed by latest commits)

Client-visible: yes if stale PDFs are served.

Evidence from saved audit before latest fixes:
- `NVDA company`: market cap `$3.10T` vs Yahoo `$5.11T`, delta `-39.4%`.
- `NVDA company`: forward PE `35.0` vs Yahoo `16.681`, delta `+109.8%`.
- `NVDA company`: beta `1.7` vs Yahoo `2.244`, delta `-24.2%`.

Current caveat:
- WIKI shows commit `095c899` + later `65c2bcf` implemented canonical `key_financials` resolver/provenance after this saved audit.
- This family must be re-checked on fresh generated PDFs before patching again.

Priority: **P0 to verify fresh**, patch only if still present.

### F8 — Visual/professional polish below client standard

Client-visible: yes.

Evidence:
- Company Overview first pages are dense text/card grids with low visual hierarchy; TSLA is a single-page metric dump.
- Deep Dive first page has dense tables and inconsistent spacing; visual proof indicates low polish for a client-facing investment PDF.

Root-cause candidate:
- ReportLab templates emphasize raw tables/text over designed hierarchy; renderer lacks charts/visual summary blocks/source appendix polish.

Priority: **P2** after correctness/source/marker defects.

## Priorité proposée

1. **P0 — Artifact validity/generation**: Deep Dive `202 generating` instead of PDF; Company Overview 1-page/tiny legacy fallback.
2. **P0 — Numeric coherence fresh verification**: regenerate/check at least NVDA + AAPL/GOOGL after key_financials resolver; patch only if mismatch persists.
3. **P1 — Internal/provider marker removal**: `source: yfinance`, `S1`, raw keys, `Not disclosed` source labels.
4. **P1 — Company source/provenance surfaced in PDF**: Company Overview must show source registry/provenance or URLs.
5. **P1 — Audience/personalization gate**: `Nami-san` allowed only with explicit `nami_personalized` metadata.
6. **P2 — Visual polish/layout**: charts, hierarchy, table wrapping, first-page professional design.

## Next patch target recommendation

Start with **F1/F5 artifact validity**, because it blocks the user's ability to even download/open the PDFs and catches stale/legacy fallbacks. Before editing symbols:

- CodeGraph: inspect `download_earnings_pdf` / report PDF route and Company Overview download route, plus generation state helpers.
- Serena: symbol overview for `backend/main.py`, `backend/company_overview_pdf.py`, `backend/company_overview.py`, and relevant `earnings_deep_dive` modules.
- Tests to add/update:
  - Deep Dive endpoint must not silently return `202` forever for completed/failed states; if generating, response must be explicit and admin status must not record false terminal success/fail.
  - Company Overview serving must reject tiny/legacy profile PDFs and trigger/fail cleanly instead of serving incomplete client PDF.
  - PDFQA gate should include stale/tiny Company Overview fixture and non-PDF Deep Dive artifact fixture.

## Non-patch conclusion at this stage

No source code has been changed in this inventory pass. The next step is structural impact mapping (CodeGraph + Serena) for the P0 artifact-validity family, then one narrow fix class at a time.
