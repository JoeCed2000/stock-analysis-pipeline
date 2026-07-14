# Public Artifact Access Contract

Status: **approved architecture contract**
Project: `stock-analysis-pipeline`
Task: `t_a8c2c269`
Date: 11/07/2026

## 1. Decision

The static production frontend must remain usable without embedding `CED_CONTROL_KEY` or any other master secret. This does **not** make every file under `analyses/` public.

The access boundary is:

1. **Public curated outputs** — intentionally publishable investor-facing artifacts already exposed by the static UI.
2. **Private/internal artifacts** — raw dossiers, source manifests, traceability data, and broad ZIP exports.
3. **Capability-scoped batch outputs** — downloadable without a master key only when the caller presents the unguessable, time-bounded capability returned by the batch submission.

Authorization is enforced server-side. `Origin`, `Referer`, loopback source IP, host name, and browser headers are never authorization signals.

## 2. Endpoint classification

| Endpoint | Classification | Required access | Rationale / compatibility |
|---|---|---|---|
| `GET|HEAD /api/report/{ticker}` | Public curated | No master key; existing public rate limit | The React `ReportView` calls `getReport(ticker)` directly. The returned final markdown is an intentionally rendered client output, not raw source material. |
| `GET|HEAD /api/report/{ticker}/pdf` | Public curated | No master key; existing public rate limit | Primary user-facing Deep Dive PDF. Existing browser links and polling must keep working. Only verified/current client-ready output may be served. |
| `GET /api/company-overview/{ticker}/download` | Public curated | No master key; existing public rate limit | `AnalysisCard` opens this URL directly in a new tab. The endpoint already applies client-readiness/quality checks. |
| `GET /api/dossier/{ticker}/download` | Public curated ZIP | No master key; existing public rate limit | Existing `AnalysisCard` downloads this deterministic URL. It is public **only because the route constructs a filtered deliverable**: verified dossier only, selected language only, PDF/XLSX/README plus transcript verbatim text, excluding JSON/CSV/Markdown and internal files. Do not replace this filter with whole-directory export. |
| `GET /api/dossier/{ticker}/status` | Public workflow metadata | No master key; existing public rate limit | Required by frontend polling. Response must not disclose absolute paths, validation file paths, secrets, or internal directory names to unauthenticated callers. |
| `GET /api/analyze/{ticker}/download` | Private legacy ZIP | Valid `X-API-Key` through `_require_auth` | Broad recursive export of readable files from the latest analysis; not used by the current frontend. Deterministic ticker URLs permit enumeration and can expose non-curated material. |
| `GET /api/sources/{ticker}` | Private provenance | Valid `X-API-Key` through `_require_auth` | Returns `sources_manifest.json`, which may reveal source URLs, collection details, local provenance, and internal data layout. No active frontend consumer was found. |
| `GET /api/traceability/{ticker}` | Private provenance | Valid `X-API-Key` through `_require_auth` | Returns the claim-level traceability matrix. This is audit evidence, not a public presentation artifact. No active frontend consumer was found. |
| `GET /api/batch/{job_id}/download` | Capability-scoped ZIP | Valid, scoped, unexpired batch capability encoded in or bound to `job_id`; master API key may remain an operator override | The route recursively ZIPs the complete analysis directories for every ticker in the batch, including raw JSON/CSV and internal artifacts. It must not be public by possession of an enumerable/stable database identifier. |
| `GET /api/batch/{job_id}/status` | Capability-scoped workflow metadata | Same batch capability as download | Status and download belong to one access scope. A caller unable to access the batch must receive the same generic not-found response for both routes. |

`GET /api/analyses` remains private and must not be used as a public artifact index. Public artifact availability is discovered only from the analysis workflow/result already visible to that user.

## 3. Public does not mean unrestricted filesystem access

Public curated routes must satisfy all of the following:

- Resolve artifacts from server-owned canonical directories only.
- Normalize and validate ticker/language/quarter inputs before lookup.
- Never accept a caller-supplied path or filename.
- Never return absolute filesystem paths in success or error payloads.
- Refuse symlinks or resolved paths escaping `ANALYSES_DIR`.
- Serve only the explicit allow-listed artifact type for that route.
- Preserve the latest-artifact and PDF quality gates; never fall back silently to an older artifact when the latest output is blocked or incomplete.
- Use generic `404` for absent/non-publishable artifacts so existence of private files is not disclosed.
- Apply rate limits to public status and download routes.
- Set `Content-Disposition` and `Content-Type` explicitly; add `X-Content-Type-Options: nosniff` to downloadable responses.
- Do not cache private/capability responses publicly. Recommended: `Cache-Control: private, no-store` for capability/private downloads and `Cache-Control: public, max-age=<bounded>` only for immutable curated outputs if a later cache policy explicitly approves it.

The curated dossier ZIP is a special case: its public status depends on the current allow-list in `dossier_download()`. Any future addition of raw source files, HAR/cookie material, logs, `.env`, validation internals, JSON, CSV, or unrestricted recursive export automatically requires reclassification to private/capability-scoped.

## 4. Batch capability contract

### 4.1 Selected design

Use a **signed, time-bounded capability carried by the existing `job_id` value**. This preserves the current frontend URL shape:

- submit: `POST /api/batch/analyze`
- response: `{ "job_id": "<opaque capability>", ... }`
- poll: `GET /api/batch/<opaque capability>/status`
- download: `GET /api/batch/<opaque capability>/download`

No frontend master key and no new browser credential store are required. `frontend/src/api.js` can continue treating `job_id` as an opaque string.

### 4.2 Capability properties

The capability must:

- use a cryptographically secure random identifier with at least 128 bits of entropy;
- be authenticated with HMAC-SHA-256 (or an established equivalent), using a server-only environment secret distinct from `CED_CONTROL_KEY`;
- bind purpose (`batch-status-download`), internal batch identifier, issue time, and expiry;
- have a bounded lifetime; recommended default **24 hours**, configurable by environment;
- use constant-time signature comparison;
- be URL-safe and never logged in full (log only a short irreversible fingerprint);
- fail closed when the signing secret is absent in production;
- return generic `404 Job not found` for malformed, forged, expired, or unknown capabilities;
- authorize only the bound batch; a token for batch A cannot access batch B;
- remain valid for status and one or more download retries until expiry. “Single use” is deliberately **not** required because browsers retry downloads and users may need to re-download during the bounded window.

The persisted batch filename/key must use the internal random batch identifier, not the full signed capability. Capability verification occurs before `_load_batch_job()` so an attacker cannot probe persistence by timing or error differences.

A valid `X-API-Key` may remain an operator override for recovery/administration, but the public browser path must never receive or depend on that key.

### 4.3 Expiry response

Malformed, expired, forged, wrong-purpose, or wrong-batch capabilities all produce the same external response:

```text
404 {"detail":"Job not found"}
```

Do not distinguish “expired”, “bad signature”, or “batch exists” to unauthenticated callers. Internal security logs may record the reason without recording the token.

## 5. Private endpoint contract

Private endpoints use the single production `_require_auth` dependency:

- Header: `X-API-Key`.
- Missing or incorrect key: `403 {"detail":"Invalid API key"}`.
- Correct key: route proceeds.
- Loopback, `testclient`, `Host`, `Origin`, `Referer`, and `ngrok-skip-browser-warning` do not bypass the key.
- HEAD and GET variants have identical authorization.
- Error responses do not reveal whether a ticker/job/artifact exists before authorization succeeds.

Apply `_require_auth` to:

- `GET /api/analyze/{ticker}/download`
- `GET /api/sources/{ticker}`
- `GET /api/traceability/{ticker}`

Batch status/download use the capability verifier described above rather than exposing the master key to the browser.

## 6. Frontend compatibility matrix

| Frontend consumer | Current behavior | Contract impact |
|---|---|---|
| `ReportView.jsx` → `getReport()` | Fetches `/api/report/{ticker}` without secret | No change. Route stays public curated. |
| `AnalysisCard.jsx` → `getTickerDownloadUrl()` | Fetches `/api/dossier/{ticker}/download?...` without secret | No change. Route stays public curated with strict ZIP allow-list. |
| `AnalysisCard.jsx` → `getCompanyOverviewDownloadUrl()` | Opens direct URL without secret | No change. Route stays public curated. |
| `useDossierPolling` / `getDossierStatus()` | Polls public status without secret | No auth change; sanitize unauthenticated status fields. |
| `BatchAnalysis.jsx` | Stores returned `job_id`, polls status, links to download | No URL/API-key change if `job_id` becomes the opaque signed capability. Treat it as opaque; do not parse it. |
| `getSources()` | API helper exists, but no active JSX consumer found | Route becomes private. If a future public UI needs citations, add a separate curated citations DTO; do not expose the raw manifest. |
| Traceability | No active frontend consumer found | Route becomes private. Future public traceability requires a separately reviewed redacted export. |

## 7. Migration plan

### Phase 1 — Establish the hard auth boundary

1. Remove every loopback/testclient/host/origin bypass from `_require_auth`.
2. Add `_require_auth` to the three private artifact routes.
3. Keep public curated routes unchanged from the browser perspective.
4. Add negative tests before deployment.

Deployment rule: do not deploy private-route decorators before the public curated matrix is covered by tests, otherwise the production static UI can be broken accidentally.

### Phase 2 — Batch capability

1. Split internal batch ID from external capability.
2. Mint the capability in `POST /api/batch/analyze` and return it as `job_id`.
3. Verify capability before both status and download lookups.
4. Persist only under internal ID.
5. Configure a dedicated signing secret and 24-hour TTL.
6. Preserve master-key operator override.
7. Add cleanup for expired batch files as a separate operational task; expiry must deny access even before cleanup runs.

Backward compatibility: capabilities minted before deployment do not exist. Existing legacy jobs may be accessible only with the master API key during a short documented migration window; do not accept unsigned legacy job IDs from unauthenticated clients.

### Phase 3 — Response hardening

1. Sanitize public dossier status and PDF error responses to remove absolute directories and internal validation paths.
2. Add `nosniff` and explicit cache policy to artifact responses.
3. Add safe security-event logging for denied private access and invalid batch capabilities.
4. Rate-limit repeated capability failures without logging raw tokens.

## 8. Required security tests

Create `tests/test_artifact_access_security.py` with remote-client tests. Use fake artifact bytes and temporary directories only; never use real analyses, cookies, tokens, or production keys.

### Public curated routes

- Unauthenticated remote client can fetch a verified final report markdown.
- Unauthenticated remote client can fetch a verified Deep Dive PDF.
- Unauthenticated remote client can fetch a client-ready Company Overview.
- Unauthenticated remote client can fetch the filtered dossier ZIP.
- Dossier ZIP excludes `.json`, `.csv`, `.md`, logs, hidden files, and a synthetic secret-like file.
- Public responses expose no absolute path.
- HEAD and GET behavior match for public report routes.

### Private routes

Parameterize over ticker ZIP, sources manifest, and traceability matrix:

- remote request without key returns `403` before artifact lookup;
- remote request with wrong key returns `403`;
- loopback request without key also returns `403`;
- spoofed `Origin`, `Referer`, `Host`, and ngrok headers do not bypass auth;
- correct `X-API-Key` reaches the route;
- missing and existing artifact names are indistinguishable to an unauthenticated caller.

### Batch capability

- Submit returns an opaque capability and no master key.
- Valid capability can poll only its bound job.
- Valid capability can download only its bound batch ZIP.
- Forged signature returns generic `404`.
- One-character token mutation returns generic `404`.
- Expired capability returns generic `404`.
- Wrong-purpose capability returns generic `404`.
- Capability for batch A cannot access batch B.
- Unsigned legacy internal job ID is denied without master key.
- Valid master key can perform the documented operator override.
- Logs do not contain the full capability.

### Regression bundle

At minimum:

```bash
PYTHONPATH=. backend/.venv/bin/python -m pytest \
  tests/test_artifact_access_security.py \
  tests/test_public_client_auth.py \
  tests/test_main_endpoints.py \
  tests/test_batch.py \
  tests/test_async_dossier.py \
  tests/test_dossier_language_zip.py \
  tests/test_seeking_alpha_access.py -q
```

Frontend compatibility gate:

```bash
cd frontend
node src/components/AnalysisCard.dossier.test.cjs
npm run build
```

If the named component test is absent, use the existing dossier/API source tests plus a focused static contract test that asserts batch `job_id` remains opaque and direct public URLs do not require an API key.

## 9. Acceptance checklist

- [ ] Endpoint classification above is implemented exactly.
- [ ] No master key is present in frontend source, bundle, query strings, local storage, or logs.
- [ ] Public user flows still work from a remote unauthenticated browser.
- [ ] Private artifact routes deny loopback and remote unauthenticated requests equally.
- [ ] Batch access is scoped, signed, time-bounded, and non-enumerable.
- [ ] Public status/error payloads disclose no absolute filesystem paths.
- [ ] Curated ZIP allow-list has regression coverage.
- [ ] Negative auth/IDOR tests pass.
- [ ] Backend regression bundle and frontend build pass.
- [ ] Persistent Ced Agent Kernel proof is READY.
- [ ] Independent security review approves the diff before deployment.

## 10. OWASP / ASVS mapping

- **V4 Access Control / OWASP A01**: deny by default for non-curated artifacts; server-side enforcement; object-bound batch capability.
- **IDOR/BOLA prevention**: deterministic ticker routes are public only for explicitly curated outputs; private deterministic routes require auth; batch token is bound to one internal object.
- **V2 Authentication**: master key never crosses into static frontend code.
- **V7 Error Handling and Logging**: generic external failures; no token/path disclosure; security events logged safely.
- **V12 Files and Resources**: canonical root containment, explicit extension/content allow-list, no caller paths.
- **V14 Configuration**: dedicated capability secret, fail-closed production configuration, bounded TTL.

## 11. Explicit non-goals

- This contract does not make `analyses/` a static file root.
- It does not authorize public browsing/listing of historical analyses.
- It does not expose raw source manifests or traceability by creating a frontend secret.
- It does not use CORS, `Origin`, `Referer`, IP address, or obscurity as authorization.
- It does not introduce user accounts or OAuth solely for these existing static-client flows.
