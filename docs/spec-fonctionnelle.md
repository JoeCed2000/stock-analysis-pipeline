# Spécification fonctionnelle — Stock Analysis Pipeline v1.1

| Métadonnée | Valeur |
|---|---|
| Projet | Stock Analysis Pipeline |
| Version | 1.1 |
| Nature | Testable, auditable, vérifiable |
| Prédécesseur | v1.0 (2026-05-18) |
| Auteurs | Hermes + Codex CLI (review) |
| Validateur métier | Ced |
| Statut | Review externe complétée (Codex 2026-05-19 + Hermes self-audit) — corrections appliquées |
| Date | 2026-05-18 |

## 1. Périmètre et définitions

### 1.1 Acteurs

| ID | Acteur | Description | Compétences |
|---|---|---|---|
| ACT-001 | Investisseur principal | Utilisateur unique, investisseur particulier francophone | Analyse financière, tickers US |
| ACT-002 | Auditeur externe | Vérifie la conformité des analyses produites | Contrôle qualité |
| ACT-003 | Veilleur automatique | Cron jobs Hermes de monitoring | Aucune (système) |

### 1.2 Périmètre fonctionnel

| ID | Élément | Justification |
|---|---|---|
| IN-001 | Analyse fondamentale par ticker (9 étapes) | Cœur du produit |
| IN-002 | Scoring BUY/HOLD/SELL (40 points, 6 catégories) | Décision d'investissement |
| IN-003 | PDF deep-dive formaté (10–14 pages, ReportLab) | Livrable principal |
| IN-004 | Dossier ZIP téléchargeable (PDF + analysis.json + sources.json) | Auditabilité |
| IN-005 | Sélection langue EN/JP/bilingual — LLM génère le deep-dive dans la langue choisie (mêmes données, même template PDF). Mode bilingual = EN+JP côte à côte (modele.pdf original) | Usage international |
| IN-006 | Batch analysis API (upload CSV, traitement séquentiel) — UI batch en v1.2 | Efficacité |
| IN-007 | Feedback utilisateur horodaté avec correction | Amélioration continue |
| IN-008 | Collecte IR sites (dates earnings, webcasts) | Enrichissement données |
| IN-009 | Health check et monitoring (endpoint + auto-recovery) | Production |

### 1.3 Hors périmètre

| ID | Élément | Raison |
|---|---|---|
| OUT-001 | Trading automatisé | Analyse seulement, pas exécution |
| OUT-002 | Données temps réel (streaming) | Fondamentale uniquement |
| OUT-003 | Screening de marché (scanner) | Analyse individuelle par ticker |
| OUT-004 | API publique / multi-utilisateur | Usage personnel |
| OUT-005 | Backtesting de stratégies | Projet séparé (hedge-fund-local) |

## 2. Exigences fonctionnelles

### UC-001 — Analyser un ticker

| Champ | Valeur |
|---|---|
| Acteur | ACT-001 |
| Préconditions | Ticker valide sur marché US, API keys configurées |
| Déclencheur | Saisie ticker + clic « Analyze » |
| Postconditions | PDF deep-dive + ZIP disponibles au téléchargement |

**Scénario nominal (AC-001) :**
> **Given** le backend est actif sur le port 8780, **and** les 6 API externes (yfinance, Finnhub, EDGAR, Seeking Alpha, Tavily, Alpha Vantage) sont accessibles, **and** le ticker AAPL est valide
> **When** l'utilisateur saisit « AAPL » et clique « Analyze »
> **Then** le pipeline exécute les 9 étapes séquentiellement, **and** un PDF deep-dive ≥ 10 pages est généré, **and** le score est affiché avec BUY/HOLD/SELL, **and** le bouton « Download ZIP » est actif

**Scénario ticker invalide (AC-002) :**
> **Given** le backend est actif
> **When** l'utilisateur saisit « ZZZZYX » (ticker inexistant)
> **Then** le système retourne un message d'erreur dans les 30 secondes, **and** aucune analyse n'est stockée

**Scénario API source partiellement down (AC-003) :**
> **Given** le backend est actif, **and** l'API Seeking Alpha est indisponible
> **When** l'utilisateur analyse NVDA
> **Then** les données encore disponibles sont collectées (≥ 3 sources), **and** les sections manquantes affichent « DONNÉE NON DISPONIBLE », **and** le score est calculé avec les sources disponibles

### UC-002 — Consulter le PDF deep-dive

| Champ | Valeur |
|---|---|
| Acteur | ACT-001 |
| Préconditions | Analyse complète disponible pour le ticker |
| Déclencheur | Clic « View Full Report » |

**Scénario nominal (AC-004) :**
> **Given** une analyse de NVDA est terminée
> **When** l'utilisateur clique « View Full Report »
> **Then** un PDF s'ouvre dans le navigateur, **and** le PDF contient les 5 sections majeures (Synthèse, Scoring, Finances, Management, Risques), **and** le header bar est dark (#2A2A2A), **and** les callout boxes bleues (#2563EB) sont visibles

**Scénario donnée manquante dans le PDF (AC-005) :**
> **Given** l'analyse de TSLA est terminée, **and** le transcript Q3 est indisponible
> **When** l'utilisateur ouvre le PDF
> **Then** la section transcript affiche « DONNÉE NON DISPONIBLE », **and** aucune donnée n'est inventée ou extrapolée

### UC-003 — Télécharger le dossier ZIP

| Champ | Valeur |
|---|---|
| Acteur | ACT-001 |
| Préconditions | Analyse complète disponible |
| Déclencheur | Clic « Download ZIP » |

**Scénario nominal (AC-006) :**
> **Given** une analyse de NVDA est terminée
> **When** l'utilisateur clique « Download ZIP »
> **Then** un fichier `.zip` est téléchargé, **and** le ZIP contient au minimum : `deep_dive_report.pdf`, `analysis.json`, `sources.json`

### UC-004 — Batch analysis

| Champ | Valeur |
|---|---|
| Acteur | ACT-001 |
| Préconditions | Fichier CSV valide avec ≤ 10 tickers |
| Déclencheur | Upload CSV + clic « Batch Analyze » |

**Scénario nominal (AC-007) :**
> **Given** un CSV contenant 3 tickers (AAPL, MSFT, GOOGL)
> **When** l'utilisateur uploade le CSV et lance le batch
> **Then** les 3 tickers sont traités séquentiellement, **and** un job_id est retourné, **and** le statut est consultable via GET /api/batch/{job_id}/status

### UC-005 — Feedback et correction

| Champ | Valeur |
|---|---|
| Acteur | ACT-001 |
| Préconditions | Une analyse existe pour le ticker |
| Déclencheur | Envoi d'un feedback (score incorrect, donnée manquante) |

**Scénario nominal (AC-008) :**
> **Given** une analyse de NVDA avec score 32/40 est affichée
> **When** l'utilisateur envoie un feedback « Score surévalué, PER trop bas »
> **Then** le feedback est horodaté (timestamp + message), **and** la réanalyse prend en compte le feedback

### UC-006 — Health check système

| Champ | Valeur |
|---|---|
| Acteur | ACT-003 (Veilleur automatique) |
| Préconditions | Cron job actif |
| Déclencheur | Toutes les 15 minutes |

**Scénario nominal (AC-009) :**
> **Given** le backend tourne sur le port 8780
> **When** le cron job appelle GET /api/health
> **Then** le endpoint retourne 200 avec `{"status": "healthy", "uptime": <N>}`, **and** si le code est ≠ 200, le script auto-recovery est déclenché

## 3. Pipeline d'analyse (9 étapes)

| Étape | ID | Module | Entrée | Sortie | Dépendance sources |
|---|---|---|---|---|---|
| 1 | PIP-001 | Profil entreprise | Ticker | CompanyProfile | yfinance |
| 2 | PIP-002 | Collecte données | Ticker, profile | FinancialData | yfinance + Finnhub + EDGAR |
| 3 | PIP-003 | Transcripts earnings | Ticker | Transcript[] | Seeking Alpha + Tavily |
| 4 | PIP-004 | Dépôts SEC | Ticker | SECFilings | EDGAR (edgartools) |
| 5 | PIP-005 | Analyse management | Transcript[] | ManagementTone | LLM local/externe |
| 6 | PIP-006 | Scoring (40 pts) | FinancialData + ManagementTone + Risques | Scoring | Calcul déterministe |
| 7 | PIP-007 | Synthèse LLM | Toutes données | DeepDiveReport | DeepSeek / GPT |
| 8 | PIP-008 | Génération PDF | DeepDiveReport | PDF (10–14 pages) | ReportLab |
| 9 | PIP-009 | Archivage | PDF + sources | ZIP + analyses/ | Disque local |

## 4. Schémas de données

### 4.1 Scoring (40 points)

```
Scoring {
    total: int ∈ [0, 40]
    financial_health: int ∈ [0, 10]   // Dette, liquidité, cash flow
    growth: int ∈ [0, 10]             // Croissance CA, BNA
    valuation: int ∈ [0, 8]           // PER, PEG, P/B, EV/EBITDA
    management: int ∈ [0, 5]          // Tone analysis, insider trades
    moat: int ∈ [0, 4]                // Marge, part de marché
    sentiment: int ∈ [0, 3]           // News, analystes
    recommendation: enum["BUY", "HOLD", "SELL"]
    summary: str (≤ 300 caractères)
}
```

**Seuils :** BUY si total ≥ 28, HOLD si 18–27, SELL si < 18. **INSUFFISANT** si < 3 sources valides (données insuffisantes — pas de recommandation, cf. BR-002).

### 4.2 AnalysisResult

```
AnalysisResult {
    ticker: str (1–5 caractères, uppercase)
    timestamp: datetime (ISO 8601)
    status: enum["running", "completed", "error"]
    score: Scoring | null
    company_profile: dict
    financial_data: FinancialData
    management_tone: ManagementTone | null
    risks: RiskItem[] (≤ 20)
    valuation: ValuationData
    sources: Source[] (≥ 1, idéalement ≥ 5 ; scoring désactivé si < 3 — cf. BR-002)
    pdf_path: str | null
    dossier_path: str | null
}
```

### 4.3 FinancialData

```
FinancialData {
    ticker: str
    market_cap: float | null          // en USD
    revenue: float | null             // TTM, en USD
    net_income: float | null
    eps: float | null
    pe_ratio: float | null
    peg_ratio: float | null
    debt_to_equity: float | null
    current_ratio: float | null
    free_cash_flow: float | null
    dividend_yield: float | null
    revenue_growth_yoy: float | null  // %
    gross_margin: float | null        // %
    operating_margin: float | null
}
```

### 4.4 Source

```
Source {
    type: enum["yfinance", "finnhub", "edgar", "seeking_alpha", "tavily", "alpha_vantage", "web"]
    name: str
    url: str | null
    retrieved_at: datetime
    status: enum["success", "partial", "failed"]
    data_points: int
}
```

### 4.5 DeepDiveReport

```
DeepDiveReport {
    ticker: str
    quarter: str                     // "2025-Q3"
    generated_at: datetime
    sections: Section[]
    metadata: {model: str, tokens: int, cost_usd: float}
}

Section {
    title: str
    content: str                     // Markdown converti en PDF
    sources: str[]                   // Références aux sources
    confidence: enum["high", "medium", "low"]
}
```

### 4.6 Feedback

```
Feedback {
    id: str (UUID v4)
    ticker: str
    timestamp: datetime
    message: str (≤ 2000 caractères)
    correction_type: enum["score", "data", "missing", "other"]
    processed: bool
    applied_at: datetime | null
}
```

## 5. Règles de gestion

| ID | Règle | Condition déclenchante | Comportement attendu | Testable |
|---|---|---|---|---|
| BR-001 | Pas d'invention de données | Source API retourne null/erreur | Afficher « DONNÉE NON DISPONIBLE » dans le PDF | ✅ |
| BR-002 | Score minimum 3 sources | < 3 sources valides après collecte | Score = null, recommandation = « INSUFFISANT », ne pas générer de PDF complet | ✅ |
| BR-003 | PDF 5 sections obligatoires | Génération PDF | Sections : Synthèse, Scoring, Finances, Management, Risques | ✅ |
| BR-004 | Archivage obligatoire | Analyse terminée (completed) | Sauvegarder dans analyses/{ticker}_{timestamp}/ | ✅ |
| BR-005 | Feedback avant réanalyse | Feedback non traité existe | Réanalyse uniquement après application du feedback | ✅ |
| BR-006 | Rate limit cascade | API retourne 429 | Exponential backoff (1s, 2s, 4s, 8s), max 3 retries, puis skip source | ✅ |
| BR-007 | Timeout source externe | > 30s sans réponse | Abandonner la source, logger l'erreur, continuer avec les autres | ✅ |
| BR-008 | CSV batch max 10 tickers | Batch upload | Rejeter si > 10 tickers avec message d'erreur | ✅ |
| BR-009 | Cache invalidation | Cache > 1h ou refresh forcé | Invalider et re-collecter | ✅ |

## 6. Exigences non fonctionnelles

| ID | Catégorie | Exigence | Cible | Mesure |
|---|---|---|---|---|
| NFR-001 | Performance | Analyse complète | < 5 min | Chrono pipeline |
| NFR-002 | Performance | Affichage PDF | < 2 s | Latence HTTP |
| NFR-003 | Disponibilité | API health | 99 % uptime | Health check cron (15 min) |
| NFR-004 | Sécurité | Auth write endpoints | X-API-Key obligatoire | 401 si absent |
| NFR-005 | Fiabilité | Données manquantes | Pas d'invention | Audit visuel PDF |
| NFR-006 | Observabilité | Logs structurés | Tous endpoints + pipeline | JSON logs avec timestamp |
| NFR-007 | Résilience | Rate limit APIs | Retry/backoff automatique | BR-006 |
| NFR-008 | Maintenabilité | Couverture de tests | ≥ 60 % pipeline | pytest --cov |
| NFR-009 | Sécurité | Secrets | .env uniquement, .gitignore | Scan pre-commit |

## 7. Observabilité et audit

### 7.1 Événements de log

| Événement | Niveau | Champs | Trigger |
|---|---|---|---|
| pipeline.start | INFO | ticker, timestamp | Début analyse |
| pipeline.step | INFO | ticker, step (1–9), duration_ms | Fin de chaque étape |
| pipeline.complete | INFO | ticker, total_ms, score, sources_count | Analyse terminée |
| pipeline.error | ERROR | ticker, step, error_type, message | Erreur étape |
| source.fetch | DEBUG | source_type, ticker, duration_ms, status | Après chaque appel API |
| source.rate_limit | WARN | source_type, retry_after_ms | API retourne 429 |
| pdf.render | INFO | ticker, pages, size_kb, duration_ms | PDF généré |
| api.request | INFO | method, path, status_code, duration_ms | Chaque requête HTTP |

### 7.2 Métriques exposées

| Métrique | Endpoint | Type |
|---|---|---|
| Uptime secondes | /api/health | HealthResponse |
| Nombre sources par ticker | /api/traceability/{ticker} | JSON |
| Statut batch job | /api/batch/{job_id}/status | JSON |
| Recherches récentes | /api/admin/recent-searches | JSON |
| Stats recherche | /api/admin/search-stats | JSON |

## 8. Politique de confidentialité

Le pipeline utilise des LLM externes pour la synthèse narrative (étape 7). Les données transmises sont des données financières publiques (ticker, chiffres trimestriels, transcripts publics).

| ID | Principe | Implémentation |
|---|---|---|
| PR-001 | Données transmises au LLM | Uniquement données publiques (chiffres SEC, transcript publics, prix de marché) |
| PR-002 | Pas de PII | Aucune donnée personnelle dans les prompts LLM |
| PR-003 | Secrets API | Stockés dans .env, jamais transmis aux LLM |
| PR-004 | Logs | Ne contiennent pas les prompts LLM complets (uniquement résumé) |
| PR-005 | Cache local | Stocké dans backend/cache/, effaçable sans impact fonctionnel |
| PR-006 | Réversibilité | Toute analyse peut être regénérée (données sources conservées dans analyses/) |
| PR-007 | Consentement | Usage personnel uniquement, pas de partage de données avec des tiers au-delà du pipeline |

## 9. Rétention et restauration

### 9.1 Rétention des analyses

| Artefact | Emplacement | Rétention |
|---|---|---|
| Analyse JSON | analyses/{ticker}_{timestamp}/ | Illimitée (disque local) |
| PDF deep-dive | analyses/{ticker}_{timestamp}/ | Illimitée |
| ZIP dossier complet | analyses/{ticker}_{timestamp}/ | Illimitée |
| Cache financier | backend/cache/ | Volatil (invalidé sur refresh) |
| Logs | backend/logs/ | Rotation manuelle |

### 9.2 Modes de défaillance et restauration

| Mode de défaillance | Symptôme | Procédure de récupération | Délai cible |
|---|---|---|---|
| Tunnel CF down | HTTP 530/1033 | `systemctl --user restart cloudflared-tunnel` | < 2 min |
| Backend down | Connection refused :8780 | `cd backend && PYTHONPATH=.. uvicorn main:app --host 0.0.0.0 --port 8780` | < 5 min |
| API source rate limit | 429 sur yfinance/Finnhub | Automatique : backoff exponentiel, max 3 retries | < 30 s |
| API source down | Timeout 30 s | Skip source, continuer avec ≥ 3 sources | Automatique |
| Build frontend manquant | 404 sur fichiers JS/CSS | `cd frontend && npm run build` | < 2 min |
| Double prefix CF | /stock-analysis/stock-analysis/ JS 404 | Accéder via https://sa.cedlabusa.net/ (pas /stock-analysis/) | Immédiat |
| Port 8780 occupé | Address already in use | `lsof -i :8780` → `kill <PID>` | < 1 min |
| Mémoire WSL saturée | OOM kill par Windows | `wsl --shutdown` + redémarrer le backend | < 3 min |
| Crash pipeline | Erreur 500, état inconsistent | Supprimer l'analyse partielle, relancer | — |

### 9.3 Vérification post-restauration

```bash
# 1. Backend health
curl -s -w "%{http_code}" https://sa.cedlabusa.net/api/health

# 2. Frontend reachable
browser_navigate → https://sa.cedlabusa.net

# 3. Analyse test
saisir "AAPL" → lancer analyse → vérifier PDF + ZIP
```

## 10. Contraintes

| ID | Contrainte | Type | Impact |
|---|---|---|---|
| C-001 | yfinance rate limit (~5 req/s informel) | Technique | Délai entre tickers batch |
| C-002 | Finnhub free tier (60 req/min) | Source | Limitation collecte news/earnings |
| C-003 | Alpha Vantage free tier (25 req/jour) | Source | Transcripts limités |
| C-004 | Tavily API (1000 req/mois) | Source | IR enrichment limité |
| C-005 | Cloudflare Tunnel exposition | Sécurité | Auth via X-API-Key obligatoire pour writes |
| C-006 | WSL2 backend uniquement | Déploiement | Pas de containerisation, pas de scaling horizontal |
| C-007 | React buildé en bundle JS | Frontend | Cache-busting obligatoire (CacheBustingStaticFiles) |
| C-008 | Seeking Alpha HTML scraping | Source | Fragile, dépend de la structure HTML |

## 11. Risques et décisions

### 11.1 Risques identifiés

| ID | Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|---|
| RSK-001 | API Seeking Alpha bloque le scraping | Moyenne | Transcripts indisponibles | Fallback Alpha Vantage + Tavily |
| RSK-002 | yfinance change l'API | Faible | Données fondamentales HS | Finnhub + EDGAR en fallback |
| RSK-003 | Double bookkeeping financier | Faible (fixé 2026-05-14) | Score erroné | Commit 3cf8f9b : sync EDGAR → financials ET fin |
| RSK-004 | Quick tunnel au lieu de named tunnel | Faible | Domaine instable | Auto-recovery détecte quick tunnel |
| RSK-005 | Indentation bug PDF renderer | Faible (fixé 2026-05-15) | PDF vide | Commit af2b3df : helpers BEFORE render function |
| RSK-006 | Mémoire WSL insuffisante | Moyenne (> 3 batch) | OOM kill | Batch max 10 tickers, clean after each |

### 11.2 Décisions d'architecture (renvoi aux ADR)

- ADR-001 : Stack Python/FastAPI + React/Vite + ReportLab + Cloudflare Tunnel
- ADR-002 : Scoring rules-based (40 pts, 6 catégories) plutôt que ML

## 12. Critères d'acceptation globaux

| ID | Critère | Méthode | Seuil |
|---|---|---|---|
| GA-001 | Analyse NVDA complète | Chronomètre | < 5 min |
| GA-002 | PDF ≥ 10 pages, émojis ◆🧠●👉⚠️ visibles | Audit visuel | 100% des pages |
| GA-003 | ZIP contient PDF + analysis.json + sources.json | Extraction manuelle | 3 fichiers min |
| GA-004 | API health retourne 200 | curl -s -w "%{http_code}" | 200 |
| GA-005 | Tests pipeline passent | pytest tests/ -v | 0 échec |
| GA-006 | Aucune donnée inventée | Audit sources vs PDF | 0 invention |
| GA-007 | Frontend accessible | browser_navigate | Page load < 5 s |
| GA-008 | Feedback enregistré | POST /api/feedback → GET /api/admin/feedback | Message horodaté présent |
| GA-009 | Erreur ticker invalide | Saisir ZZZZYX | Message erreur < 30 s |
| GA-010 | Rate limit géré | Simuler 429 yfinance | Retry automatique, skip après 3 |

## 13. Glossaire

| Terme | Définition |
|---|---|
| Ticker | Symbole boursier (ex: AAPL, NVDA, MSFT) — 1 à 5 caractères, uppercase |
| Deep-dive | Analyse narrative enrichie générée par LLM à partir des données collectées |
| Scoring | Note sur 40 points répartis en 6 catégories, déterminant la recommandation BUY/HOLD/SELL |
| EDGAR | Electronic Data Gathering, Analysis, and Retrieval — base de dépôts SEC |
| Callout box | Encadré coloré dans le PDF mettant en valeur une information clé |
| Quick tunnel | Tunnel Cloudflare éphémère sans nom de domaine stable (debug) |
| Named tunnel | Tunnel Cloudflare permanent avec nom de domaine configuré (production) |
|| CacheBustingStaticFiles | Classe FastAPI qui ajoute Cache-Control: no-cache aux fichiers statiques |

## 14. V2.7 — Sections PDF Structurées

### 14.1 Contexte
Les PDF earnings deep-dive actuels utilisent des sections textuelles générées par LLM, sans structuration fine des données financières. La V2.7 introduit 6 modèles Pydantic structurés, chacun responsable d'une section du PDF avec des données typées, sourcées et traçables.

### 14.2 Modèles de données (T1)
| # | Modèle | Contenu | Statut |
|---|---|---|---|
| 1 | `ExecutiveSnapshot` | ticker, prix, market cap, verdict, score | ✅ Intégré |
| 2 | `FinancialMetrics` (V2.7) | EPS, Revenue, marges, croissance, FCF + display | ✅ Intégré |
| 3 | `ValuationSection` | PE trailing/forward, PEG, PS, PB, EV/EBITDA | ✅ Intégré |
| 4 | `ValuationContextSection` | 7 signaux contextuels V2.4 | ✅ Intégré (T4) |
| 5 | `PeerBenchmarkSection` | Benchmarks relatifs aux pairs V2.5 | ✅ Intégré (T5) |
| 6 | `DataQualitySection` | Fraîcheur des sources, complétude | ✅ Intégré (T6) |

### 14.3 Rendu PDF (T2)
Fonctions de rendu dans `pdf_renderer.py` :
- `render_executive_snapshot()` — carte d'en-tête avec prix, market cap, verdict
- `render_financial_metrics()` — tableaux EPS, Revenue, marges, croissance, FCF
- `render_valuation()` — multiples de valorisation
- `render_valuation_context()` — signaux contextuels (pending data)
- `render_peer_benchmark()` — comparaison pairs (pending data)
- `render_data_quality()` — audit trail des sources (pending data)

Chaque renderer retourne `[]` si le modèle est `None` — aucun breaking change.

### 14.4 Intégration Pipeline (T3)
Le mapper (`backend/earnings_deep_dive/mapper.py`) peuple les modèles V2.7 :
- **ExecutiveSnapshot** : depuis `company_overview` (market cap, secteur) + `scoring` (verdict)
- **FinancialMetrics** : mapping direct depuis l'ancien `schemas.FinancialMetrics`
- **ValuationSection** : PE trailing/forward depuis yfinance
- **ValuationContextSection (T4)** : 7 signaux via `get_valuation_context_snapshot()` — PEG, P/S vs growth, EV/EBITDA vs growth, P/FCF vs growth, FCF Yield + résumé
- **PeerBenchmarkSection (T5)** : via `get_peer_benchmark_snapshot()` (cache 5 min) + `buildPeerBenchmarkSummary()` — top 5 pairs par similarité
- **DataQualitySection (T6)** : source freshness depuis la bibliographie (`sources`), completeness score (0-100), champs manquants, confidence tier (high/medium/low)

### 14.5 Tests
- `tests/spec_v27_report_model.py` — 25 tests (modèles Pydantic)
- `tests/spec_v27_pdf_renderer.py` — 36 tests (rendu PDF)
- `tests/spec_v27_integration.py` — 13 tests (mapper → pipeline → PDF)
- `tests/test_v27_valuation_context.py` — 17 tests (T4, ValuationContext)
- `tests/test_v27_peer_benchmark.py` — 33 tests (T5, PeerBenchmark)
- `tests/test_v27_data_quality.py` — 23 tests (T6, DataQuality)

### 14.6 État actuel
- ✅ T1 : Modèles Pydantic (6 modèles, tous nullable, USD-only)
- ✅ T2 : Fonctions de rendu PDF (6 renderers, aucun breaking change)
- ✅ T3 : Intégration mapper → pipeline (3/6 modèles peuplés)
- ✅ T4 : ValuationContext — 7 signaux depuis endpoint V2.4
- ✅ T5 : PeerBenchmark — top 5 pairs depuis infrastructure V2.5
- ✅ T6 : DataQuality — source freshness, completeness score, confidence tier

## 15. Correctif qualité API — 2026-05-27

- `/api/analyze/async` reste rétrocompatible avec les clients historiques qui envoient `{ "ticker": "NVDA" }`; le contrat canonique reste `{ "tickers": ["NVDA"] }`.
- Les tests FastAPI en processus reconnaissent l'hôte synthétique `testclient` pour éviter les faux 403/rate-limit en environnement de test uniquement.
- `/api/health` et `/api/version` bornent les appels Git à 5 secondes pour éviter qu'un probe bloqué rende l'API indisponible.
- Vérification associée : `backend/tests` + tests API ciblés = 192 tests passés; build frontend Vite production passé.

## 16. Correctif saisie ticker — rate limit parser — 2026-05-27

- Symptôme utilisateur : après saisie d'un ticker, aucun bouton d'analyse n'apparaît et l'interface semble ne rien faire.
- Cause racine : le parser de saisie appelle `/api/batch/upload` après debounce. Le rate limiter comptait toutes les requêtes d'une même IP dans un seul compteur ; des chargements page/assets pouvaient donc épuiser le quota plus strict d'un endpoint d'écriture et retourner `429` au parser.
- Correction backend : les compteurs de rate limit sont séparés par `(IP, tier)` et `/api/batch/upload` est classé dans le tier léger `default` car utilisé pendant la saisie.
- Correction frontend : en cas d'échec temporaire du parser live, `TickerInput` affiche un avertissement visible et utilise un fallback local pour tickers/ISINs simples au lieu d'échouer silencieusement.
- Vérification associée : test de non-régression `test_page_loads_do_not_rate_limit_ticker_parser`, suite backend/API ciblée `193 passed`, build frontend Vite production passé.

## 17. Admin feedback + accès Seeking Alpha — durcissement et preuve prod — 2026-05-28

### 17.1 Backfill historique GOOG
- Deux entrées historiques ont été injectées dans le store canonique `feedback_GOOG` à partir du texte WhatsApp fourni par le métier :
  - `2026-05-28_043100` — demande sur les documents P1/P5/P7/P9
  - `2026-05-28_052100` — demande "Company Overview" / investor perspective
- Chaque entrée référence une pièce jointe PDF dédiée :
  - `2026-05-28_043100_deep_dive_GOOG.pdf`
  - `2026-05-28_052100_deep_dive_GOOG.pdf`
- Les entrées sont visibles via `GET /api/admin/feedback` sur la prod et gardent le format canonique (`id`, `ticker`, `submitted_at`, `text`, `files`, `processed`).

### 17.2 Route de téléchargement des pièces jointes feedback
- La route `GET /api/feedback-file/{ticker}/{filename}` sert les pièces jointes stockées dans le répertoire canonique d'analyses.
- Vérification prod : les deux PDFs GOOG ci-dessus répondent HTTP 200 avec `Content-Type: application/pdf` et `Content-Length: 372344`.

### 17.3 Accès Seeking Alpha côté serveur
- L'admin dispose de deux endpoints dédiés :
  - `GET /api/admin/seeking-alpha/access` — état de configuration (`configured`, `cookie_count`, `server_side_only`, dates)
  - `POST /api/admin/seeking-alpha/test` — test live de connectivité transcript sur un ticker
- Le stockage serveur des cookies Seeking Alpha est durci :
  - dossier parent créé avec permission stricte (`0700`, best-effort)
  - écriture atomique via fichier temporaire puis rename
  - fichier final en permission stricte (`0600`, best-effort)
  - `.state/` ignoré par git pour éviter toute fuite accidentelle
- Contrat sécurité : l'API ne renvoie jamais le `cookie_header` brut au frontend.

### 17.4 Vérifications exécutées
- Tests ciblés : `PYTHONPATH=/home/ced/codex-projects/stock-analysis-pipeline .venv/bin/pytest tests/test_seeking_alpha_access.py tests/test_feedback.py` → **21 passed**
- Restart backend prod : uvicorn PID `311265`, start time `2026-05-28 13:11:37`, listener `0.0.0.0:8780`
- Recette navigateur prod :
  - `https://sa.cedlabusa.net/stock-analysis/` → page d'accueil OK, 0 erreur JS
  - `https://sa.cedlabusa.net/stock-analysis/#admin` → panneau "Seeking Alpha Access" visible, table de recherches peuplée, 0 erreur JS
- Vérification live des endpoints admin SA :
  - `GET /api/admin/seeking-alpha/access` → HTTP 200, `configured=false`, `server_side_only=true`
  - `POST /api/admin/seeking-alpha/test` → HTTP 200, `ok=false`, `reason=no_cookies_configured` (endpoint joignable, cookies non chargés)
- Vérification métier connexe : la table admin montre l'unique consultation GOOG avec user-agent Mac à `28/05, 04:04:58`.

## 18. Hard gate complétude données (peer/valuation/history/PDF) — 2026-05-28

### 18.1 Metrics history : suppression des trimestres vides
- Endpoint concerné : `GET /api/metrics-history/{ticker}` (`backend/main.py`).
- Correctif :
  - backfill de la date de trimestre depuis cash-flow/balance-sheet quand la ligne income statement est absente ;
  - suppression des lignes où **toutes** les métriques sont `None` (évite les faux trimestres vides) ;
  - exposition explicite `dropped_empty_quarters` + `dropped_count` pour auditabilité.
- Non-régression : `backend/tests/test_metrics_history_endpoint.py` (2 tests) :
  - drop des quarters 100% vides ;
  - conservation des quarters partiels avec date valide.

### 18.2 Placeholder normalization PDF
- Fichiers :
  - `backend/earnings_deep_dive/pdf_renderer.py`
  - `backend/earnings_deep_dive/mapper.py`
- Correctif :
  - remplacement des placeholders `N/A` par `Not available` dans les notes/source rows ;
  - normalisation cellule tableau `N/A` → `Not available` ;
  - wording narratif aligné (`Not available or Not disclosed`, sans token `N/A`).
- Non-régression : `tests/test_pdf_commentary.py::test_pdf_replaces_na_placeholders_with_not_available`.

### 18.3 Vérifications exécutées
- Suite ciblée :
  - `PYTHONPATH=/home/ced/codex-projects/stock-analysis-pipeline/backend .venv/bin/python -m pytest backend/tests/test_metrics_history_endpoint.py backend/tests/test_peer_universe.py backend/tests/test_valuation_endpoint.py backend/tests/test_peer_benchmark_api.py backend/tests/test_peer_batch.py tests/test_pdf_commentary.py -q`
  - Résultat : **57 passed**.
- Audit API local 7 tickers (`NVDA,AAPL,MSFT,GOOG,TSLA,AMZN,META`) :
  - champs valuation critiques complets (`price, market_cap, enterprise_value, pe_current, pe_forward, peg_ratio, eps_growth, revenue_growth, total_debt`) ;
  - peer benchmark `status=available` avec `sample_size > 0` ;
  - `metrics-history` sans lignes entièrement vides.
- Audit production same-origin via navigateur (`sa.cedlabusa.net`) : mêmes résultats sur les 7 tickers.
- PDF GOOG régénéré : `analyses/2026-05-28_230657_GOOG_Alphabet_Inc./07_final_report/earnings_deep_dive.pdf`
  - occurrences `null/undefined/NaN/N/A` : **0** ;
  - fallback restant : `Not available` explicite (cas réellement indisponibles).

## 19. §3 Report Period Consistency — 2026-05-29

### 19.1 ReportPeriodContext model
- Nouveau modèle Pydantic `ReportPeriodContext` dans `report_model.py` — source unique de vérité pour toutes les périodes du rapport.
- Champs : `ticker`, `company_name`, `fiscal_year`, `fiscal_quarter`, `calendar_period`, `earnings_release_date`, `transcript_period`, `press_release_period`, `filing_period`, `guidance_period`, `comparison_prior_year_period`, `report_title_period_label`, `display_period_label`, `generated_at`.
- Propriété `is_valid` : True ssi `fiscal_year`, `fiscal_quarter` et `report_title_period_label` sont renseignés.
- Ajouté comme champ optionnel `period_context` dans `EarningsDeepDiveReport`.

### 19.2 Builder et parsing
- `_build_report_period_context()` dans `mapper.py` : construit le contexte à partir du `resolved_quarter` et des métriques.
- `_parse_fiscal_quarter()` : parse `"FY2026 Q1"`, `"2026Q1"`, `"Q1 2026"` → `(fiscal_year, fiscal_quarter)`.
- Intégré dans `build_earnings_deep_dive_report()` — le contexte est transmis au modèle de rapport.

### 19.3 SA_REPORT_PERIOD_CONSISTENCY_GATE (RULE 11)
- Ajouté dans `pre_render_validator.py` — règle bloquante (error severity).
- 5 sous-règles :
  - **11a** : Titre doit matcher la période de filing SEC.
  - **11b** : Guidance doit être forward-looking (strictement après la période courante).
  - **11c** : Transcript doit matcher la période de filing.
  - **11d** : Press release doit matcher la période de filing.
  - **11e** : Période de comparaison prior-year = même quarter, année fiscale - 1.
- `_try_parse_quarter()` : parse tolérant aux formats, retourne `(None, None)` sur entrée non parseable.
- `period_context=None` → gate no-op (rétrocompatibilité).

### 19.4 Pipeline wiring
- Le pipeline (`pipeline.py`) construit un `_LightPeriodContext` minimal pour le validateur à partir du `transcript_quarter`.
- Le contexte complet (`ReportPeriodContext`) est construit dans le mapper.

### 19.5 Tests
- `tests/spec_v27_period_consistency.py` — **31 tests** :
  - 4 tests modèle (création, validation, intégration report)
  - 8 tests parsing (7 formats valides, 6 formats invalides, cross-check)
  - 3 tests builder (résolution, quarter différent, métriques enrichies)
  - 8 tests gate (all-matching, 5 mismatch rules, no-context skip, unparseable)
- Non-régression : `pytest tests/spec_v27_*.py tests/test_v27_*.py` → **195 passed**.

## 20. §10 Highlights/Lowlights Quality Gate — 2026-05-29

### 20.1 RULE 12 — Highlights/Lowlights quality
- Ajouté dans `pre_render_validator.py` — règle bloquante (error severity).
- 4 sous-règles :
  - **12a** — Empty bullets : lignes avec juste un marqueur et pas de contenu → ❌
  - **12b** — Duplicates : 70%+ overlap entre deux highlights → ❌
  - **12c** — "No major red flags" paradox : claim contredit par ≥2 risques listés → ❌
  - **12d** — Unsubstantiated : ≥2 highlights sans chiffre ni source → ❌

### 20.2 Prompt hardening
- Prompt EN Highlights renforcé avec STRUCTURE REQUIREMENTS explicites (claim + number + source + implication, pas de empty bullets, pas de duplicates).

### 20.3 Tests
- `tests/spec_v27_highlights_quality.py` — **17 tests** :
  - 4 empty bullets, 4 duplicates, 3 red-flags paradox, 4 unsubstantiated, 2 integration
- Non-régression : `pytest tests/spec_v27_*.py tests/test_v27_*.py` → **212 passed**.
