# SA PDF verification package — t_0da449db

Generated: 2026-06-01T17:07:11.078720Z
Artifacts root: `/home/ced/codex-projects/stock-analysis-pipeline/docs/pdf-audits/verification-t_0da449db-20260601T165622Z`

## Coverage
- Tickers scanned: AAPL, GOOGL, MSFT, NVDA, TSLA
- First-page PNG proofs generated: 11
- deep_en: 3 ticker(s) with PNG proof -> AAPL, GOOGL, TSLA
- deep_jp: 3 ticker(s) with PNG proof -> AAPL, GOOGL, NVDA
- company: 5 ticker(s) with PNG proof -> AAPL, GOOGL, MSFT, NVDA, TSLA

## Runtime/health proof
### tb sa-check
```text
🟢 Local API:  OK (http://localhost:8780/api/health)
🟢 Prod API:   OK (https://sa.cedlabusa.net/api/health)
🟢 dist/:      index 645B, bundle 318,844B, 10.6h old (Jun 01 08:32)
🟢 Backend:    PID 1278410, started 15:59, ~3.2h uptime
🟢 Tunnel:     named tunnel running (default from config.yml)

🟢 ALL OK
```

### API health
```text
LOCAL_HEALTH
{"status":"ok","service":"stock-analysis-pipeline","timestamp":"2026-06-01T17:06:33.975922+00:00","version":"v2.3-accepted-243-g3a92b48","commit":"3a92b48"}
PROD_HEALTH
{"status":"ok","service":"stock-analysis-pipeline","timestamp":"2026-06-01T17:06:34.110431+00:00","version":"v2.3-accepted-243-g3a92b48","commit":"3a92b48"}
```

### Backend process
```text
1278410 Mon Jun  1 15:59:12 2026 /home/ced/codex-projects/stock-analysis-pipeline/backend/.venv/bin/python3.12 -m uvicorn backend.main:app --host 0.0.0.0 --port 8780
```

## Pass/Fail per ticker + report type
| Ticker | Report | HTTP | PDF | Pages | First-page PNG | Row status |
|---|---|---:|---|---:|---|---|
| AAPL | company | 200 | yes | 5 | yes | FAIL |
| AAPL | deep_en | 200 | yes | 24 | yes | FAIL |
| AAPL | deep_jp | 200 | yes | 26 | yes | FAIL |
| GOOGL | company | 200 | yes | 6 | yes | FAIL |
| GOOGL | deep_en | 200 | yes | 25 | yes | FAIL |
| GOOGL | deep_jp | 200 | yes | 26 | yes | FAIL |
| MSFT | company | 200 | yes | 4 | yes | FAIL |
| MSFT | deep_en | 202 | no | 0 | no | FAIL |
| MSFT | deep_jp | 202 | no | 0 | no | FAIL |
| NVDA | company | 200 | yes | 6 | yes | FAIL |
| NVDA | deep_en | 202 | no | 0 | no | FAIL |
| NVDA | deep_jp | 200 | yes | 22 | yes | FAIL |
| TSLA | company | 200 | yes | 1 | yes | FAIL |
| TSLA | deep_en | 200 | yes | 19 | yes | FAIL |
| TSLA | deep_jp | 202 | no | 0 | no | FAIL |

## Banned marker QA (pass/fail by marker and report type)
### deep_en
| Marker | Fail rows / total rows | Total occurrences | Verdict |
|---|---:|---:|---|
| `NaN` | 3 / 5 | 286 | FAIL |
| `source: yfinance` | 3 / 5 | 118 | FAIL |
| `S1` | 2 / 5 | 12 | FAIL |
| `null` | 0 / 5 | 0 | PASS |
| `undefined` | 0 / 5 | 0 | PASS |
| `DATA NOT AVAILABLE` | 0 / 5 | 0 | PASS |
| `Not disclosed` | 3 / 5 | 65 | FAIL |

### deep_jp
| Marker | Fail rows / total rows | Total occurrences | Verdict |
|---|---:|---:|---|
| `NaN` | 3 / 5 | 134 | FAIL |
| `source: yfinance` | 3 / 5 | 63 | FAIL |
| `S1` | 3 / 5 | 18 | FAIL |
| `null` | 0 / 5 | 0 | PASS |
| `undefined` | 0 / 5 | 0 | PASS |
| `DATA NOT AVAILABLE` | 0 / 5 | 0 | PASS |
| `Not disclosed` | 3 / 5 | 85 | FAIL |

### company
| Marker | Fail rows / total rows | Total occurrences | Verdict |
|---|---:|---:|---|
| `NaN` | 5 / 5 | 97 | FAIL |
| `source: yfinance` | 0 / 5 | 0 | PASS |
| `S1` | 0 / 5 | 0 | PASS |
| `null` | 0 / 5 | 0 | PASS |
| `undefined` | 0 / 5 | 0 | PASS |
| `DATA NOT AVAILABLE` | 0 / 5 | 0 | PASS |
| `Not disclosed` | 0 / 5 | 0 | PASS |

## Evidence paths
- Raw JSON: `/home/ced/codex-projects/stock-analysis-pipeline/docs/pdf-audits/verification-t_0da449db-20260601T165622Z/verification_raw.json`
- Summary JSON: `/home/ced/codex-projects/stock-analysis-pipeline/docs/pdf-audits/verification-t_0da449db-20260601T165622Z/verification_summary.json`
- Proof PNG dir: `/home/ced/codex-projects/stock-analysis-pipeline/docs/pdf-audits/verification-t_0da449db-20260601T165622Z/proofs`
- Extracted text dir: `/home/ced/codex-projects/stock-analysis-pipeline/docs/pdf-audits/verification-t_0da449db-20260601T165622Z/text`
- Raw HTTP/PDF dir: `/home/ced/codex-projects/stock-analysis-pipeline/docs/pdf-audits/verification-t_0da449db-20260601T165622Z/raw`
