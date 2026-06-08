# stock-analysis-pipeline

- **Stack**: Python, React, Vite
- **LOC**: 30,566
- **Path**: `/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline`
- **Dernière indexation**: 2026-05-06 06:54 UTC

## 📊 Langages

| Langage | Lignes |
|---------|--------|
| Python | 13,112 |
| JSON | 8,287 |
| Markdown | 6,792 |
| JavaScript React | 1,784 |
| JavaScript | 406 |
| Shell | 90 |
| YAML | 79 |
| HTML | 16 |

## 🏗️ Architecture (AGENTS.md)

```markdown
# AGENTS.md — Stock Analysis Pipeline

## 1. Sécurité — NON NÉGOCIABLE
- Secrets dans .env uniquement. .env dans .gitignore AVANT premier commit.
- Pas de sudo, pas de droits admin, pas de registre Windows.
- Endpoint externe → prévenir avant curl/API.
- Sandbox : travailler uniquement dans `stock-analysis-pipeline/`.

## 2. Qualité — NON NÉGOCIABLE
- TDD : pas de code sans test échouant d'abord. RED → GREEN → REFACTOR.
- Backup avant modif de config : `cp fichier fichier.bak`.
- Pas de replace_all=true sur du code.
- Commit atomique à chaque feature qui marche.

## 3. Git — NON NÉGOCIABLE
- `git diff --staged --stat` avant chaque commit.
- Jamais `git add -A` sans vérifier le staging.
- Pas de commit de logs, .env, node_modules, analyses/, ou binaires.

## 4. Validation — NON NÉGOCIABLE
- Fichiers créés → `stat` ou `ls -la`
- Endpoints → `curl` et vérifier le status code
- Frontend → `browser_navigate` + `browser_console`
- Tests → lancés et passés

## 5. Stack
- Backend: Python 3.11+ FastAPI, yfinance, finnhub-python
- Frontend: React + Vite
- Tests: pytest, pytest-asyncio

## 6. Règle anti-invention
Toute donnée financière doit être sourcée. Si une donnée manque → "DONNÉE NON DISPONIBLE".
Les conclusions doivent être auditables à partir du dossier de sources.
```

## 🧱 Code Structure

### `backend/earnings_deep_dive/errors.py`

- **`EarningsDeepDiveError`**
  - *(no methods)*
- **`TranscriptMissingError`**
  - *(no methods)*
- **`KimiFailureError`**
  - *(no methods)*
- **`ValidationError`**
  - *(no methods)*

### `backend/earnings_deep_dive/prompts.py`

- **`SectionName`**
  - `__new__(cls,canonical:str,title:str) -> "SectionName"`
  - `__str__(self) -> str`
  - `__repr__(self) -> str`
  - `__contains__(self,item:object) -> bool`
  - `translate(self,table:Any) -> str`

### `backend/earnings_deep_dive/schemas.py`

- **`FinancialMetrics`**
  - *(no methods)*
- **`DeepDiveRequest`**
  - `normalize_ticker(cls,value:str) -> str`
  - `strip_company(cls,value:Optional[str]) -> Optional[str]`
- **`SectionStatus`**
  - *(no methods)*
- **`DeepDiveResponse`**
  - *(no methods)*

### `backend/logging_config.py`

- **`SecretRedactingFormatter`**
  - `__init__(self,fmt=None,datefmt=None)`
  - `format(self,record)`
- **`ContextInjectingFormatter`**
  - `format(self,record)`
- **`LogContext`**
  - `__init__(self,job_id:Optional[str]=None,ticker:Optional[str]=None)`
  - `__enter__(self)`
  - `__exit__(self,*args)`
- **`ContextAdapter`**
  - `process(self,msg,kwargs)`

### `backend/main.py`

- **`BatchAnalyzeRequest`**
  - *(no methods)*

### `backend/models.py`

- **`TickerRequest`**
  - *(no methods)*
- **`FinancialData`**
  - *(no methods)*
- **`SegmentInfo`**
  - *(no methods)*
- **`ManagementTone`**
  - *(no methods)*
- **`RiskItem`**
  - *(no methods)*
- **`ValuationData`**
  - *(no methods)*
- **`Scoring`**
  - `total(self) -> int`
  - `decision(self) -> str`
- **`Source`**
  - *(no methods)*
- **`Claim`**
  - *(no methods)*
- **`AnalysisResult`**
  - *(no methods)*
- **`AnalysisJobResponse`**
  - *(no methods)*
- **`AnalysisJobStatus`**
  - *(no methods)*

### `tests/test_circuit_breaker.py`

- **`TestCircuitBreakerFinnhub`**
  - `test_finnhub_retries_on_429(self)`
  - `test_finnhub_gives_up_after_max_retries(self)`
  - `test_finnhub_handles_timeout(self)`
- **`TestSourcesManifestAccuracy`**
  - `test_get_stock_data_returns_source_info(self)`

### `tests/test_coverage_gaps.py`

- **`TestHealthEndpoint`**
  - `test_health_returns_correct_structure(self)`
- **`TestAnalysesList`**
  - `test_analyses_list_returns_array(self)`
- **`TestBatchUpload`**
  - `test_batch_upload_no_file_400(self)`
- **`TestSourcesEndpoint`**
  - `test_sources_404_for_unknown_ticker(self)`
- **`TestTraceabilityEndpoint`**
  - `test_traceability_404_for_unknown_ticker(self)`
- **`TestReportEndpoint`**
  - `test_report_404_for_unknown_ticker(self)`
  - `test_report_pdf_404_for_unknown_ticker(self)`
- **`TestBatchJobNotFound`**
  - `test_batch_status_404(self)`
  - `test_batch_download_404(self)`
- **`TestEURConversion`**
  - `test_convert_to_eur_basic(self)`
- **`TestScoringEdgeCases`**
  - `test_score_management_realtime_with_multilingual_tone(self)`
  - `test_score_geopolitical_all_sectors(self)`
  - `test_scoring_total_property(self)`

### `tests/test_integration.py`

- **`TestAnalyzeEndpoint`**
  - `test_analyze_returns_correct_structure(self,mock_10k,mock_yf)`
  - `test_analyze_handles_missing_data_gracefully(self,mock_10k,mock_yf)`
  - `test_analyze_invalid_ticker_format_422(self)`
  - `test_analyze_empty_tickers_422(self)`
  - `test_analyze_lang_ja_propagates(self)`
- **`TestRateLimit`**
  - `test_rate_limit_analyze_endpoint(self)`
  - `test_health_endpoint_not_rate_limited(self)`
- **`TestDebugEndpoint`**
  - `test_debug_yf_cache_blocked_in_production(self)`
  - `test_debug_sources_blocked_in_production(self)`
- **`TestDossierTranslation`**
  - `test_ja_download_does_not_mutate_originals(self,mock_10k,mock_yf)`

### `tests/test_models.py`

- **`TestTickerRequest`**
  - `test_valid_single_ticker(self)`
  - `test_valid_multiple_tickers(self)`
  - `test_empty_tickers_rejected(self)`
  - `test_max_10_tickers(self)`
- **`TestScoring`**
  - `test_total_sums_all_criteria(self)`
  - `test_default_all_zero(self)`
  - `test_decision_buy(self)`
  - `test_decision_hold_pullback(self)`
  - `test_decision_hold_fragile(self)`
  - `test_decision_sell(self)`
- **`TestFinancialData`**
  - `test_defaults_all_none(self)`
  - `test_partial_data(self)`
- **`TestAnalysisResult`**
  - `test_default_factory_creates_submodels(self)`
- **`TestSource`**
  - `test_valid_source(self)`
- **`TestClaim`**
  - `test_valid_claim(self)`
- **`TestAnalysisJobResponse`**
  - `test_default_status_processing(self)`
- **`TestAnalysisJobStatus`**
  - `test_empty_results_by_default(self)`

### `tests/test_rapidapi_sa.py`

- **`FakeResponse`**
  - `__init__(self,payload,status_code=200)`
  - `json(self)`

### `tests/test_scorer.py`

- **`TestScoreTicker`**
  - `test_high_growth_buy(self)`
  - `test_stable_big_tech(self)`
  - `test_struggling_value(self)`
  - `test_all_none_data_returns_neutral(self)`
- **`TestIndividualScoreFunctions`**
  - `test_all_scores_in_range(self)`

### `tests/test_seeking_alpha.py`

- **`TestSeekingAlpha`**
  - `test_fetch_fool_transcript_function(self)`
  - `test_search_transcript_web_with_text(self)`

## 🔌 APIs / Endpoints

| Méthode | Path | Framework | Fichier |
|---------|------|-----------|---------|
| POST | `/api/batch/upload` | FastAPI | `backend/main.py` |
| POST | `/api/batch/analyze` | FastAPI | `backend/main.py` |
| GET | `/api/batch/{job_id}/status` | FastAPI | `backend/main.py` |
| GET | `/api/batch/{job_id}/download` | FastAPI | `backend/main.py` |
| GET | `/api/analyze/{ticker}/download` | FastAPI | `backend/main.py` |
| GET | `/api/health` | FastAPI | `backend/main.py` |
| GET | `/api/debug/yf-cache/{ticker}` | FastAPI | `backend/main.py` |
| GET | `/api/debug/sources` | FastAPI | `backend/main.py` |
| GET | `/api/earnings/quarters/{ticker}` | FastAPI | `backend/main.py` |
| POST | `/api/earnings/deep-dive` | FastAPI | `backend/main.py` |
| GET | `/api/dossier/{ticker}/status` | FastAPI | `backend/main.py` |
| GET | `/api/dossier/{ticker}/download` | FastAPI | `backend/main.py` |
| POST | `/api/dossier/{ticker}/upload` | FastAPI | `backend/main.py` |
| POST | `/api/analyze` | FastAPI | `backend/main.py` |
| GET | `/api/report/{ticker}/pdf` | FastAPI | `backend/main.py` |
| GET | `/api/report/{ticker}` | FastAPI | `backend/main.py` |
| GET | `/api/sources/{ticker}` | FastAPI | `backend/main.py` |
| GET | `/api/traceability/{ticker}` | FastAPI | `backend/main.py` |
| POST | `/api/cache/financials/{ticker}` | FastAPI | `backend/main.py` |
| GET | `/api/analyses` | FastAPI | `backend/main.py` |

## 📁 Fichiers clés

| Fichier | Rôle |
|---------|------|
| `AGENTS.md` | Règles agent |
| `requirements.txt` | Dépendances Python |
| `analyses/2026-05-04_NVDA_NVIDIA_Corp/05_market_and_context/README.md` | Documentation projet |
| `backend/requirements.txt` | Dépendances Python |
| `frontend/package.json` | Dépendances & scripts Node |
| `frontend/vite.config.js` | Configuration |

## 📐 Conventions

- **Tests**: `pytest` — `python -m pytest tests/ -v`
