# Revue de code complète — Rapport d'audit qualité professionnelle
**Projet** : Stock Analysis Pipeline  
**Date** : 2026-05-05  
**Périmètre** : Backend (22 fichiers Python, ~6 100 lignes) + Frontend (11 fichiers JSX/JS, ~1 950 lignes)  
**Tests** : 28 tests (model, scoring, endpoints, dossier), 100% passants  
**Auditeur** : Hermes (skills : security-tester + agentic-engineering-review)

---

## 1. Synthèse exécutive

| Métrique | Valeur |
|----------|--------|
| **Note globale** | **5.8/10** (↑ 0.6 depuis audit 2026-05-04) |
| **Niveau de maturité** | **MVP → Pré-production** (en transition) |
| **Verdict** | ⚠️ Pas encore prêt pour usage sérieux. Progrès significatif sur i18n + logging + sécurité, mais lacunes P0/P1 bloquantes. |
| **Tests** | 28/28 ✅ — couverture limitée aux modèles et scorer, pas de test endpoint complet |
| **Sécurité** | 🟡 Correct — pas de secrets dans le code, .env gitignoré, mais CORS wildcard + debug endpoint exposé |
| **i18n** | ✅ EN/JA complet — labels UI + backend. ⚠️ Traductions de surface, pas de fallback structuré |

### Top 10 risques

1. **🔴 P0** — `os.environ.setdefault()` = stale env vars Hermes → clés incorrectes injectées
2. **🔴 P1** — Debug endpoint `/api/debug/yf-cache/{ticker}` exposé sans protection
3. **🔴 P1** — CORS `allow_origins=["*"]` en production
4. **🟠 P1** — `_ticker_exists()` désactivé → accepte n'importe quel ticker jusqu'à l'échec API
5. **🟠 P1** — `_score_management_realtime` en français hardcodé — casse l'i18n
6. **🟠 P2** — Code dupliqué `analyze_ticker` vs `analyze_ticker_fast` — divergence garantie
7. **🟡 P2** — `GEMINI_API = "http://127.0.0.1:7863"` hardcodé — casse au changement réseau
8. **🟡 P2** — `_batch_jobs` en mémoire volatile — perdu au restart Render
9. **🟡 P2** — `getConvictionLevel()` ne comprend que l'anglais — JA cassé
10. **🟢 P3** — Aucun rate limiting sur `/api/analyze` — abus possible

---

## 2. Cartographie du projet

### Modules backend (22 fichiers)

| Module | Responsabilité | Lignes | Qualité |
|--------|---------------|--------|---------|
| `main.py` | 16 endpoints FastAPI, parsing tickers, upload, cache | 964 | 🟡 — trop de responsabilités |
| `pipeline.py` | Analyse complète + fast-path + dossier | 1 193 | 🟠 — duplication avec async_dossier |
| `async_dossier.py` | Génération dossier background + status | 387 | ✅ Bien structuré |
| `sources_collector.py` | Yahoo Finance + Finnhub + TwelveData + cache | 836 | 🟡 — fusion de providers |
| `scorer.py` | 8 critères × 5 points = /40 | 210 | ✅ Clair, testé |
| `models.py` | 14 modèles Pydantic | 153 | ✅ Propre |
| `orchestrator.py` | Dispatch analyse (seq + stub parallel) | 75 | 🟡 — parallèle non fonctionnel |
| `translator.py` | Kimi K2.6 via NVIDIA | 175 | ✅ Robuste (retry×6, timeout 180s) |
| `i18n.py` | Labels EN/JA backend | 95 | ✅ Complet |
| `logging_config.py` | Logging structuré + redaction secrets | 206 | ✅ Excellent |
| `kimi_provider.py` | Analyse management + risques via Kimi | ~100 | Non audité en détail |
| `market_context.py` | Contexte marché Finnhub + Gemini | ~50 | 🟡 IP hardcodée |
| `pdf_generator.py` | MD→PDF via weasyprint | ~80 | ✅ Fonctionnel |
| Autres (9 fichiers) | Profil, Excel, 8-K, 10-K PDF, transcripts... | ~900 | ✅ Spécialisés |

### Modules frontend (11 fichiers)

| Fichier | Responsabilité | Lignes | Qualité |
|---------|---------------|--------|---------|
| `App.jsx` | Routing, état global, i18n, language persistence | 205 | ✅ Clean |
| `AnalysisCard.jsx` | Carte résultat + dossier polling + scoring chart | 255 | ✅ Bon |
| `TickerInput.jsx` | Input tickers avec parsing/validation | 197 | ✅ UX soignée |
| `BatchAnalysis.jsx` | Upload CSV + batch | ~150 | Non audité |
| `ScoringChart.jsx` | SVG bar chart scoring | ~180 | Fonctionnel |
| `SmartLoader.jsx` | Loader animé + progression | 101 | ✅ |
| `i18n.js` | Traductions EN/JA | 161 | ✅ Complet |
| `api.js` | Client API + helpers | 106 | ✅ |
| `LanguageSelector.jsx` | Dropdown drapeaux EN/JA | ~40 | ✅ |
| `ReportView.jsx` | Vue rapport détaillé | ~100 | Non audité |
| `AboutSection.jsx` | Section "Comment ça marche" | ~40 | ✅ |

### Flux critiques

```
User → TickerInput → App.handleAnalyze → api.analyzeTickers(lang)
  → POST /api/analyze?lang=ja
  → orchestrator.run_analysis_sequential → pipeline.analyze_ticker_fast
  → sources_collector.get_stock_data (cache → YF → Finnhub → TwelveData)
  → scorer.score_ticker → AnalysisResult
  → i18n.translate(decision/conviction, lang)
  → JSONResponse → App → AnalysisCard (polling dossier)
  → GET /api/dossier/{ticker}/download?lang=ja
  → translator.translate_text (Kimi K2.6)
  → PDF génération → ZIP → download
```

### Zones sensibles

- **Cache disque** (`backend/.cache/`) : données financières persistées, pas dans Git ✅
- **Secrets** : `.env` (FINNHUB, DEEPSEEK, DOSSIER_UPLOAD_SECRET) — gitignoré ✅
- **Upload endpoint** : protégé par `X-Upload-Secret` header ✅
- **Debug endpoints** : `/api/debug/yf-cache` NON protégé 🔴 — `/api/debug/sources` protégé ✅
- **Thread background** : `async_dossier.py` — daemon thread, OK pour Render

---

## 3. Tableau des findings prioritaires

| ID | Sévérité | Catégorie | Fichier / Zone | Problème | Impact | Recommandation |
|----|----------|-----------|----------------|----------|--------|----------------|
| F01 | 🔴 P0 | Sécurité | `backend/main.py:50` | `os.environ.setdefault()` — stale env vars Hermes | Clés incorrectes injectées silencieusement | `os.environ[k] = v` |
| F02 | 🔴 P1 | Sécurité | `backend/main.py:453-483` | `/api/debug/yf-cache/{ticker}` sans protection | Expose données cache + structure interne | Ajouter `ENVIRONMENT` check comme `/api/debug/sources` |
| F03 | 🔴 P1 | Sécurité | `backend/main.py:56` | `allow_origins=["*"]` | CORS ouvert — tout site peut appeler l'API | Lister origines explicites (Vercel + localhost) |
| F04 | 🟠 P1 | Validation | `backend/main.py:124-130` | `_ticker_exists()` toujours True | Accepte tickers invalides, échec silencieux à l'analyse | Réactiver validation YF avec cache + timeout 3s |
| F05 | 🟠 P1 | i18n | `backend/scorer.py:108-109` | `_score_management_realtime` hardcode français ("optimiste", "confiant") | Scoring management cassé si Kimi répond en anglais | Utiliser des patterns anglais ou une liste multilingue |
| F06 | 🟠 P1 | Qualité | `backend/pipeline.py:26-1193` + `804-1193` | Code dupliqué entre `analyze_ticker` et `analyze_ticker_fast` | Divergence garantie, maintenance doublée | Extraire steps communs dans des fonctions partagées |
| F07 | 🟡 P2 | Config | `backend/market_context.py:10` | `GEMINI_API = "http://127.0.0.1:7863"` hardcodé | Casse au changement réseau/IP | Mettre dans `.env` + fallback |
| F08 | 🟡 P2 | Architecture | `backend/main.py:64` | `_batch_jobs = {}` en mémoire | Perdu au restart Render | Persister dans `batches/` JSON |
| F09 | 🟡 P2 | i18n | `frontend/src/components/AnalysisCard.jsx:18-24` | `getConvictionLevel()` match seulement "high"/"strong"/"low" | JA: `高い` non reconnu → toujours "Moderate" | Utiliser les valeurs de `i18n.js` ou le score backend |
| F10 | 🟡 P2 | Architecture | `backend/orchestrator.py:45-75` | `run_analysis_parallel` = stub, retourne erreur | Parallélisation impossible | Implémenter avec `delegate_task` ou supprimer |
| F11 | 🟢 P3 | i18n | `backend/pipeline.py:195,873,900-902` + `scorer.py:920` | `DONNÉE NON DISPONIBLE` en français | Mix FR/EN dans projet anglais | Remplacer par "DATA NOT AVAILABLE" |
| F12 | 🟢 P3 | Qualité | `backend/pipeline.py:23` | `__import__("datetime")` comme fallback timezone | Anti-pattern fragile | `from zoneinfo import ZoneInfo; PARIS = ZoneInfo("Europe/Paris")` |
| F13 | 🟢 P3 | Performance | `backend/main.py` | Pas de rate limiting sur `/api/analyze` | Abus possible (appels Finnhub + YF coûteux) | `slowapi` ou middleware rate limit |
| F14 | 🟢 P3 | i18n | `frontend/src/components/AnalysisCard.jsx:26-38` | `getInsight()` retourne toujours en anglais | JA: insights en anglais malgré `?lang=ja` | Traduire les insights via `t()` |
| F15 | 🟢 P3 | Tests | `tests/` | 28 tests — pas de test d'intégration endpoint complet, pas de test translator, pas de test concurrent | Régressions possibles sur endpoints complexes | Ajouter tests d'intégration + edge cases réseau |
| F16 | 🟢 P3 | Dépendances | `requirements.txt` | Dépendances datées (cryptography 41→48, antlr 4.9→4.13) | Vulnérabilités potentielles | `pip-audit` + mise à jour |
| F17 | 🟢 P3 | Observabilité | `backend/main.py:696` | Pas de log des headers/langue/timing sur `/api/analyze` | Diagnostic lent | Ajouter durée + lang dans le log |
| F18 | 🟢 P3 | Frontend | `frontend/src/i18n.js` | Pas de namespace ni fallback structuré | Nouveaux composants = risque clés manquantes | Wrapper `t()` avec warning console en dev |

---

## 4. Analyse détaillée par domaine

### 4.1 Architecture générale

**Ce qui est solide :**
- Séparation claire backend (FastAPI) / frontend (React+Vite)
- Modèles Pydantic bien typés, validation d'entrée cohérente
- Pattern async dossier : fast analysis (<5s) → background génération → polling status → download
- Stratégie multi-source (Yahoo Finance → Finnhub → TwelveData) avec fallback
- Cache disque avec merge YF/API (double cache)

**Ce qui est faible :**
- `main.py` (964 lignes) est un god file : 16 endpoints + parsing + validation + upload + cache — à splitter
- `analyze_ticker` et `analyze_ticker_fast` partagent ~900 lignes de logique dupliquée → divergence garantie
- `run_analysis_parallel` est un stub non fonctionnel
- `_batch_jobs` dict en mémoire — perdu au restart
- Architecture "fast then background" a créé deux chemins de code (pipeline + async_dossier) qui font la même chose

### 4.2 Sécurité

| Check | Résultat |
|-------|----------|
| Secrets dans le code | ✅ Aucun — toutes les clés dans `.env` |
| `.env` dans `.gitignore` | ✅ Ligne 2 |
| Secrets dans Git | ✅ Aucun trouvé dans l'historique |
| CORS | 🔴 `allow_origins=["*"]` (ligne 56) |
| Debug endpoints | 🔴 `/api/debug/yf-cache` non protégé (ligne 453) |
| Upload auth | ✅ `X-Upload-Secret` header (ligne 636) |
| Input validation | 🟡 Format ticker OK, mais `_ticker_exists()` désactivé |
| File upload safety | ✅ `os.path.basename()` sanitization (ligne 652) |
| `.cache/` gitignoré | ✅ Ligne 42 du `.gitignore` |
| Dependency audit | 🟡 30+ packages outdated |

**Détail F01** (P0) : `os.environ.setdefault()` est documenté comme dangereux dans la mémoire Hermes — les variables d'env d'une session précédente survivent et écrasent les nouvelles. Ligne 50 : `os.environ.setdefault(k.strip(), v.strip())` → doit être `os.environ[k.strip()] = v.strip()`.

**Détail F02** (P1) : `/api/debug/yf-cache/{ticker}` retourne le contenu du cache YF sans aucune protection. N'importe qui peut voir les données financières en cache. Le fix est trivial : ajouter le même guard `ENVIRONMENT != development → 403` que `/api/debug/sources` (ligne 490).

### 4.3 Robustesse et gestion d'erreurs

**Ce qui est solide :**
- `translator.py` : 6 tentatives (3 SDK + 3 HTTP), exponential backoff, timeout 180s, temp 0.0 ✅
- `sources_collector.py` : fallback Finnhub → Yahoo Finance → TwelveData
- Dossier generation : chaque étape dans un try/except individuel

**Ce qui est faible :**
- 85 `except Exception` dans le backend — beaucoup silencieux (`pass` ou simple `logger.warning`)
- `_ticker_exists()` désactivé → l'utilisateur découvre l'échec seulement après 20s d'analyse
- Pas de circuit breaker sur les APIs externes (Finnhub 429 → toutes les requêtes échouent)
- Render free tier : le thread background est tué si idle — pas de retry automatique

### 4.4 Concurrence

- `_dossier_registry` protégé par `threading.Lock()` ✅
- `_batch_jobs` dict **non protégé** — race condition possible si deux requêtes batch simultanées
- Thread daemon pour dossier background — OK pour Render (pas de vraie concurrence)
- Pas de mécanisme pour empêcher deux analyses simultanées du même ticker

### 4.5 Performance

| Point | Évaluation |
|-------|-----------|
| Cache disque | ✅ Double cache (YF + main) avec merge |
| Timeouts | ✅ Finnhub 10s, YF 10s, Kimi 180s |
| Heavy work off main thread | ✅ Dossier génération en thread daemon |
| Rate limiting | ❌ Aucun |
| N+1 queries | 🟡 Batch analysis fait N appels séquentiels — pas de batching YF |
| Payload size | ✅ `financials`/`valuation`/`segments`/`management_tone` popés avant réponse |
| Frontend | ✅ Polling 5s, countdown, skeleton cards |

### 4.6 Qualité du code

**Forces :**
- `logging_config.py` est excellent — SecretRedactingFormatter + ContextInjectingFormatter + LogContext
- `translator.py` est robuste — chunking paragraphes, double fallback (SDK + HTTP)
- `scorer.py` est clair et bien testé
- `async_dossier.py` bien structuré avec cache discipline (never return "generating" from cache)

**Faiblesses :**
- `main.py` est un god file (964 lignes, 16 endpoints)
- Duplication majeure `analyze_ticker` ↔ `analyze_ticker_fast`
- `PARIS = timezone(offset=datetime.now(timezone.utc).astimezone().utcoffset() or __import__("datetime").timedelta(hours=2))` — utiliser `ZoneInfo("Europe/Paris")`
- `DONNÉE NON DISPONIBLE` en français dans 4+ fichiers

### 4.7 Tests

**28 tests, 100% passants :**
- 17 tests modèles (Pydantic validation, décisions, scoring)
- 5 tests scorer (NVDA-like, MSFT-like, retailer, edge cases)
- 3 tests endpoints (list analyses, dossier download, requirements)
- 2 tests seeking_alpha
- 1 test async_dossier

**Lacunes :**
- ❌ Aucun test d'intégration complet (POST /api/analyze → vérifier réponse)
- ❌ Aucun test du translator (Kimi K2.6)
- ❌ Aucun test des endpoints debug
- ❌ Aucun test de concurrence (batch jobs)
- ❌ Aucun test avec mock réseau (YF down, Finnhub 429)
- ❌ Aucun test du frontend

### 4.8 Observabilité

**Forces :**
- `logging_config.py` — structured logging avec job_id/ticker context, rotation 5×5MB, redaction secrets
- Debug endpoint `/api/debug/sources` (protégé) pour vérifier config

**Faiblesses :**
- Pas de log de durée sur `/api/analyze`
- Pas de métriques (nombre d'appels, latence p95, taux d'erreur)
- Pas d'alerting
- Logs Render: `logs/pipeline.log` disparaît au restart

### 4.9 i18n

**Forces :**
- Double couche : `frontend/src/i18n.js` (UI) + `backend/i18n.py` (API labels)
- `?lang=ja` propagé dans tous les endpoints
- Language persistence via `localStorage`
- Traduction documents via Kimi K2.6 avec retry

**Faiblesses :**
- `getConvictionLevel()` (frontend) ne reconnaît que l'anglais → JA cassé
- `getInsight()` (frontend) retourne toujours en anglais
- `_score_management_realtime` (backend) hardcode du français
- Pas de namespace ou fallback structuré dans `t()`
- `DONNÉE NON DISPONIBLE` en français (back+front)

---

## 5. Corrections recommandées par priorité

### 🔴 P0 — Critique

| Action | Fichiers | Pourquoi | Effort |
|--------|----------|----------|--------|
| `os.environ.setdefault` → `os.environ[k] = v` | `backend/main.py:50` | Stale env vars Hermes = clés incorrectes | 1 ligne |

### 🔴 P1 — Important

| Action | Fichiers | Pourquoi | Effort |
|--------|----------|----------|--------|
| Protéger `/api/debug/yf-cache` | `backend/main.py:453` | Ajouter `ENVIRONMENT` check | 3 lignes |
| Restreindre CORS origins | `backend/main.py:56` | `["https://stock-analysis-pipeline.vercel.app", "http://localhost:5173"]` | 1 ligne |
| Réactiver `_ticker_exists` | `backend/main.py:124` | Validation YF avec cache + timeout 3s | 30 lignes |
| Corriger `_score_management_realtime` | `backend/scorer.py:108-109` | Remplacer FR par patterns EN multilingues | 5 lignes |

### 🟠 P2 — Medium

| Action | Fichiers | Pourquoi | Effort |
|--------|----------|----------|--------|
| Extraire code commun pipeline | `backend/pipeline.py` | Factoriser `analyze_ticker` + `analyze_ticker_fast` | 2h |
| `GEMINI_API` → `.env` | `backend/market_context.py:10` | Config externe | 5 lignes |
| Persister `_batch_jobs` | `backend/main.py:64` | JSON dans `batches/` | 30 lignes |
| Fix `getConvictionLevel` JA | `AnalysisCard.jsx:18-24` | Utiliser les valeurs i18n | 10 lignes |

### 🟡 P3 — Mineur

| Action | Fichiers | Effort |
|--------|----------|--------|
| `DONNÉE NON DISPONIBLE` → `DATA NOT AVAILABLE` | 4 fichiers backend | 10 lignes |
| `PARIS` → `ZoneInfo("Europe/Paris")` | `pipeline.py:23` | 2 lignes |
| Ajouter rate limiting | `backend/main.py` | `slowapi` middleware, 30min |
| `getInsight()` i18n | `AnalysisCard.jsx:26-38` | 15 lignes |
| Ajouter log durée `/api/analyze` | `backend/main.py:696` | 3 lignes |
| Ajouter tests intégration + mock réseau | `tests/` | 2-4h |
| Mise à jour dépendances | `requirements.txt` | `pip-audit` + upgrade |

---

## 6. Roadmap de professionnalisation

### Phase 1 : Sécurisation (cette semaine — 2h)

- [x] `.env` dans `.gitignore` ✅
- [x] Upload auth ✅
- [x] Logging sans secrets ✅
- [ ] F01 : Fix `os.environ.setdefault` (1 ligne)
- [ ] F02 : Protéger `/api/debug/yf-cache` (3 lignes)
- [ ] F03 : Restreindre CORS (1 ligne)
- [ ] F04 : Réactiver `_ticker_exists` (30 lignes)
- [ ] F05 : Fix scorer i18n (5 lignes)

### Phase 2 : Qualité et tests (2-3 jours)

- [ ] Split `main.py` en route modules
- [ ] Factoriser `analyze_ticker` / `analyze_ticker_fast`
- [ ] Ajouter tests intégration endpoint
- [ ] Ajouter tests mock réseau
- [ ] Rate limiting
- [ ] Fix i18n gaps (getConvictionLevel, getInsight, DONNÉE NON DISPONIBLE)

### Phase 3 : Industrialisation (1-2 semaines)

- [ ] Métriques + alerting
- [ ] Circuit breaker APIs externes
- [ ] `_batch_jobs` persistent
- [ ] `run_analysis_parallel` fonctionnel
- [ ] Mise à jour dépendances + `pip-audit` en CI
- [ ] Tests frontend (Vitest + Testing Library)

---

## 7. Checklist qualité finale

- [ ] **Sécurité** : CORS restreint, debug endpoints protégés, setdefault fixé
- [ ] **i18n** : Plus de français hardcodé, getConvictionLevel multilingue, getInsight traduit
- [ ] **Code** : Plus de god file main.py, plus de duplication pipeline
- [ ] **Tests** : Tests intégration endpoint, mock réseau, edge cases
- [ ] **Perf** : Rate limiting, pas de N+1 évitable, cache discipline
- [ ] **Observabilité** : Log durée, métriques basiques
- [ ] **Config** : Pas d'IP hardcodée, .env chargé correctement

---

## 8. Conclusion

### Ce qui est solide
- **Logging** : `logging_config.py` est un modèle du genre — redaction secrets, context injection, rotation
- **Translator** : 6 tentatives, double fallback, chunking — robuste
- **i18n double couche** : UI + API labels bien séparés, `?lang=ja` propagé partout
- **Cache discipline** : Double cache YF/main, merge, jamais de "generating" retourné
- **Tests scorer** : 4 scénarios réels (NVDA, MSFT, retailer, edge case)

### Ce qui est insuffisant
- **Duplication pipeline** : `analyze_ticker` et `analyze_ticker_fast` sont un bug en attente
- **Validation ticker** : désactivée → expérience utilisateur dégradée
- **Debug endpoint** : exposé sans protection
- **Tests intégration** : 0 — on ne sait pas si l'API fonctionne de bout en bout sans déploiement

### Les 5 actions prioritaires (à faire aujourd'hui)

1. **`os.environ.setdefault` → `os.environ[k] = v`** (1 ligne, P0)
2. **Protéger `/api/debug/yf-cache`** (3 lignes, P1)
3. **Restreindre CORS aux origines explicites** (1 ligne, P1)
4. **Fix `_score_management_realtime`** — remplacer français par anglais (5 lignes, P1)
5. **Réactiver `_ticker_exists`** avec cache + timeout 3s (30 lignes, P1)

---

*Rapport généré le 2026-05-05 par audit Hermes — skills security-tester + agentic-engineering-review.*
*Prochaine revue recommandée : après déploiement Phase 1.*
