# Stock Analysis Pipeline — WIKI

## Architecture
- **Backend**: Python 3.11+ FastAPI (port 8780), yfinance + finnhub-python
- **Frontend**: React + Vite (port 5173 dev, bundled to dist/)
- **Deploy**: Cloudflare Tunnel → sa.cedlabusa.net
- **Tests**: pytest 153/153 (backend), node 68/68 (frontend chartUtils)

## Key Endpoints
| Endpoint | Method | Description |
|---|---|---|
| `/api/analyze` | POST | Synchronous ticker analysis (90s timeout) |
| `/api/analyze/async` | POST | Async ticker analysis (job-based) |
| `/api/valorization/{ticker}` | GET | Market metadata (status, source, currency) |
| `/api/valuation-context/{ticker}` | GET | V2.4: 7 context signals (PEG, P/S vs Growth, EV/EBITDA vs Growth, P/FCF vs Growth, FCF Yield, Valuation Support, Context Summary) |
| `/api/peer-benchmark/{ticker}` | GET | V2.5: Peer-relative benchmarks with neutral labels, summary (valuation/growth/quality/confidence) |
| `/api/metrics-history/{ticker}` | GET | Quarterly fundamentals for valuation multiples |

## Key Components
| Component | File | Purpose |
|---|---|---|
| ValuationGroup | `frontend/src/components/ValuationGroup.jsx` | 8-metric grid + V2.4 context summary card + enriched tooltips |
| AnalysisCard | `frontend/src/components/AnalysisCard.jsx` | Full analysis card with ValuationGroup + PeerBenchmarkGroup |
| PeerBenchmarkGroup | `frontend/src/components/PeerBenchmark/PeerBenchmarkGroup.jsx` | V2.5 Group 9: Summary card + Relative Valuation table + Quality vs Peers table |
| chartUtils | `frontend/src/components/chartUtils.js` | Valuation computation, formatting |
| api.js | `frontend/src/api.js` | All API calls including fetchValuationContext, fetchPeerBenchmark |
| i18n.js | `frontend/src/i18n.js` | EN+JP translations including peer benchmark section |

## Recent Changes
| Date | Task | Description |
|---|---|---|
| 2026-05-28 | Front feedback restore + SA availability badge | Restored the user-facing feedback UX that disappeared after commit `bf6f4fd`: re-added `FeedbackPage.jsx`, restored `#feedback` hash routing, and restored the `💬 Feedback` header button in `App.jsx`. Added a visible homepage status badge (`SA: available/unavailable/checking`) backed by `GET /api/admin/seeking-alpha/access` so users can immediately see Seeking Alpha availability without opening admin. Verification: `frontend/npm run build` (64 modules, `dist/assets/index-C1wPPSto.js`), production browser checks on `https://sa.cedlabusa.net/stock-analysis/?ts=20260528-1413` (feedback button + SA badge visible), `#feedback` page loads with history/status counters, `#admin` still shows `Configured · 12 cookies`, and browser console has 0 JS errors. | ✅ DONE |
| 2026-05-28 | Seeking Alpha access hardening + live restart | Hardened the server-side Seeking Alpha cookie store: new `backend/seeking_alpha_access.py` now enforces parent dir perms (`0700` best-effort), atomic writes, file perms (`0600` best-effort), and `.state/` is ignored by git. Added security assertions in `tests/test_seeking_alpha_access.py` (no `cookie_header` echoed back, POSIX mode check when available). Verification: `PYTHONPATH=/home/ced/codex-projects/stock-analysis-pipeline .venv/bin/pytest tests/test_seeking_alpha_access.py tests/test_feedback.py` → `21 passed`; backend restarted on PID `311265` at `2026-05-28 13:11:37`; production admin page `https://sa.cedlabusa.net/stock-analysis/#admin` renders with 0 JS errors; live `GET /api/admin/seeking-alpha/access` returns `configured=false`, `server_side_only=true`; live `POST /api/admin/seeking-alpha/test` returns HTTP 200 with `reason=no_cookies_configured` (endpoint reachable, no cookies loaded yet). | ✅ DONE |
| 2026-05-28 | GOOG historical feedback backfill + attachment proof | Backfilled 2 historical GOOG feedback entries from the provided WhatsApp text into the canonical feedback store: `2026-05-28_043100` (P1/P5/P7/P9 message) and `2026-05-28_052100` (Company Overview request), each with a copied GOOG deep-dive PDF attachment. Verification: production admin feedback API now returns both GOOG rows with timestamps `04:31` and `05:21`; attachments `2026-05-28_043100_deep_dive_GOOG.pdf` and `2026-05-28_052100_deep_dive_GOOG.pdf` download via `GET /api/feedback-file/GOOG/{filename}` with HTTP 200, `Content-Type: application/pdf`, `Content-Length: 372344`. The admin search table also shows the unique Mac user-agent GOOG consultation at `28/05, 04:04:58`. | ✅ DONE |
| 2026-05-28 | Front feedback removal | Removed the user-facing feedback entry point from the main frontend: deleted the `💬 Feedback` button, removed `#feedback` routing from `App.jsx`, and deleted the unused `FeedbackPage.jsx` component. Admin feedback/backend endpoints remain untouched. Verification: `frontend/npm run build` OK, Playwright `tests_e2e/test_sa_recette.py -k test_p0_home_loads` passed, production browser check on `https://sa.cedlabusa.net/stock-analysis/` shows no feedback button, and `#feedback` now lands on the 404 page with 0 JS errors. | ✅ DONE |
| 2026-05-28 | Multiprofile feedback auto-intake | Added shared Hermes script `/home/ced/.hermes/shared/scripts/sa_feedback_auto_intake.py` plus 3 staggered cron jobs (codex-first/default/deepseek-first) that scan canonical `SA_ANALYSES_DIR/feedback_*`, create ready Kanban tasks on board `sa-pipeline` for each `processed=false` entry, and write back `processed=true` + `processing_task_id` so the feedback page shows “Taken into account”. Obsolete paused Nami feedback cron jobs were removed. Verification: controlled dry-run, live task creation/cleanup, and browser-visible status transition on `https://sa.cedlabusa.net/#feedback` from `Pending` → `Taken into account` with auto note + counter update, then cleanup back to baseline; idle run prints nothing. | ✅ DONE |
| 2026-05-28 | Dedicated user feedback page | Added a user-visible `#feedback` page and header button on the production frontend, plus a global feedback flow independent of ticker. Backend now supports general feedback via `feedback_GENERAL`, keeps ticker-specific history intact, exposes `GET /api/feedback` for user history, and still preserves per-ticker/admin views. Verification: `PYTHONPATH=. .venv/bin/pytest tests/test_feedback.py -q` = 13 passed, `frontend/npm run build` OK, backend listener restarted at 08:48, production browser check on `https://sa.cedlabusa.net/#feedback` shows existing GOOGL feedback with date + status and 0 JS errors. | ✅ DONE |
| 2026-05-28 | Canonical admin feedback store | Root cause fixed for empty admin feedback inbox across `/home` vs `/mnt` runtimes: backend paths now resolve through shared `SA_ANALYSES_DIR`, preload + deep-dive output validation use the same canonical analyses root, and the historical `feedback_GOOGL` folder was migrated into the shared store. Verification: targeted backend tests `tests/test_feedback.py` + `tests/test_storage_paths.py` = 14 passed, backend restarted at 07:55, production admin page now shows 1 Nami feedback entry with 0 JS errors. | ✅ DONE |
| 2026-05-27 | Ticker input rate-limit fix | Root cause of “typing ticker does nothing”: `/api/batch/upload` debounce parser could be 429-limited by prior page/static requests from the same IP. Rate-limit buckets are now per IP+tier, parser stays in the lightweight default tier, and the frontend has a local ticker fallback + visible warning instead of silent failure. Verification: 193 backend/API tests passed + frontend production build. | ✅ DONE |
| 2026-05-27 | API compatibility + test gate | Legacy `{ticker: "NVDA"}` payload accepted for `/api/analyze/async`; FastAPI TestClient auth/rate-limit bypass handles synthetic `testclient` host; `/api/health` and `/api/version` git probes have 5s timeouts. Verification: 192 backend/API tests passed + frontend production build. | ✅ DONE |
| 2026-05-26 | SA-P0-403 | **REVIEW APPROVED**: Root-cause 403 on /api/analyze — process_nami_feedback.py was reading ADMIN_SECRET placeholder instead of CED_CONTROL_KEY. Fix verified: 153/153 tests, 0 JS errors, no more 403. |
| 2026-05-26 | V2.7-T3 | **Integration — Mapper + Pipeline Wiring**: _build_v27_models() populates 3/6 V2.7 models from old metrics + company_overview + scoring. ExecutiveSnapshot (market cap, sector, verdict), FinancialMetrics (EPS/revenue/margins/growth/FCF with display strings), ValuationSection (PE multiples). 13 integration tests (unit + pipeline→PDF). Commit: 0e6bba2. | ✅ DONE |
| 2026-05-26 | V2.7-T2 | **PDF Sections Rendering**: 6 V2.7 section renderer functions in pdf_renderer.py. ExecutiveSnapshot, FinancialMetrics, Valuation, ValuationContext, PeerBenchmark, DataQuality — all integrated into PDF story flow. 36 spec tests. Commit: 6919b8d. | ✅ DONE |
| 2026-05-26 | V2.7-T1 | **Report Model Extension**: 6 structured PDF section Pydantic models (ExecutiveSnapshot, FinancialMetrics, ValuationSection, ValuationContextSection, PeerBenchmarkSection, DataQualitySection). All nullable, USD-only, source/timestamp tracking. 25 spec tests. Commit: a375420. | ✅ DONE |
| 2026-05-25 | V2.6-T1 | Export Snapshot Contract: immutable USD-only snapshot builder, centralized N/A/sanitizer/enums, 4 focused no-fetch tests | ✅ DONE — REVIEW GATE |
| 2026-05-25 | V2.5-T6 | **FINAL QA — APPROVED**: 221/221 tests, 4 API endpoints verified, frontend browser QA, 0 forbidden labels, 0 JS errors, build fresh | ✅ APPROVED — READY FOR ARCHIVE |
| 2026-05-25 | V2.5-T5 | Peer Benchmark Frontend: Group 9 in AnalysisCard, Summary Card + Relative Valuation Table + Quality Table, i18n EN/JP, 8 E2E tests | ✅ DONE — REVIEW GATE |
| 2026-05-25 | V2.5-T1 | Peer Universe: 3 curated groups (NVDA/AAPL/TSLA), loader/validator, 9 tests |
| 2026-05-25 | V2.5-T4 | Peer Benchmark API: GET /api/peer-benchmark/{ticker}, peer_context + benchmarks + summary, 16 tests | ✅ DONE — REVIEW GATE |
| 2026-05-25 | V2.5-T3 | Peer Benchmark Engine: 6 pure functions (median, percentile rank, spread, direction, labels, summary), 47 tests | ✅ REVIEWED |
| 2026-05-25 | V2.5-T2 | Peer Batch Layer: get_peer_benchmark_snapshot() with cache + partial failure, 9 tests | ✅ REVIEWED |
| 2026-05-25 | V2.4 Frontend | Valuation Context UI: mini summary card with 5 fields, enriched tooltips on 5 metrics, N/A handling, prudent wording |
| 2026-05-25 | V2.4 Backend | `/api/valuation-context/{ticker}` endpoint with 7 context signals |
| 2026-05-25 | V2.3 | Historical valuation data feasibility (PARTIAL) |
| 2026-05-25 | P0-F2F3 | 6-category scoring chart, deep-dive mapper |
| 2026-05-25 | Swarm | Codebase audit: 3 largest files (pipeline.py=2447, mapper.py=2297, main.py=2010) — 165 .py files total |

## Non-Regression Playbooks
- **When modifying ValuationGroup**: run `node chartUtils.test.cjs` (68 tests), rebuild frontend, test NVDA and MSFT
- **When modifying PeerBenchmarkGroup**: run `npm run build`, verify browser console 0 errors, test NVDA/AAPL/TSLA
- **When modifying backend routes**: run `pytest backend/tests/` (153 tests)
- **Before any deploy**: rebuild frontend (`npm run build`), verify bundle has expected code

## Quality Gates
- Frontend build: `npm run build` must succeed (49 modules)
- Tests: 153 backend + 68 frontend = 0 failures
- Browser console: 0 errors, 0 warnings
- Review by different agent required before merge
