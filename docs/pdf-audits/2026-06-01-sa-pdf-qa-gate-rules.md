# SA PDF QA Gate Rules — EN/JP Deep Dive + Company Overview

Status: implementation-ready rule specification
Task: `t_4dd1230d`
Source audit: `docs/pdf-audits/2026-06-01-sa-pdf-pro-qa-raw.json`
Rendered smoke inputs: PNG files listed in `files_rendered` and each artifact `rendered_pages`
Audience modes: `generic` (default), `nami_personalized`, `internal_debug`

## 1. Purpose

This gate is the automated pre-delivery check for client-facing PDF artifacts. It must run before declaring any PDF work ready for Nami or any generic client audience.

The gate emits three outcome classes:

| Outcome | Meaning | Blocks delivery? |
|---|---|---|
| `defect` | Client-facing output is missing, broken, internally contaminated, or materially incoherent | yes |
| `warning` | Output is usable but lower quality, incomplete, or needs review | no |
| `allowed` | Normally forbidden condition is explicitly permitted by the selected audience mode | no |

No rule may silently pass on missing input. Missing audit fields must be reported as `defect` unless the rule below explicitly says `warning`.

## 2. Expected audit input shape

The gate consumes the JSON shape already produced by `2026-06-01-sa-pdf-pro-qa-raw.json`:

```text
{
  "tickers": {
    "NVDA": {
      "analysis_dir": ".../analyses/<run>_NVDA_...",
      "artifacts": {
        "deep_en": {
          "exists": true,
          "is_pdf": true,
          "pages": 27,
          "size": 426594,
          "links": 9,
          "errors": [],
          "lang": {"jp_chars": 0, "latin_chars": 59665, "jp_ratio": 0.0},
          "forbidden_counts": {"NaN": 45, "source: yfinance": 9, "Nami-san": 12},
          "placeholder_counts": {"Not available": 2, "No data": 2, "not disclosed": 14},
          "sections_present": {"Financial Metrics": true, "Valuation": true, ...},
          "page_char_min": 1296,
          "page_char_median": 2856,
          "page_char_max": 4635,
          "snippets": ["..."],
          "rendered_pages": ["/tmp/..._p1.png", "/tmp/..._p2.png"]
        },
        "deep_jp": {...},
        "company": {...}
      },
      "raw_files": {
        "company_json": ".../company_overview_<TICKER>.json",
        "yahoo_snapshot": ".../yahoo_snapshot_<TICKER>.json",
        "validation_en": ".../deep_dive_validation.json",
        "validation_jp": ".../jp/.../deep_dive_validation.json"
      },
      "raw_compare": {
        "market_cap": {"company_overview": 4583336181760, "yahoo_snapshot": 4583336595549.074, "delta_pct": -0.000009},
        "pe_forward": {"company_overview": 32.47, "yahoo_snapshot": 30.40, "delta_pct": 6.80}
      }
    }
  },
  "files_rendered": ["/tmp/sa_pdf_audit_output/NVDA_deep_en_p1.png", ...]
}
```

Implementation must preserve enough details per finding to debug quickly:

```text
finding = {
  rule_id,
  severity: defect|warning|allowed,
  ticker,
  artifact: deep_en|deep_jp|company,
  message,
  observed,
  expected,
  evidence_path?,
  audience_mode
}
```

## 3. Artifact matrix

| Artifact key | Required in generic mode | Language expectation | Default page range | Source URL expectation |
|---|---:|---|---:|---|
| `deep_en` | yes | English, `jp_ratio <= 0.05` | 10–40 pages | >= 5 HTTP(S) URLs |
| `deep_jp` | yes | Japanese, `jp_ratio >= 0.30` | 10–45 pages | >= 5 HTTP(S) URLs |
| `company` | yes | English unless future JP company mode is explicit | 3–12 pages | >= 1 HTTP(S) URL or explicit source registry |

If a future run intentionally skips one artifact, the audit input must carry an explicit skip declaration outside `artifacts`, for example:

```text
"expected_artifacts": {"deep_jp": {"required": false, "reason": "..."}}
```

Without that explicit skip declaration, absence is a `defect`.

## 4. Severity matrix by audience mode

| Condition | generic | nami_personalized | internal_debug |
|---|---|---|---|
| `Nami`, `Nami-san`, `Namiさん`, `Nami様` in PDF prose | `defect` | `allowed` only in configured personalized blocks | `warning` |
| Internal pipeline/source labels in prose (`source: yfinance`, `LLM synthesis`, validation messages) | `defect` | `defect` | `allowed` only when debug artifact flag is true |
| Missing or non-PDF artifact | `defect` | `defect` | `defect` |
| `NaN`, `null`, `undefined`, `DATA NOT AVAILABLE` visible in text | `defect` | `defect` | `warning` only for debug artifacts |
| Benign em dash `—` as typography | `allowed` | `allowed` | `allowed` |
| Em dash `—` as missing-data placeholder in table value cells | `warning` by default; `defect` for key metrics | `warning` by default; `defect` for key metrics | `warning` |

Important: `nami_personalized` is not a blanket waiver. It allows Nami personalization only when the implementation passes `audience_mode=nami_personalized` and the artifact metadata or run configuration confirms the PDF was generated for Nami. Generic PDF generation must still block any accidental personalization leakage.

## 5. Rule definitions

The rules below cover artifact existence, page count sanity, text extraction, marker detection, placeholder detection, numeric coherence, source URLs, section presence, and rendered-page smoke.

### PDFQA-001 — Ticker envelope exists

Inputs: `tickers` dictionary.

Logic:
- For each requested ticker, there must be a corresponding `tickers[<ticker>]` object.
- `analysis_dir` must be a non-empty absolute path.

Severity:
- Missing ticker object: `defect`.
- Missing or relative `analysis_dir`: `defect`.

### PDFQA-002 — Required artifact key exists

Inputs: `artifacts`, artifact matrix, optional explicit skip declaration.

Logic:
- For each required artifact key in the matrix, `artifacts[key]` must exist.
- If skipped, the skip must be explicit and include a non-empty reason.

Severity:
- Missing required artifact without skip: `defect`.
- Explicit skip with reason: `warning` unless the delivery checklist requires that artifact, then `defect`.

### PDFQA-003 — Artifact exists and is a real PDF

Inputs: artifact fields `exists`, `is_pdf`, `size`, `errors`.

Logic:
- `exists` must be true.
- `is_pdf` must be true.
- `size` must be >= 10_000 bytes for `deep_*`; >= 8_000 bytes for `company`.
- `errors` must be empty.

Severity:
- Any false `exists` or `is_pdf`: `defect`.
- Size below threshold: `defect`.
- Non-empty `errors`: `defect`, include the first error string.

Example from current audit: NVDA/GOOGL `deep_jp` have `exists=true` but `is_pdf=false`, `pages=0`, and `FileDataError`; this is a `defect`, not a warning.

### PDFQA-004 — Page count sanity

Inputs: artifact `pages`.

Logic:
- `deep_en`: 10 <= pages <= 40.
- `deep_jp`: 10 <= pages <= 45.
- `company`: 3 <= pages <= 12.
- `pages == 0` is always invalid for required PDFs.

Severity:
- Outside range: `defect`.
- Within 1 page of min/max: `warning` for review, but do not block.

### PDFQA-005 — Text extraction non-empty

Inputs: `page_char_min`, `page_char_median`, `page_char_max`, `snippets`.

Logic:
- `page_char_median` must be >= 500 for `deep_*` and >= 300 for `company`.
- `page_char_max` must be > 0.
- `snippets` must be non-empty for valid PDFs.
- For `deep_*`, no page should have fewer than 250 extracted characters unless it is a cover/table-of-contents page and the audit marks it as such.

Severity:
- Zero text or empty snippets: `defect`.
- Median below threshold: `defect`.
- One or more very sparse pages with otherwise valid median: `warning`.

### PDFQA-006 — Language ratio sanity

Inputs: `lang.jp_ratio`, artifact key.

Logic:
- `deep_en` and `company` default English: `jp_ratio <= 0.05`.
- `deep_jp`: `jp_ratio >= 0.30`.
- Future bilingual mode must declare a `language_mode=bilingual` override and must require `0.10 <= jp_ratio <= 0.70`.

Severity:
- Wrong language ratio: `defect`.
- Borderline ratio within 0.05 of threshold: `warning`.

### PDFQA-007 — Forbidden/internal markers

Inputs: `forbidden_counts` plus full extracted text when available.

Hard-fail markers in client PDFs:
- `DATA NOT AVAILABLE`
- `N/A` when used as a standalone table value or sentence placeholder
- `null`
- `undefined`
- `NaN`
- `LLM synthesis`
- `source: yfinance`
- `raw_`, `_raw`, `validation`, `pre_render_validator`, `pytest`, `traceback`
- `FileDataError`, `Exception(`, `HTTPException`, `NoneType`

Logic:
- Counts are case-sensitive for exact raw tokens (`NaN`, `N/A`) and case-insensitive for prose phrases.
- `NaN` is always a `defect` in generic and Nami modes.
- Internal provider strings such as `source: yfinance` must not appear in final prose. Client-safe source labels are allowed, e.g. `Yahoo Finance`, `SEC filing`, `Seeking Alpha transcript`.

Severity:
- Any hard-fail marker count > 0: `defect` except where `internal_debug` explicitly allows it.
- Provider-safe labels are `allowed`.

### PDFQA-008 — Placeholder and missing-data wording

Inputs: `placeholder_counts`, full extracted text.

Blocked placeholders:
- `DATA NOT AVAILABLE`
- `No data` as a final user-facing value
- `Not available` for required key metrics
- `unavailable` when used without explanation
- `not disclosed` when the source actually has a value
- repeated em dash placeholders in value cells

Allowed missing-data wording:
- `Not retrieved` for a source that truly was not retrieved.
- `Not disclosed by the company` when the source registry confirms the issuer did not disclose the value.
- `Not meaningful` for negative earnings or mathematically invalid valuation ratios.

Thresholds:
- `deep_*`: more than 5 placeholder occurrences is a `warning`; any occurrence in the executive snapshot, verdict, or key financial tables is a `defect`.
- `company`: more than 3 placeholder occurrences is a `warning`; any occurrence in CEO, segments, competitors, market cap, revenue, FCF, PE, or beta is a `defect`.

Severity:
- Blocked placeholder in key area: `defect`.
- Excessive non-key placeholders: `warning`.
- Allowed wording with documented reason: `allowed`.

### PDFQA-009 — Personalization leakage gate

Inputs: `audience_mode`, artifact metadata if available, `forbidden_counts`, full extracted text.

Personalization tokens:
- `Nami`
- `Nami-san`
- `Namiさん`
- `Nami様`
- Japanese direct-client phrasing that identifies Nami specifically.

Logic:
- In `generic` mode, any personalization token is a `defect`.
- In `nami_personalized` mode, personalization is `allowed` only if:
  1. the run configuration explicitly selected `nami_personalized`, and
  2. the artifact is intended for Nami delivery, and
  3. the personalization appears in client-safe advice/prose, not in source citations, filenames, or metadata dumps.
- In `internal_debug` mode, personalization is a `warning` unless the debug artifact is intentionally user-specific.

Severity:
- Accidental leakage in generic mode: `defect`.
- Correct personalized delivery: `allowed`.
- Personalized token in source/metadata/debug dumps: `defect` even in Nami mode.

### PDFQA-010 — Required section presence

Inputs: `sections_present`.

Deep Dive required sections:
- `Financial Metrics`
- `Valuation`
- `Operating Metrics`
- `Cash Flow`
- `Capital Efficiency`
- `Investment Thesis` or equivalent thesis/verdict section
- `Risks` or equivalent risk section
- `Sources` or source appendix

Company Overview required sections:
- `Executive Snapshot`
- `Company Overview`
- `How the Company Makes Money`
- `Business Segments`
- `Growth Drivers`
- `Competitive Advantages`
- `Risks` or `Business Risks`
- `Competitors` or peer/competitive context
- `Investor Takeaway`

Logic:
- Missing a required section is a defect if the section is part of the current product contract.
- Missing a newly proposed but not yet contracted section is a warning until the implementation version turns it on.

Severity:
- Contracted required section missing: `defect`.
- Optional/enrichment section missing: `warning`.

### PDFQA-011 — Source URL presence and validity

Inputs: artifact `links`, extracted URLs if available, raw source files.

Logic:
- `deep_*` must expose at least 5 HTTP(S) URLs in the PDF text or annotations.
- `company` must expose at least 1 HTTP(S) URL or reference an explicit source registry in the audit input.
- URLs must start with `https://` unless the source is a local evidence file in the audit report.
- URLs must not be placeholders (`example.com`, `localhost`, `127.0.0.1`, empty string).
- For transcript sources, prefer stable listing URLs when detail URLs are known to rot.

Severity:
- Missing required URLs: `defect` for `deep_*`; `defect` for `company` unless an explicit source registry is present, otherwise `warning` for a transition period.
- Insecure or placeholder URLs: `defect`.
- URL count below threshold but sources are available in sidecar JSON: `warning`, plus implementation should copy them into PDF.

### PDFQA-012 — Key numeric coherence

Inputs: `raw_compare`, optional source ledgers (`company_json`, `yahoo_snapshot`, validation files).

Metrics checked by default:
- `market_cap`
- `revenue`
- `gross_margin`
- `operating_margin`
- `free_cash_flow`
- `pe_ratio`
- `pe_forward`
- `beta`

Logic:
- If both `company_overview` and `yahoo_snapshot` are numeric, compute absolute percentage delta.
- Thresholds:
  - `market_cap`, `revenue`, `free_cash_flow`: warn at > 5%, defect at > 10%.
  - `gross_margin`, `operating_margin`: warn at > 2 percentage points, defect at > 5 percentage points.
  - `pe_ratio`, `pe_forward`: warn at > 10%, defect at > 20%.
  - `beta`: warn at > 10%, defect at > 20%.
- If one side is null and the value is a key company overview field, emit a warning requiring provenance review; do not fabricate a value.
- If the company overview uses `key_financials` from Spark and Yahoo has no field, require source provenance in `company_json` before allowing delivery.

Severity:
- Delta above defect threshold: `defect`.
- Delta above warning threshold: `warning`.
- Missing comparison source for a key metric: `warning`; `defect` if the PDF displays a precise number without provenance.

Example from current audit: NVDA `market_cap` delta -39.38% and `pe_forward` delta +109.82% are `defect` findings.

### PDFQA-013 — First-page render smoke

Inputs: `rendered_pages`, `files_rendered`, PNG file metadata.

Logic:
- Each valid PDF artifact must have at least page 1 rendered to PNG.
- Page 1 PNG must exist, be readable, have width >= 300 px and height >= 400 px.
- PNG file size must be >= 10 KB.
- The image must not be blank: at least 2% of pixels should differ from the dominant background color, or the luminance standard deviation must be >= 5.
- The rendered page should not be visually tiny: effective page area should be >= 120_000 pixels.

Severity:
- Missing/unreadable page 1 render: `defect`.
- Blank/near-blank page 1: `defect`.
- Very small or suspiciously low-detail render: `warning`.

### PDFQA-014 — Rendered page coverage

Inputs: `rendered_pages`.

Logic:
- Required minimum rendered pages per artifact:
  - 3 pages for `deep_*` when pages >= 3.
  - min(3, pages) pages for `company`.
- Rendered page list must include page 1.

Severity:
- No rendered pages for a valid artifact: `defect`.
- Fewer than minimum but page 1 exists and passes smoke: `warning`.

### PDFQA-015 — Raw file sidecar presence

Inputs: `raw_files`.

Logic:
- `company_json` and `yahoo_snapshot` are required for numeric coherence checks.
- `validation_en` is required when `deep_en` is required.
- `validation_jp` is required when `deep_jp` is required.
- Paths must be non-empty absolute paths. If the implementation runs outside the same host, it may accept a structured sidecar object instead of a filesystem path.

Severity:
- Missing sidecar required for an enabled artifact: `defect`.
- Path present but file absent: `warning` if the raw JSON already contains equivalent data; otherwise `defect`.

### PDFQA-016 — Stale/legacy artifact guard

Inputs: artifact path if available, analysis_dir, filename patterns, PDF size/pages.

Logic:
- PDF path must live under the selected `analysis_dir` unless explicitly marked as shared static fixture.
- Legacy filename patterns such as `company_profile_<TICKER>.pdf` are not acceptable as fresh company overview output unless the current pipeline explicitly generated them in the same run.
- A 1-page company profile under 10 KB is a stale/legacy suspect.

Severity:
- Served artifact outside selected analysis directory without explicit override: `defect`.
- Legacy/suspicious filename or 1-page tiny profile: `defect`.

### PDFQA-017 — Null audit-field robustness

Inputs: all artifact fields.

Logic:
- Any missing core field (`exists`, `is_pdf`, `pages`, `size`, `links`, `errors`, `lang`, `sections_present`) must produce a finding.
- Implementation must not treat missing fields as zero success.

Severity:
- Missing core field: `defect`.
- Missing optional enrichment field (`snippets`, `rendered_pages`) when the artifact itself is invalid: attach as context only, do not duplicate findings.

## 6. Default pass/fail policy

A ticker passes only when all required artifacts pass with zero `defect` findings.

A run passes only when every requested ticker passes.

Warnings are included in the report and should be reviewed before client delivery, but they do not block unless the caller sets `strict_warnings=true`.

Allowed findings must be explicit. The report must include why the condition was allowed and which audience/debug mode enabled it.

## 7. Minimal CLI acceptance contract for implementation

The future implementation should provide one command similar to:

```bash
python -m tools.pdf_qa_gate \
  --audit-json docs/pdf-audits/2026-06-01-sa-pdf-pro-qa-raw.json \
  --audience-mode generic \
  --render-smoke \
  --out docs/pdf-audits/<timestamp>-pdf-qa-gate-report.json
```

Expected exit codes:

| Exit code | Meaning |
|---:|---|
| 0 | No defects; warnings may exist |
| 1 | One or more defects |
| 2 | Invalid audit input or gate configuration |

Expected report summary:

```text
{
  "passed": false,
  "audience_mode": "generic",
  "tickers_checked": 3,
  "artifact_count": 9,
  "defect_count": 12,
  "warning_count": 8,
  "allowed_count": 0,
  "findings": [...]
}
```

## 8. Current audit examples the gate must catch

From `2026-06-01-sa-pdf-pro-qa-raw.json`, a conforming implementation should at least flag:

- NVDA `deep_jp`: `PDFQA-003` and `PDFQA-004` defects (`is_pdf=false`, `pages=0`, `FileDataError`).
- GOOGL `deep_jp`: same JP PDF defects.
- NVDA `deep_en` and GOOGL `deep_en` in generic mode: `PDFQA-009` personalization leakage due to `Nami-san` tokens.
- All PDFs with `NaN` counts: `PDFQA-007` defects.
- Deep Dive PDFs with `source: yfinance`: `PDFQA-007` defects; final prose must use client-safe source labels.
- Company PDFs with `links=0`: `PDFQA-011` defect unless an explicit source registry is supplied.
- NVDA numeric deltas for market cap and forward PE: `PDFQA-012` defects.
- AAPL `deep_jp`: control example for a valid JP artifact (`is_pdf=true`, pages=27, `jp_ratio=0.55`, rendered pages present); the implementation must not over-block this case except for independent marker/placeholder findings.
- Any valid artifact missing rendered page 1: `PDFQA-013` defect.

## 9. Non-goals

- The gate must not rewrite PDF content.
- The gate must not invent missing financial values.
- The gate must not perform live network fetches by default; URL reachability checks can be a separate optional `--live-url-check` mode to keep local QA deterministic.
- The gate must not consider `curl 200` sufficient for client readiness; browser/PDF render smoke remains required for client-facing delivery.
