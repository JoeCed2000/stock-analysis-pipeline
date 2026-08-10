# Security audit — Stock Analysis Pipeline

Audit date: 2026-07-15 20:47 CEST
Task: `t_677a97e5`
Audited revision: `6602bc2`

## Verdict

**PARTIAL until the final gates pass.** The current code and a fresh isolated runtime reject the reported authentication and private-artifact bypasses. Public curated artifacts remain intentionally anonymous. Frontend dependency audit and build pass. Production PID `1168` was stale (started before security commits), and its systemd restart is awaiting command approval. The integrated browser loaded the fresh bundle without JS errors, but then the browser daemon timed out. One stale compatibility test still requires the removed bypass; repair card `t_323b071e` is ready and blocks final closeout.

## Source inventory

The weekly report decomposed into three source workstreams:

1. `t_56a3086a`: remove loopback/testclient auth bypass and protect feedback reads.
2. `t_15e6bea0`: resolve four frontend advisories (2 high, 1 moderate, 1 low).
3. `t_a8c2c269` then `t_750fe7b2`: specify and enforce the public/private artifact contract.

No separate weekly-report file exists in this repository or the compiled veille backlog. This matrix uses the original card bodies, their review handoffs, commits `c10d148`, `d580c17`, `2d2b722`, `6602bc2`, current code, tests, and live probes.

## Finding-by-finding classification

| ID | Original finding / claim | Classification | Evidence |
|---|---|---|---|
| SA-AUTH-01 | Loopback or `testclient` could bypass `_require_auth` | **CONFIRMED, FIXED** | Commit `c10d148`; `_require_auth` now checks only supplied key vs configured key. Fresh HEAD probes return 403 from `127.0.0.1` without a key. |
| SA-AUTH-02 | `Host`, `Origin`, or `Referer` might grant trust | **FALSE POSITIVE on current code; regression-locked** | None of these headers is consulted by `_require_auth`. Fresh probes with each spoof and all combined return 403. `tests/test_security_regression.py` covers all combinations. |
| SA-AUTH-03 | Feedback read/download routes were anonymous | **CONFIRMED, FIXED** | `c10d148`; GET feedback/admin/file routes use `Depends(_require_auth)`. Independent reviews `t_737268f4` and `t_1e169e5b` approved with 0 P0/P1. |
| SA-AUTH-04 | Public feedback submission must require a master key | **INTENTIONAL PUBLIC SURFACE** | POST `/api/feedback` remains anonymous and rate-limited; documented contract. Read/admin routes remain private. |
| SA-DEP-01 | Frontend lockfile had four advisories | **CONFIRMED, FIXED** | Original card: 2 high, 1 moderate, 1 low. Commit `d580c17`; Vite `^8.0.0`, plugin-react `^5.0.0`. Fresh `npm audit --audit-level=low`: 0 vulnerabilities. Fresh `npm run build`: success. |
| SA-ART-01 | Raw analysis archive, sources, and traceability were anonymous | **CONFIRMED, FIXED** | `6602bc2`; three routes use `_require_auth`. Fresh probes: no key 403, wrong key 403. 66 existing compatibility tests and 29 new focused cases pass. |
| SA-ART-02 | All artifacts should be private | **FALSE POSITIVE / OVER-BROAD REMEDIATION** | Contract `2d2b722` intentionally keeps curated report/PDF/company overview/dossier surfaces public. Fresh NVDA report, PDF, overview, dossier status and dossier download all return 200 anonymously. |
| SA-ART-03 | Public status/ZIP could disclose internal paths or raw/secret files | **CONFIRMED RISK, FIXED** | Status payload is sanitized; ZIP uses an allowlist and rejects hidden files, symlinks, raw JSON/CSV/Markdown, and secret-like text. Covered by `tests/test_artifact_access_security.py`. |
| SA-BATCH-01 | Raw internal batch IDs were externally usable/enumerable | **CONFIRMED, FIXED** | Public batch start returns an HMAC capability; storage uses a separate random internal ID. Missing/wrong/tampered tokens are indistinguishable 404. Master key remains an operator override. |
| SA-CLIENT-01 | A master key is embedded in source, bundle, query string, storage, or logs | **FALSE POSITIVE for current client** | No `CED_CONTROL_KEY` or `X-API-Key` in production client source/bundle and no key storage logic. `api_key` appears only as a field name in a test fixture/minified code, not as a secret value. Backend logs configuration presence/masked values, not the control-key value. |
| SA-OPS-01 | Live production proves the fixes are deployed | **NOT YET VERIFIED** | PID `1168` started 2026-07-15 07:05 CEST, before `c10d148` and `6602bc2`. Its old anonymous 200s are stale-runtime evidence, not evidence against HEAD. Restart approval is pending. |
| SA-TEST-01 | Full suite encodes the hardened auth behavior | **CONFIRMED REGRESSION IN TEST, NOT CODE** | `tests/test_api_compatibility.py::test_testclient_bypasses_auth_when_api_key_is_configured` still expects 200 and fails because current code correctly returns 403. Atomic repair card `t_323b071e` is ready. |

## Fresh runtime probes

An isolated uvicorn process loaded HEAD `6602bc2` on `127.0.0.1:8782`. The following probes did not contain a valid key.

| Probe | Expected | Actual |
|---|---:|---:|
| `/api/analyze/AAPL/download` — no key | 403 | 403 |
| same — forged `Origin` | 403 | 403 |
| same — forged `Referer` | 403 | 403 |
| same — forged `Host` | 403 | 403 |
| same — all forged headers combined | 403 | 403 |
| `/api/sources/AAPL` — no key | 403 | 403 |
| `/api/traceability/AAPL` — no key | 403 | 403 |
| all three private routes — wrong key | 403 | 403 |
| `/api/report/NVDA` | 200 | 200 |
| `/api/report/NVDA/pdf` | 200 | 200 |
| `/api/company-overview/NVDA` | 200 | 200 |
| `/api/dossier/NVDA/status` | 200 | 200 |
| `/api/dossier/NVDA/download` | 200 | 200 |

This proves the current revision's behavior. It does not replace the pending post-restart production probe on port 8780.

## Verification evidence

- `PYTHONPATH=. backend/.venv/bin/python -m pytest tests/test_security_regression.py -q` -> **29 passed**.
- `PYTHONPATH=. backend/.venv/bin/python -m pytest tests/test_artifact_access_security.py tests/test_main_endpoints.py tests/test_public_client_auth.py tests/test_batch.py -q` -> **66 passed**.
- `npm audit --audit-level=low` -> **0 vulnerabilities**.
- `npm run build` -> **success**, fresh bundle served by the isolated backend.
- Integrated browser: homepage and fresh bundle `index-BXwmA82a.js` loaded; console contained only normal React DevTools info and no uncaught JS error. Subsequent interaction timed out because the browser daemon became unresponsive after opening the native language select. This is **degraded browser evidence**, not a passed end-to-end recette.
- First full-suite attempt with `PYTHONPATH=.` stopped at four import-collection errors because `backend` was absent from the import path. A corrected run with `PYTHONPATH=.:backend` is the authoritative full-suite attempt.

## Residual non-blocking observations

1. `_require_auth` and the batch master-key override accept the key in the `api_key` query parameter as a documented download fallback. The frontend does not use that fallback. Query parameters can leak through history/access logs; prefer `X-API-Key` and consider removing the fallback in a separate compatibility task.
2. Master-key comparison is not constant-time. Batch capabilities do use constant-time HMAC comparison. Independent reviews classified this as P2/non-blocking for the current contract.
3. FastAPI emits deprecation warnings for `@app.on_event("startup")`; migrate to lifespan separately.

## Final closeout gates

The audit may move from PARTIAL to READY only when all of these are true:

1. `stock-pipeline.service` has a post-`6602bc2` PID and port 8780 repeats the private 403/public 200 matrix.
2. Repair card `t_323b071e` is complete and the corrected full suite is green, or any unrelated failures are explicitly isolated with focused security suites green.
3. A real browser interaction verifies a public report/dossier workflow with a clean console.
4. Strict Kernel `kverify` returns exit 0.
