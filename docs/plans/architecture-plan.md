# Stock Analysis Pipeline — Architecture Plan

> **Date:** 2026-05-04
> **Architect:** Hermes (solo — Codex non disponible)
> **Post-mortem 03/05 appliqué:** Plan avant code, TDD, sub-agents, verification, commits atomiques

---

## Objectif

Application web d'analyse action (BUY/HOLD/SELL) avec pipeline 9 étapes,
dossier de sources traçable, et parallélisation par ticker.

## Architecture globale

```
┌─────────────────────────────────────────────────┐
│  Frontend React + Vite (port 5180)              │
│  - Input: tickers (comma-separated)             │
│  - Bouton "Analyser" → POST /api/analyze        │
│  - Dashboard: cartes par ticker, scoring,       │
│    expand vers rapport complet                  │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│  FastAPI Backend (port 8780)                    │
│  - POST /api/analyze {"tickers": [...]}         │
│  - GET /api/analyze/{job_id} (poll status)      │
│  - GET /api/report/{ticker} (rapport markdown)  │
│  - GET /api/sources/{ticker} (manifest JSON)    │
│                                                  │
│  Orchestrateur:                                  │
│  - Reçoit N tickers                              │
│  - Spawn N sub-agents via delegate_task         │
│  - Chaque agent retourne le rapport + manifest   │
│  - Agrège les résultats pour le frontend         │
└──────────────────┬──────────────────────────────┘
                   │
     ┌─────────────┼─────────────┬─────────────┬──────────────┐
     ▼             ▼             ▼             ▼             ▼
  Agent         Agent         Agent         Agent         Agent
  NVDA          MSFT          ASML          MC.PA         AAPL
  (9 étapes)    (9 étapes)    (9 étapes)    (9 étapes)    (9 étapes)
     │             │             │             │             │
     ▼             ▼             ▼             ▼             ▼
  /analyses/    /analyses/    /analyses/    /analyses/    /analyses/
  2026-05-04    2026-05-04    2026-05-04    2026-05-04    2026-05-04
  _NVDA_...     _MSFT_...     _ASML_...     _MC_...       _AAPL_...
```

## Stack technique

| Couche | Techno | Justification |
|--------|--------|---------------|
| Backend | Python 3.11 + FastAPI | Async, performant, familier |
| Finance | yfinance + finnhub-python | Gratuits, données US+EU |
| SEC | requests → sec.gov EDGAR API | Public, fiable |
| Frontend | React + Vite | Même stack que AlphaRadarWeb |
| Parallélisation | delegate_task (DeepSeek V4 Pro) | 1 agent par ticker |
| Tests | pytest + pytest-asyncio | TDD |

## Structure du projet

```
stock-analysis-pipeline/
├── AGENTS.md                    # Règles de sécurité
├── SKILLS.md                    # Skills essentiels
├── .gitignore
├── .env                         # FINNHUB_API_KEY, etc.
├── backend/
│   ├── main.py                  # FastAPI app + routes
│   ├── orchestrator.py          # Spawn sub-agents, aggrège résultats
│   ├── pipeline.py              # Les 9 étapes du pipeline (exécutées par agent)
│   ├── sources_collector.py     # Collecte des sources (YF, Finnhub, SEC)
│   ├── scorer.py                # Scoring sur 40 points
│   └── models.py                # Pydantic models
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Point d'entrée
│   │   ├── components/
│   │   │   ├── TickerInput.jsx  # Input + bouton
│   │   │   ├── AnalysisCard.jsx # Carte par ticker (score, décision)
│   │   │   ├── ReportView.jsx   # Rapport complet (markdown)
│   │   │   └── SourcesView.jsx  # Manifest des sources
│   │   └── api.js               # Client API
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── tests/
│   ├── test_pipeline.py
│   ├── test_orchestrator.py
│   ├── test_scorer.py
│   └── test_models.py
├── analyses/                    # Généré au runtime, gitignoré
│   └── {YYYY-MM-DD}_{TICKER}_{NAME}/
│       ├── 01_official_company_sources/
│       ├── 02_sec_or_regulatory_filings/
│       ├── 03_financial_data_sources/
│       ├── 04_transcripts_and_management/
│       ├── 05_market_and_context/
│       ├── 06_extracted_data/
│       │   ├── extracted_financials.json
│       │   ├── extracted_risks.json
│       │   ├── extracted_management_quotes.json
│       │   ├── sources_manifest.json
│       │   └── claim_traceability_matrix.csv
│       └── 07_final_report/
│           └── report.md
└── docs/
    └── plans/
        └── architecture-plan.md
```

## Pipeline 9 étapes (exécuté par chaque agent)

| # | Étape | Sources | Livrable |
|---|-------|---------|----------|
| 1 | Identification | yfinance | Ticker, nom, secteur, capi, prix, prix EUR |
| 2 | Chiffres financiers | yfinance + Finnhub | CA, croissance, marges, RN, FCF, dette, guidance |
| 3 | Segments | Finnhub + site entreprise | Segment principal, %CA, croissance |
| 4 | Discours management | SEC EDGAR (latest 10-K/10-Q) | Ton, confiance, promesses, signaux défensifs |
| 5 | Risques officiels | SEC EDGAR (Risk Factors) | Concentration, cyclicité, supply chain, régulation |
| 6 | Valorisation | yfinance | PE actuel, forward PE, PEG, marge sécurité |
| 7 | Scoring | Calculé | 8 critères ×5 = /40 |
| 8 | Décision | Règles scoring | BUY/HOLD/SELL + conditions |
| 9 | Sortie | Généré | report.md + sources_manifest.json + claim_traceability_matrix.csv |

## Sub-agent contract (chaque agent reçoit)

```python
goal = "Analyser le ticker {TICKER} et produire le rapport complet + dossier sources"
context = """
PIPELINE: exécute les 9 étapes dans l'ordre.
SOURCES: yfinance, Finnhub API (clé dans .env), SEC EDGAR API.
RÈGLE ABSOLUE: pas de donnée inventée. Si indisponible → 'DONNÉE NON DISPONIBLE'.
FORMAT SORTIE: report.md (markdown) + sources_manifest.json + claim_traceability_matrix.csv.
DOSSIER: analyses/{date}_{TICKER}_{NOM}/
"""
```

## Implémentation en 3 phases

### Phase 1 — Backend
1. `models.py` — Pydantic models (TickerRequest, AnalysisResult, Source, Claim)
2. `sources_collector.py` — yfinance wrapper, Finnhub wrapper, SEC EDGAR fetcher
3. `pipeline.py` — 9 étapes séquentielles, produit le rapport
4. `scorer.py` — Scoring /40
5. `orchestrator.py` — Spawn delegate_task par ticker, aggrège
6. `main.py` — FastAPI routes (POST /analyze, GET /report, GET /sources)

### Phase 2 — Frontend
1. `api.js` — Client API
2. `TickerInput.jsx` — Champ texte + bouton "Analyser"
3. `AnalysisCard.jsx` — Carte résumé (score, décision, KPIs)
4. `ReportView.jsx` — Rapport complet
5. `App.jsx` — Assemblage

### Phase 3 — Intégration
1. Backend + Frontend start scripts
2. Test avec 5 tickers (NVDA, MSFT, ASML, MC.PA, AAPL)
3. Recette visuelle (browser_navigate + console)
4. Commit final

## Règles appliquées du post-mortem 03/05

| Erreur | Contre-mesure |
|--------|---------------|
| Annonce sans vérif | `stat` + `curl` + `pytest` avant tout "done" |
| Pas de plan | Ce document |
| Zéro test | TDD pour chaque fichier backend |
| 57 tool calls solo | delegate_task par ticker (max 3 en //) |
| Fichiers fantômes | `find analyses/ -name "*.md"` après chaque batch |
| Hot reload NTFS | curl après chaque modif frontend |
| git add -A sans vérif | `git diff --staged --stat` obligatoire |

## Prochains steps

1. Valider ce plan avec Ced
2. Phase 1: Backend avec TDD
3. Phase 2: Frontend
4. Phase 3: Intégration + test 5 tickers
