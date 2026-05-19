# Spécification technique — Stock Analysis Pipeline v1.1

| Métadonnée | Valeur |
|---|---|
| Projet | Stock Analysis Pipeline |
| Version | 1.1 |
| Nature | Référence technique vérifiée |
| Prédécesseur | v1.0 (2026-05-18) |
| Auteurs | Hermes + Codex CLI (review) |
| Statut | Brouillon en review externe |
| Date | 2026-05-18 |

## 1. Stack technique

| Couche | Technologie | Version | Justification |
|---|---|---|---|
| Backend | Python + FastAPI | 3.11+ / 0.115+ | Léger, asynchrone natif, écosystème data |
| Frontend | React + Vite | React 18+ | UX riche (téléchargements, états complexes) |
| PDF Engine | ReportLab | 4.x | Contrôle layout précis (tables, callout boxes) |
| Scoring | Rules engine déterministe | — | 40 pts, 6 catégories, pas de ML |
| Sources | yfinance, Finnhub, EDGAR, Seeking Alpha, Tavily, Alpha Vantage | — | Données publiques / freemium |
| Tunnel | Cloudflare Tunnel (named) | — | Exposition sécurisée, domaine stable |
| Runtime | WSL2, venv | — | Python, asynchrone |
| Tests | pytest, pytest-asyncio, Playwright | — | Unitaire + E2E |

## 2. Architecture

### 2.1 Diagramme de déploiement

```
Navigateur ──→ sa.cedlabusa.net (Cloudflare Edge)
                    │
                    ▼ Tunnel Cloudflare (named, e92cfcfb)
                    │
                    ▼ Backend FastAPI (localhost:8780)
                    │
       ┌────────────┼───────────────┐
       ▼            ▼               ▼
   StaticFiles   Middleware       Router API
   (dist/)       (CORS, API-Key)  (29 routes, 6 groupes)
       │            │               │
       └────────────┴───────────────┘
                    │
       ┌────────────┼───────────────┬────────────┬──────────┐
       ▼            ▼               ▼            ▼          ▼
   yfinance     Finnhub          EDGAR       SeekingA    Tavily       AlphaV
   (pricing)    (financials)     (filings)   (transcr.)  (IR web)    (backup)
```

### 2.2 Structure des modules

```
backend/
├── main.py                   # Routes API (29 endpoints) + StaticFiles + Middleware
├── pipeline.py               # Orchestration 9 étapes
├── models.py                 # Pydantic models (AnalysisResult, Scoring, etc.)
├── sources_collector.py      # Collecte multi-source (yfinance, Finnhub, EDGAR)
├── scorer.py                 # Scoring rules-based 40 pts
├── transcript_finder.py      # Recherche transcripts (Seeking Alpha, web)
├── edgar_extractor.py        # SEC EDGAR filings parsing
├── sec_8k.py                 # 8-K filings specific parser
├── feedback_store.py         # Gestion feedback horodaté
├── rapidapi_sa.py            # Seeking Alpha via RapidAPI
├── earnings_deep_dive/
│   ├── schemas.py            # DeepDiveRequest, DeepDiveResponse
│   ├── collector.py          # Collecte données deep-dive
│   └── renderer.py           # ReportLab PDF renderer
├── cache/                    # Cache volatil données financières
├── logs/                     # Logs structurés JSON
└── analyses/                 # Analyses archivées (ticker_timestamp/)
```

### 2.3 Pipeline 9 étapes (flux de données)

```
PIP-001 Profil ──→ yfinance
PIP-002 Collecte ──→ yfinance + Finnhub + EDGAR
PIP-003 Transcripts ──→ Seeking Alpha + Tavily
PIP-004 SEC ──→ EDGAR (edgartools)
PIP-005 Management ──→ LLM (tone analysis)
PIP-006 Scoring ──→ Rules engine (40 pts)
PIP-007 Deep-dive ──→ LLM (synthèse narrative)
PIP-008 PDF ──→ ReportLab
PIP-009 Archive ──→ analyses/ + ZIP
```

## 3. Routes API (auditées 2026-05-18)

Vérifié via `grep -n '@app\.' backend/main.py` — 29 routes uniques.

### 3.1 Health & Debug

| ID | Méthode | Path | Description | Auth |
|---|---|---|---|---|
| API-001 | GET | `/api/health` | Health check (uptime, status) | Non |
| API-002 | GET | `/api/debug/yf-cache/{ticker}` | Debug cache yfinance | Non |
| API-003 | GET | `/api/debug/sources` | Debug sources disponibles | Non |

### 3.2 Analyse

| ID | Méthode | Path | Description | Auth |
|---|---|---|---|---|
| API-010 | POST | `/api/analyze` | Analyse synchrone complète | Non |
| API-011 | POST | `/api/analyze/async` | Analyse asynchrone (background job) | Non |
| API-012 | GET | `/api/analyze/job/{job_id}` | Statut job async | Non |
| API-013 | GET | `/api/analyze/{ticker}/download` | Télécharger analyse JSON | Non |

### 3.3 Earnings Deep-dive

| ID | Méthode | Path | Description | Auth |
|---|---|---|---|---|
| API-020 | GET | `/api/earnings/quarters/{ticker}` | Lister les quarters disponibles | Non |
| API-021 | POST | `/api/earnings/deep-dive` | Générer deep-dive LLM | Non |
| API-022 | HEAD | `/api/report/{ticker}/pdf` | Vérifier existence PDF | Non |
| API-023 | GET | `/api/report/{ticker}/pdf` | Télécharger PDF deep-dive | Non |
| API-024 | HEAD | `/api/report/{ticker}` | Vérifier existence rapport HTML | Non |
| API-025 | GET | `/api/report/{ticker}` | Voir rapport HTML | Non |

### 3.4 Dossier ZIP

| ID | Méthode | Path | Description | Auth |
|---|---|---|---|---|
| API-030 | GET | `/api/dossier/{ticker}/status` | Statut dossier | Non |
| API-031 | GET | `/api/dossier/{ticker}/download` | Télécharger ZIP | Non |
| API-032 | POST | `/api/dossier/{ticker}/upload` | Upload dossier personnalisé | Oui |

### 3.5 Batch

| ID | Méthode | Path | Description | Auth |
|---|---|---|---|---|
| API-040 | POST | `/api/batch/upload` | Upload CSV tickers | Non |
| API-041 | POST | `/api/batch/analyze` | Lancer batch analysis | Non |
| API-042 | GET | `/api/batch/{job_id}/status` | Statut batch job | Non |
| API-043 | GET | `/api/batch/{job_id}/download` | Télécharger résultats batch | Non |

### 3.6 Sources & Cache

| ID | Méthode | Path | Description | Auth |
|---|---|---|---|---|
| API-050 | GET | `/api/sources/{ticker}` | Sources collectées | Non |
| API-051 | GET | `/api/traceability/{ticker}` | Traçabilité des sources | Non |
| API-052 | POST | `/api/cache/financials/{ticker}` | Rafraîchir cache | Non |

### 3.7 Feedback & Admin

| ID | Méthode | Path | Description | Auth |
|---|---|---|---|---|
| API-060 | POST | `/api/feedback` | Envoyer feedback | Non |
| API-061 | GET | `/api/feedback/{ticker}` | Lire feedback ticker | Non |
| API-062 | GET | `/api/admin/feedback` | Tout feedback | Non |
| API-063 | GET | `/api/admin/recent-searches` | Recherches récentes | Non |
| API-064 | GET | `/api/admin/search-stats` | Stats recherche | Non |
| API-065 | GET | `/api/analyses` | Liste analyses disponibles | Non |

**Total : 29 routes API** (3 health/debug + 4 analyse + 6 deep-dive + 3 dossier + 4 batch + 3 sources + 6 admin/feedback).

## 4. Middleware et configuration

### 4.1 CORS

```python
# Middleware HTTP (ligne 95 de main.py)
# Allow: sa.cedlabusa.net, localhost:8780, localhost:5173 (dev)
```

### 4.2 Auth

```python
# X-API-Key header requis pour tous les endpoints write + admin (15 routes protégées)
# Configuré via .env : CED_CONTROL_KEY
# Lecture endpoints (GET) = public (sauf admin/debug)
# Bypass: localhost + same-origin (frontend sur sa.cedlabusa.net)
```

### 4.3 Static Files

```python
# CacheBustingStaticFiles (Cache-Control: no-cache)
# Monte frontend/dist/ sur /
# Fallback SPA : index.html pour routes React inconnues
```

### 4.4 Rate limiting

Rate limiter middleware (in-memory token bucket, 60s window) :
- **Heavy** (10 req/min) : `/api/analyze`, `/api/analyze/async`, `/api/earnings/deep-dive`, `/api/batch/analyze`
- **Moderate** (30 req/min) : `/api/feedback`, `/api/cache/financials/*`, `/api/dossier/*`, `/api/batch/upload`
- **Default** (120 req/min) : tous les autres endpoints
- **Skipped** : `/api/health` uniquement
- Les limites externes (BR-006 : backoff exponentiel) restent en complément. Le batch est limité à 10 tickers dans le code.

## 5. Modèle de scoring

| Catégorie | ID | Points | Données | Logique |
|---|---|---|---|---|
| Financial Health | SC-FIN | /10 | Dette/equity, current ratio, FCF | Ratio → seuil → points |
| Growth | SC-GRW | /10 | Revenue growth YoY, EPS trend | % croissance → seuil → points |
| Valuation | SC-VAL | /8 | PER, PEG, P/B, EV/EBITDA | Comparaison secteur → points |
| Management | SC-MGT | /5 | Tone analysis, insider trades | Positif/négatif → points |
| Moat | SC-MOA | /4 | Gross margin, market share | Marge > seuil → points |
| Sentiment | SC-SEN | /3 | News sentiment, analyst ratings | Positif/négatif/neutre → points |

**Pondération :** BUY ≥ 28, HOLD 18–27, SELL < 18.

## 6. Gestion des erreurs

| Erreur | Code HTTP | Condition | Comportement |
|---|---|---|---|
| Ticker invalide | 400 | Ticker < 1 ou > 5 char, ou non trouvé | `{"error": "Invalid ticker"}` |
| Ticker non trouvé | 404 | yfinance ne trouve pas | `{"error": "Ticker not found"}` |
| Analyse déjà en cours | 409 | Job async actif pour ce ticker | `{"error": "Analysis in progress", "job_id": "..."}` |
| Batch trop grand | 400 | CSV > 10 tickers | `{"error": "Max 10 tickers per batch"}` |
| API source timeout | 503 | > 30s aucune réponse | Continuer avec sources restantes (pas d'erreur utilisateur) |
| Rate limit source | — | 429 API externe | Retry interne (3x, backoff), skip si échec |
| PDF non trouvé | 404 | GET /api/report/{t}/pdf sans analyse | `{"error": "No report for this ticker"}` |
| Donnée manquante | — | Champ null retourné par API | "DONNÉE NON DISPONIBLE" dans le PDF |
| Erreur interne | 500 | Exception non rattrapée | Log error + `{"error": "Internal error"}` |

## 7. Sources de données

| Source | Module | Rate limit | Timeout | Fallback |
|---|---|---|---|---|
| Yahoo Finance | yfinance | ~5 req/s (informel) | 15 s | Finnhub pour financials |
| Finnhub | finnhub-python | 60 req/min | 10 s | EDGAR pour fundamentals |
| SEC EDGAR | edgartools | ~10 req/s | 20 s | Aucun (source primaire) |
| Seeking Alpha | rapidapi_sa.py + scraping | Variable | 25 s | Tavily + Alpha Vantage |
| Tavily | tavily API | 1000 req/mois | 10 s | DDG (dégradé) |
| Alpha Vantage | alpha_vantage.py | 25 req/jour | 10 s | Cache + Finnhub |

## 8. Sécurité

| ID | Mesure | Implémentation |
|---|---|---|
| SEC-001 | Secrets dans .env | Jamais commités (.gitignore), chargés par python-dotenv |
| SEC-002 | X-API-Key write endpoints | Vérifié dans le middleware, depuis CED_CONTROL_KEY env |
| SEC-003 | CORS restreint | Allow: sa.cedlabusa.net, localhost:8780, localhost:5173 |
| SEC-004 | Pas de secrets dans les logs | Logs JSON structurés sans .env values |
| SEC-005 | Cloudflare TLS | Named tunnel, chiffrement de bout en bout |

## 9. Tests

### 9.1 Suite de tests

| Fichier | Type | Couvre | Exécution |
|---|---|---|---|
| `tests/test_pipeline.py` | Unitaire | Étapes pipeline (mock I/O) | `pytest tests/ -v` |
| `tests/test_scorer.py` | Unitaire | Calcul score 40 pts | `pytest tests/test_scorer.py -v` |
| `tests/test_sources_collector.py` | Unitaire | Collecte avec mock APIs | `pytest tests/ -v` |
| `tests/test_edgar.py` | Unitaire | Parsing SEC filings | `pytest tests/test_edgar.py -v` |
| `tests/test_renderer.py` | Unitaire | Génération PDF (output check) | `pytest tests/test_renderer.py -v` |
| `tests_e2e/test_sa_recette.py` | E2E | Parcours complet navigateur | `pytest tests_e2e/ -v --headed` |
| `tests_e2e/conftest.py` | Fixtures | Setup Playwright | Automatique |

### 9.2 Commandes

```bash
# Tests unitaires
cd backend && PYTHONPATH=.. python -m pytest tests/ -v

# Tests E2E (avec navigateur visible)
PYTHONPATH=.. python -m pytest tests_e2e/ -v --headed

# Coverage
PYTHONPATH=.. python -m pytest tests/ --cov=. --cov-report=term-missing
```

## 10. Déploiement

### 10.1 Backend

```bash
cd /home/ced/codex-projects/stock-analysis-pipeline/backend
source .venv/bin/activate
PYTHONPATH=.. uvicorn main:app --host 0.0.0.0 --port 8780
```

### 10.2 Frontend

```bash
cd /home/ced/codex-projects/stock-analysis-pipeline/frontend
npm run build     # → backend/frontend/dist/
# Servi par le backend via CacheBustingStaticFiles
```

### 10.3 Tunnel Cloudflare

```bash
# Production (named tunnel)
cloudflared tunnel run e92cfcfb-86b6-4e36-9669-2120cad8bed3

# Service systemd
systemctl --user start cloudflared-tunnel
```

### 10.4 Vérification post-déploiement

```bash
curl -s -w "\nHTTP %{http_code}" https://sa.cedlabusa.net/api/health
```

## 11. Production et monitoring

### 11.1 Auto-recovery

Script : `~/.hermes/scripts/hermes_auto_recover.sh`
- Cron : toutes les 15 minutes
- Vérifie `curl https://sa.cedlabusa.net/api/health`
- Si != 200 → `systemctl --user restart cloudflared-tunnel`
- Si toujours down → alerte Telegram

### 11.2 Logs

- Emplacement : `backend/logs/`
- Format : JSON structuré
- Champs : timestamp, ticker, step, duration_ms, error
- Rotation : manuelle (pas de logrotate configuré)

### 11.3 Cache

- Emplacement : `backend/cache/`
- Invalidation : refresh forcé (POST /api/cache/financials/{ticker}) ou > 1h
- Stockage : fichiers JSON par ticker

## 12. Pièges techniques connus

| ID | Piège | Symptôme | Fix |
|---|---|---|---|
| PIT-001 | Double bookkeeping | Score erroné après enrichissement EDGAR | Commit 3cf8f9b : sync financials + fin |
| PIT-002 | Quick tunnel parasite | Domaine non stable | `ps aux | grep cloudflared` → kill quick |
| PIT-003 | Double prefix CF | /stock-analysis/stock-analysis/ JS 404 | Accéder via https://sa.cedlabusa.net/ |
| PIT-004 | Build frontend manquant | 404 sur fichiers JS/CSS | `npm run build` avant de démarrer le backend |
| PIT-005 | Indentation Python PDF renderer | PDF retourne None | Fonctions helper avant la fonction render |
| PIT-006 | Port Windows ghost | Process Windows sur :8780 non visible WSL | `powershell.exe 'Get-NetTCPConnection -LocalPort 8780'` |
| PIT-007 | Frontend bundle stale | Changements frontend non visibles | `rm -rf dist/ cache/ && npm run build` |

## 13. Questions techniques ouvertes

| ID | Question | Impact | Statut |
|---|---|---|---|
| Q-001 | Migrer vers cache Redis ? | Performance analyses multiples (> 3 batch) | À évaluer |
| Q-002 | Base de données (SQLite/PostgreSQL) ? | Persistance, recherche historique | À décider |
| Q-003 | Containerisation Docker ? | Portabilité, isolation | Non prioritaire (WSL OK) |
| Q-004 | Frontend mobile responsive ? | Usage mobile Ced | À décider |
| Q-005 | Log rotation automatique ? | Gestion disque | À implémenter |
