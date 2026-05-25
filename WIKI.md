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
