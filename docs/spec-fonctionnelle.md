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
| CacheBustingStaticFiles | Classe FastAPI qui ajoute Cache-Control: no-cache aux fichiers statiques |
