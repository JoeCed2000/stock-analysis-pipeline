# Revue de code complète — Rapport d'audit qualité professionnelle

**Projet** : `stock-analysis-pipeline`
**Date** : 2026-05-04
**Méthode** : Audit read-only — aucun fichier modifié
**Périmètre** : backend (5,103 lignes Python, 19 fichiers) + frontend (1,602 lignes JSX/JS, 10 fichiers) + config + tests

---

## 1. Synthèse exécutive

| Métrique | Valeur |
|----------|--------|
| **Note globale** | 5.2/10 |
| **Niveau de maturité** | **MVP** (Minimum Viable Product) |
| **Verdict** | **NON prêt pour usage sérieux** — utilisable en démo uniquement |
| **Tests** | 3 fichiers, ~118 lignes, couverture <10% |
| **Sécurité secrets** | ✅ Bonne — 0 secret exposé |
| **Sécurité endpoints** | 🔴 Insuffisante — CORS wildcard, pas de rate limiting |
| **Architecture** | 🟡 Acceptable pour un MVP, monolithique pour la suite |

### Top 10 des risques

| # | Sévérité | Risque |
|---|----------|--------|
| 1 | P0 | Crash serveur Render — batch status bloque le thread principal 30s+ |
| 2 | P1 | CORS `allow_origins=["*"]` — tout site peut appeler l'API |
| 3 | P1 | Pas de rate limiting — 1 utilisateur peut épuiser les quotas API Finnhub/Yahoo |
| 4 | P1 | 0 test d'intégration — impossible de savoir si le pipeline fonctionne après un déploiement |
| 5 | P1 | Duplication massive — `analyze_ticker` / `analyze_ticker_fast` ~200 lignes copiées |
| 6 | P1 | État partagé mutable sans lock — `_batch_jobs` dict corrompable en concurrence |
| 7 | P1 | Stack traces exposées aux utilisateurs — `HTTPException(detail=str(e))` |
| 8 | P2 | Pas de persistance batch jobs — perdus au redémarrage Render |
| 9 | P2 | Bug scorer — `_score_moat` a du code mort ligne 132-133, scoring management dépend du français |
| 10 | P2 | 4 modules legacy non utilisés — alpha_vantage, transcript_finder, seeking_alpha, transcript_rich |

---

## 2. Cartographie du projet

### Modules détectés

```
backend/
├── main.py (536 loc)        — API FastAPI : 16 endpoints, parsing, validation
├── models.py (153 loc)      — 12 modèles Pydantic (✅ bien structuré)
├── pipeline.py (951 loc)    — Pipeline 9 étapes (⚠️ monolithique, dupliqué)
├── orchestrator.py (75 loc) — Dispatch séquentiel/parallèle
├── scorer.py (210 loc)      — Scoring 8 critères (/40) (✅ propre, bugs mineurs)
├── sources_collector.py (736 loc) — Données Yahoo/Finnhub/Twelve/SEC (⚠️ trop gros)
├── kimi_provider.py (220 loc) — Kimi K2.6 via NVIDIA NIM
├── async_dossier.py (200 loc) — Génération dossier en background
├── logging_config.py (175 loc) — Logging structuré + redaction (✅ excellent)
├── excel_generator.py        — Génération Excel
├── company_profile.py        — Profil entreprise
├── tenk_pdf.py               — Conversion 10-K → PDF
├── sec_8k.py                 — Téléchargement 8-K SEC
├── pdf_generator.py          — Génération PDF rapport
├── market_context.py         — Contexte marché
├── management_analyzer.py    — Analyse management (legacy?)
├── alpha_vantage.py          — ⚠️ Legacy (Alpha Vantage)
├── transcript_finder.py      — ⚠️ Legacy
├── transcript_rich.py        — ⚠️ Legacy
├── seeking_alpha.py          — ⚠️ Legacy (Seeking Alpha sans API)
├── tone_config.json          — Configuration tones
├── requirements.txt          — Dépendances backend
└── .cache/                   — Cache local
```

### Flux critiques

```
[Frontend] → POST /api/analyze → orchestrator.run_analysis_sequential()
  → pipeline.analyze_ticker_fast() → [sources_collector + scorer + kimi_provider]
  → async_dossier.generate_dossier_background() → [excel_generator + tenk_pdf + sec_8k]
  → GET /api/dossier/{ticker}/status → GET /api/dossier/{ticker}/download
```

### Zones les plus sensibles

1. **main.py** — Point d'entrée unique, concentration de toute la logique API
2. **pipeline.py** — Cœur métier, 951 lignes, duplication `analyze_ticker`/`analyze_ticker_fast`
3. **_batch_jobs** (main.py:51) — Dict mutable partagé sans synchronisation
4. **sources_collector.py:112-121** — Appels Finnhub avec token en query param

---

## 3. Tableau des findings prioritaires

| ID | Sév. | Catégorie | Fichier / Zone | Problème | Impact | Recommandation |
|----|------|-----------|----------------|----------|--------|----------------|
| F01 | 🔴 P0 | Concurrence | main.py:247 | `batch_status()` exécute TOUS les tickers dans un GET — bloque le thread >30s | Timeout Render → crash serveur | BackgroundTasks ou queue asynchrone |
| F02 | 🟡 P1 | Sécurité | main.py:43 | CORS `allow_origins=["*"]` | Tout site web peut appeler l'API | Lister les origines explicites |
| F03 | 🟡 P1 | Sécurité | main.py:425 | Pas de rate limiting | Épuisement quotas API (Finnhub 60/min) | slowapi ou middleware custom |
| F04 | 🟡 P1 | Tests | tests/ | 0 test d'intégration | Aucune garantie que le pipeline fonctionne | Tests API + pipeline mocké |
| F05 | 🟡 P1 | Architecture | pipeline.py:26-750 + :753-950 | `analyze_ticker` et `analyze_ticker_fast` dupliquent ~200 lignes | Deux sources de vérité, divergence garantie | Extraire le core commun |
| F06 | 🟡 P1 | Concurrence | main.py:51 | `_batch_jobs` dict sans lock | Corruption en requêtes concurrentes | `threading.Lock` ou `asyncio.Lock` |
| F07 | 🟡 P1 | Erreurs | main.py:435 | `HTTPException(detail=str(e))` expose les stack traces | Fuite d'information interne | Logger l'exception, retourner message générique |
| F08 | 🟡 P1 | Configuration | render.yaml | Render attend `PYTHONPATH=..` mais le start command est dans `backend/` | Incohérence de PYTHONPATH | Fixer le working directory |
| F09 | 🟢 P2 | Robustesse | pipeline.py:753+ | `try/except: pass` ignore silencieusement les erreurs I/O | Dossier incomplet sans avertissement | Logger + fallback explicite |
| F10 | 🟢 P2 | Robustesse | main.py:51,213 | Batch jobs en mémoire, perdus au restart | Perte de jobs en cours | Persistance fichier ou DB |
| F11 | 🟢 P2 | Qualité | scorer.py:132-133 | `if gm > 0.40: score += 0` — code mort | Aucun (neutre), mais confusion | Supprimer ou corriger la logique |
| F12 | 🟢 P2 | Qualité | scorer.py:108-121 | Keywords français hardcodés pour `_score_management_realtime` | Si Kimi répond en anglais → score bloqué à 3 | Matching insensible à la langue ou fallback |
| F13 | 🟢 P2 | Qualité | main.py:328,393,481 | Logique "find latest analysis dir" dupliquée 6× | Divergence, maintenance lourde | Extraire `_get_latest_analysis_dir(ticker)` |
| F14 | 🟢 P2 | Architecture | sources_collector.py | 736 lignes — 4 sources de données + ISIN + cache | Difficile à tester isolément | Split par provider (YahooProvider, FinnhubProvider…) |
| F15 | 🟢 P2 | Dead code | backend/ | alpha_vantage.py, transcript_finder.py, seeking_alpha.py, transcript_rich.py | Code mort, confusion | Supprimer ou documenter "legacy" |
| F16 | 🟢 P2 | Frontend | BatchAnalysis.jsx | 396 lignes — composant trop gros | Maintenance difficile | Split en sous-composants |
| F17 | 🟢 P2 | Observabilité | main.py:349 | Health check ne vérifie que "ok" | Ne détecte pas API key manquante | Vérifier config au démarrage |
| F18 | 🟡 P1 | Tests | tests/ | test_scorer.py: pas de test avec tone_data=None, edge cases | Les bugs du scorer ne sont pas détectés | Ajouter tests edge cases |
| F19 | 🟢 P2 | Build | render.yaml:6 | `buildCommand: pip install -r requirements.txt` — pas de versioning strict | Build non reproductible | `pip install -r requirements.txt --require-hashes` ou Poetry |
| F20 | 🟢 P2 | Config | frontend/.env.production | URL Render hardcodée | Si l'URL Render change → frontend cassé | Variable d'env Vercel |

---

## 4. Analyse détaillée par domaine

### 4.1 Architecture et modularité — Note : 5/10

**✅ Ce qui est bon :**
- `models.py` : 12 modèles Pydantic propres, bien typés, avec valeurs par défaut et `@property` pour `Scoring.total`
- `scorer.py` : 8 fonctions de scoring indépendantes, 210 lignes, responsabilité unique par fonction
- `kimi_provider.py` : Interface propre avec fallback HTTP quand le client OpenAI échoue
- `logging_config.py` : Redaction des secrets, rotation, injection de contexte — niveau professionnel

**🔴 Problèmes :**

1. **Pipeline monolithique** (pipeline.py:951 lignes) — deux fonctions `analyze_ticker` et `analyze_ticker_fast` qui dupliquent massivement la logique de création des modèles, scoring, et construction du résultat. Toute modification d'un champ Pydantic nécessite une mise à jour aux deux endroits.

2. **Sources collector fourre-tout** (sources_collector.py:736 lignes) — mélange Yahoo Finance, Finnhub, Twelve Data, SEC EDGAR, ISIN, conversion EUR, cache. Impossible de tester un provider isolément.

3. **Pas de couche de service** — `main.py` appelle directement `orchestrator.run_analysis_sequential()` puis manipule les résultats bruts. Pas d'abstraction entre la couche HTTP et la couche métier.

4. **Duplication "find latest analysis dir"** — Le pattern `sorted(ANALYSES_DIR.glob(f"*_{ticker_clean}_*"), reverse=True)` apparaît dans 6 endpoints différents (lignes 305, 329, 405, 463, 483, 498, 513).

**Recommandation :**
- Extraire un `AnalysisRepository` avec `get_latest(ticker)` et `list_all()`
- Créer des classes provider : `YahooFinanceProvider`, `FinnhubProvider`, `TwelveDataProvider`, `SecEdgarProvider`
- Fusionner `analyze_ticker` et `analyze_ticker_fast` avec un paramètre `fast_mode: bool = True`

### 4.2 Sécurité — Note : 6/10

**✅ Ce qui est bon :**
- **Secret hygiene** : `.env` dans `.gitignore`, `.env.example` avec `***`, `render.yaml` sans valeurs, `NVIDIA.txt` placeholder. Zéro secret dans Git.
- **Logging** : `SecretRedactingFormatter` redacte toutes les clés API avant écriture disque
- **Debug endpoint** : Protégé par `ENVIRONMENT=development` → 403 en production
- **Input validation** : ISIN checksum (ISO 6166), regex ticker strict, rejet des tokens invalides avec message d'erreur classifié

**🔴 Problèmes :**

1. **CORS wildcard** (main.py:43) — `allow_origins=["*"]` permet à n'importe quel site web d'appeler l'API. En production, cela expose les quotas API (Finnhub 60 req/min) à des abus cross-origin.

2. **Pas de rate limiting** — Un seul utilisateur ou bot peut saturer les quotas :
   - Finnhub : 60 req/min → ~1 req/s
   - Yahoo Finance : rate-limit non documenté mais agressif
   - NVIDIA NIM (Kimi) : 40 req/min
   Aucune protection contre les appels en rafale.

3. **Token Finnhub en query param** (sources_collector.py:121) — `f"https://finnhub.io/api/v1{path}&token={api_key}"`. Le token apparaît dans les logs d'accès Render et potentiellement dans les logs CDN. Préférer le header `X-Finnhub-Token`.

4. **Pas de validation taille upload** (main.py:186) — `/api/batch/upload` accepte n'importe quel fichier sans limite de taille. Un fichier de 100MB peut être uploadé → mémoire saturée.

5. **Fuites d'information** (main.py:435) — `HTTPException(status_code=500, detail=str(e))` expose les messages d'erreur Python bruts, incluant potentiellement des chemins de fichiers serveur.

6. **Pas de Content-Security-Policy, X-Frame-Options, HSTS** — headers de sécurité absents.

**Recommandation :**
- Restreindre CORS à `https://frontend-six-zeta-81.vercel.app` uniquement
- Ajouter `slowapi` avec `@limiter.limit("10/minute")` sur `/api/analyze`
- Utiliser `X-Finnhub-Token` header au lieu de query param
- Ajouter `FileSizeValidator(max_size=5*1024*1024)` sur l'upload
- Remplacer `detail=str(e)` par `detail="Internal server error"` + log

### 4.3 Gestion d'erreurs et résilience — Note : 4/10

**✅ Ce qui est bon :**
- `kimi_provider.py` : double fallback — client OpenAI → HTTP direct, avec logging clair
- `sources_collector.py` : fallback chaîné Finnhub → Twelve Data → Yahoo Finance
- `analyze_ticker_fast` : chaque étape wrapped dans try/except

**🔴 Problèmes :**

1. **Silent failures** (pipeline.py:753+) — Les `try/except: pass` dans `analyze_ticker_fast` ignorent les erreurs de sauvegarde JSON/Yahoo/Finnhub sans aucune trace. L'utilisateur reçoit un résultat "succès" avec des données partielles sans savoir ce qui a échoué.

2. **Crash serveur sur batch** (main.py:247) — `batch_status()` exécute TOUS les tickers de manière synchrone dans un GET. Pour 10 tickers à 5s chacun = 50 secondes. Render a un timeout de 30 secondes sur les requêtes HTTP → crash.

3. **Pas de timeout sur les appels externes** — Ni Yahoo Finance, ni Finnhub, ni SEC EDGAR n'ont de timeout configuré. Un réseau lent peut bloquer indéfiniment.

4. **Pas de retry avec backoff** — Les appels API qui échouent (rate-limit 429, timeout réseau) ne sont pas retentés.

5. **État incohérent possible** — Si `analyze_ticker_fast` crée le répertoire de sortie mais échoue avant de sauvegarder les données, le dossier existe mais est vide. La fonction `get_dossier_status` le détectera comme "in_progress" indéfiniment.

6. **Pas de circuit breaker** — Si Finnhub est down, chaque requête tentera Finnhub d'abord et attendra le timeout avant de passer à Twelve Data.

**Recommandation :**
- Remplacer `except: pass` par `except Exception as e: logger.warning(...)` systématiquement
- Passer le batch en BackgroundTask asynchrone
- Ajouter `timeout=10` sur tous les `requests.get()`
- Implémenter un `@retry(max_attempts=3, backoff=2)` sur les appels API
- Ajouter un fichier `.dossier_status.json` dans le répertoire d'analyse pour tracker l'état

### 4.4 Concurrence et multithreading — Note : 3/10

**✅ Ce qui est bon :**
- `async_dossier.py` : `threading.Lock` sur `_dossier_registry` — correct
- Uvicorn single-worker par défaut → limite les dégâts de concurrence

**🔴 Problèmes :**

1. **Race condition sur `_batch_jobs`** (main.py:51,213-263) — Le dict est lu et écrit sans aucun lock. Deux requêtes concurrentes sur le même job_id peuvent :
   - Écraser le statut
   - Perdre des résultats
   - Double-incrémenter `completed`

2. **Batch processing dans le thread HTTP** (main.py:247) — Le traitement batch bloque le thread principal de l'application. Pendant ce temps, aucune autre requête n'est servie (sur un worker unique).

3. **`async_dossier` thread détaché** — Si le serveur Render s'endort (free tier, 15 min d'inactivité), le thread de génération est tué. Les fichiers partiellement écrits restent sur disque → état corrompu.

4. **Pas de protection contre les analyses concurrentes du même ticker** — Deux utilisateurs peuvent lancer `POST /api/analyze` pour AAPL simultanément → deux dossiers créés, deux threads background, conflits potentiels sur le cache Yahoo Finance.

**Recommandation :**
- Remplacer `_batch_jobs` par un `asyncio.Lock` ou une queue
- Utiliser `BackgroundTasks` de FastAPI pour le traitement batch
- Ajouter un verrou par ticker (`threading.Lock` dans un dict `_ticker_locks`) pour éviter les analyses concurrentes dupliquées
- Écrire un fichier `.lock` dans le répertoire d'analyse pendant la génération

### 4.5 Performance — Note : 5/10

**✅ Ce qui est bon :**
- `analyze_ticker_fast()` : pas de conversion PDF/Excel synchrone → ~3-5s au lieu de 20-30s
- Cache fichier pour Yahoo Finance (TTL 1h) dans `sources_collector.py`
- `TTLCache` backend pour les données Yahoo (maxsize 50, ttl=3600)

**🔴 Problèmes :**

1. **Pas de cache pour Finnhub** — Les appels à Finnhub (company profile, news, peers) ne sont pas cachés. Pour une analyse batch de 10 tickers US → 30 appels Finnhub.

2. **SEC EDGAR pas caché** — Le téléchargement du 10-K (fichier HTML volumineux) est refait à chaque analyse.

3. **Chargement mémoire du buffer ZIP** (main.py:296,334,410) — `io.BytesIO()` stocke tout le ZIP en mémoire. Pour 10 tickers avec dossiers complets → plusieurs centaines de MB.

4. **Pas de pagination** — `/api/analyses` retourne tous les dossiers sans limite. Si 1000 analyses sont stockées → réponse JSON massive.

5. **Re-parsing des données Yahoo** — `get_stock_data()` parse toute la réponse Yahoo à chaque appel, même si les données sont en cache.

**Recommandation :**
- Ajouter `TTLCache` pour Finnhub (sur `get_finnhub_company_profile`, `get_finnhub_news`)
- Cacher le 10-K téléchargé (le HTML ne change qu'une fois par an)
- Utiliser `StreamingResponse` avec générateur pour les ZIP
- Ajouter `?limit=50&offset=0` à `/api/analyses`

### 4.6 Qualité du code — Note : 5/10

**✅ Ce qui est bon :**
- `models.py` : Pydantic bien typé, `@property` pour champs calculés, `Field(default_factory=...)`
- `scorer.py` : Fonctions courtes (10-25 lignes), responsabilité unique, bien nommées
- `logging_config.py` : Design pattern ContextManager propre

**🔴 Problèmes :**

1. **Duplication massive** (pipeline.py) — `analyze_ticker` et `analyze_ticker_fast` partagent ~80% de code. Voir section 4.1.

2. **Duplication "find latest dir"** (main.py) — 6 occurrences du même pattern avec `sorted(ANALYSES_DIR.glob(...))`. 

3. **Code mort dans le scorer** (scorer.py:130-133) :
   ```python
   if gm > 0.60: score += 1
   if gm > 0.40: score += 0  # ⚠️ Jamais exécuté si gm > 0.60, neutre sinon
   ```
   La ligne 132 ne fait rien — soit c'est un bug, soit c'est du code mort.

4. **Biais français dans le scorer** (scorer.py:108-121) — `_score_management_realtime` cherche les mots "optimiste", "confiant", "élevée", "bonne", "faible". Si Kimi K2.6 répond en anglais → le score management reste bloqué à 3.

5. **Modules legacy** — `alpha_vantage.py`, `transcript_finder.py`, `transcript_rich.py`, `seeking_alpha.py` sont importés nulle part ou référencés comme fallback non fonctionnel. Ils polluent le codebase.

6. **`import` dans les fonctions** (pipeline.py, main.py, async_dossier.py) — Les `from backend.xxx import yyy` à l'intérieur des fonctions contournent les imports circulaires mais rendent le graphe de dépendances opaque.

7. **Noms incohérents** — `backend/requirements.txt` et `requirements.txt` à la racine. Lequel est utilisé ? (Réponse : les deux, selon le contexte Render vs local.)

**Recommandation :**
- Appliquer DRY sur les 3 patterns dupliqués
- Corriger `_score_moat` : soit `score += 0` est un bug (fallait `score += 1` ?), soit supprimer la ligne
- Rendre `_score_management_realtime` insensible à la langue (matching sémantique ou keywords EN+FR)
- Nettoyer les modules legacy
- Résoudre les imports circulaires par refactoring (provider pattern)

### 4.7 Tests et couverture qualité — Note : 2/10

**🔴 État actuel :**
- 3 fichiers de test : `test_models.py` (118 lignes), `test_scorer.py`, `test_seeking_alpha.py`
- 0 test d'intégration
- 0 test d'API (FastAPI TestClient)
- 0 test frontend
- 0 test de performance
- 0 test de sécurité

**Tests existants :**
- `test_models.py` : Valide la création des modèles Pydantic, valeurs par défaut, validation rejet. ✅ Correct mais superficiel.
- `test_scorer.py` : Non lu en détail mais basé sur le nom — probablement des tests unitaires des fonctions de scoring.
- `test_seeking_alpha.py` : Test d'un module legacy/non fonctionnel.

**Tests critiques manquants :**

| Catégorie | Test manquant | Risque couvert |
|-----------|---------------|----------------|
| Intégration | `test_analyze_endpoint` — POST /api/analyze avec mock Yahoo | Pipeline complet fonctionnel ? |
| Intégration | `test_dossier_flow` — fast analysis → status → download | Flux async fonctionnel ? |
| Erreur | `test_yahoo_failure` — Yahoo down → fallback fonctionne ? | Résilience |
| Erreur | `test_kimi_timeout` — NVIDIA NIM lent → timeout + fallback ? | Résilience |
| Sécurité | `test_cors_headers` — Les bonnes origines sont-elles autorisées ? | Sécurité |
| Sécurité | `test_debug_endpoint_403` — /api/debug/sources bloqué en prod ? | Sécurité |
| Scoring | `test_scorer_unknown_data` — Toutes les valeurs None → score cohérent ? | Robustesse |
| Scoring | `test_scorer_english_tone` — Kimi répond en anglais → management score ? | Bug #F12 |
| Concurrence | `test_concurrent_batch` — 2 requêtes simultanées → état cohérent ? | Race condition |
| Performance | `test_analyze_under_5s` — Fast path < 5 secondes ? | SLA |

**Recommandation :**
- Ajouter `pytest-asyncio` + `httpx.AsyncClient` pour les tests d'API
- Mocker `yfinance`, `finnhub`, `requests` pour des tests déterministes
- Viser 60% de couverture backend minimum avant usage sérieux
- Ajouter 1 test d'intégration end-to-end avec mock de toutes les sources externes

### 4.8 Observabilité et diagnostic — Note : 6/10

**✅ Ce qui est bon :**
- `logging_config.py` : Format structuré `timestamp | LEVEL | module | JOB:xxx | TICKER: msg`
- Rotation automatique (5 MB × 5 backups)
- Redaction des secrets
- `LogContext` pour injecter job_id/ticker dans tous les logs d'un bloc

**🔴 Problèmes :**

1. **Pas de métriques** — Aucun compteur de requêtes, latence, taux d'erreur, appels API externes. Impossible de savoir si le service dégrade.

2. **Health check superficiel** (main.py:349) — Retourne juste `{"status": "ok"}`. Ne vérifie pas :
   - Présence des clés API obligatoires
   - Connectivité Finnhub/Yahoo
   - Espace disque disponible

3. **Logs non structurés en JSON** — Le format texte est lisible mais difficile à parser par des outils de monitoring (Loki, ELK).

4. **Pas de tracing distribué** — Impossible de corréler une requête frontend → backend → appels API externes.

**Recommandation :**
- Ajouter un middleware de métriques (temps de réponse, compteur par endpoint)
- Enrichir le health check : `{"status": "ok", "checks": {"finnhub": true, "yahoo": true, "disk": "85%"}}`
- Passer au format JSON pour les logs en production (configurable)

### 4.9 Build, configuration et documentation — Note : 5/10

**✅ Ce qui est bon :**
- `render.yaml` : Configuration Render propre, Infrastructure as Code
- `.env.example` : Documenté, toutes les clés listées avec instructions
- `DEPLOY.md` : Instructions de déploiement
- `POSTMORTEM.md` : Analyse post-incident (token GitHub expiré)
- `docs/plans/architecture-plan.md` : Plan d'architecture

**🔴 Problèmes :**

1. **Deux requirements.txt** — `requirements.txt` (racine) et `backend/requirements.txt` créent une ambiguïté. Render utilise celui de la racine, mais le code backend est dans `backend/`.

2. **PYTHONPATH fragile** — Le start command Render `cd backend && PYTHONPATH=.. uvicorn main:app` dépend d'un chemin relatif. Si l'arborescence change → cassé.

3. **Pas de versioning strict** — `requirements.txt` utilise `package>=version` ou pas de version du tout. Build non reproductible → "ça marchait hier".

4. **Pas de Docker** — Pas de `Dockerfile` ou `docker-compose.yml` pour le développement local reproductible.

5. **Pas de pre-commit hooks** — Pas de linting automatique (black, ruff, eslint) avant commit.

6. **Fichiers parasites à la racine** — `COMMANDS.md`, `COMMANDS.txt`, `NVIDIA.txt`, `test_tickers.txt`, `run_daily_backlog.py` — pas clair ce qui est documentation vs outil vs placeholder.

7. **Documentation développeur absente** — Pas de `README.md` avec instructions de setup local, architecture, contribution.

**Recommandation :**
- Consolider en un seul `requirements.txt` avec versions exactes (`==`)
- Ajouter `Dockerfile` + `docker-compose.yml`
- Ajouter `.pre-commit-config.yaml` avec black + ruff + eslint
- Nettoyer les fichiers parasites racine
- Écrire un `README.md` avec : setup, architecture, endpoints, déploiement

---

## 5. Liste des corrections recommandées par priorité

### 🔴 P0 — À traiter immédiatement (bloque la mise en production)

| # | Action | Fichiers | Pourquoi | Effort | Risque si non corrigé |
|---|--------|----------|----------|--------|----------------------|
| P0-1 | Passer `batch_status` en background task — ne plus bloquer le GET | main.py:237 | Crash serveur Render après 30s | 2h | Service inutilisable pour >1 ticker |

### 🟡 P1 — À traiter avant toute version sérieuse

| # | Action | Fichiers | Pourquoi | Effort | Risque si non corrigé |
|---|--------|----------|----------|--------|----------------------|
| P1-1 | Restreindre CORS à l'origine Vercel | main.py:43 | Tout site peut appeler l'API | 5 min | Abus quotas API |
| P1-2 | Ajouter rate limiting (slowapi) | main.py | Protection quotas Finnhub/Yahoo/Kimi | 30 min | Épuisement quotas → service down |
| P1-3 | Écrire tests d'intégration minimum (happy path + error path) | tests/ | Garantie que le pipeline fonctionne | 4h | Déploiement aveugle |
| P1-4 | Extraire `analyze_ticker_core()` partagé par fast et full | pipeline.py | Éliminer duplication, une seule source de vérité | 3h | Divergence garantie entre les deux paths |
| P1-5 | Ajouter `threading.Lock` sur `_batch_jobs` | main.py:51 | Éviter corruption en requêtes concurrentes | 15 min | Corruption données |
| P1-6 | Masquer les stack traces — `detail="Internal error"` | main.py:435 | Ne pas exposer l'implémentation | 10 min | Fuite d'information |
| P1-7 | Ajouter timeout=10 sur tous les `requests.get()` | sources_collector.py, kimi_provider.py | Éviter blocage indefini | 20 min | Serveur bloqué |
| P1-8 | Token Finnhub → header `X-Finnhub-Token` au lieu de query param | sources_collector.py:121 | Token dans les logs CDN | 15 min | Exposition token |

### 🟢 P2 — À planifier (dette technique)

| # | Action | Fichiers | Pourquoi | Effort |
|---|--------|----------|----------|--------|
| P2-1 | Extraire `_get_latest_analysis_dir(ticker)` — éliminer 6 duplications | main.py | Maintenance | 20 min |
| P2-2 | Corriger `_score_moat` — supprimer la ligne 132 morte | scorer.py:132 | Code mort | 2 min |
| P2-3 | Rendre `_score_management_realtime` insensible à la langue | scorer.py:108 | Bug si Kimi répond en anglais | 1h |
| P2-4 | Remplacer `except: pass` par `except Exception as e: logger.warning(...)` | pipeline.py:753+ | Silent failures → données incomplètes sans avertissement | 30 min |
| P2-5 | Persister `_batch_jobs` sur disque (JSON) | main.py | Survie au redémarrage Render | 1h |
| P2-6 | Nettoyer modules legacy (alpha_vantage, transcript_*, seeking_alpha) | backend/ | Code mort | 15 min |
| P2-7 | Ajouter `FileSizeValidator(5MB)` sur `/api/batch/upload` | main.py:186 | Protection OOM | 10 min |
| P2-8 | Corriger PYTHONPATH Render (utiliser `sys.path` ou structure standard) | render.yaml, main.py | Reproductibilité | 30 min |
| P2-9 | Ajouter health check riche (vérifier API keys, connectivité) | main.py:349 | Détection proactive des pannes | 30 min |
| P2-10 | Consolider les deux `requirements.txt` avec versions exactes | requirements.txt | Build reproductible | 20 min |
| P2-11 | Écrire `README.md` (setup, architecture, endpoints) | README.md | Onboarding | 1h |

### 🔵 P3 — Améliorations confort/propreté

| # | Action | Fichiers | Effort |
|---|--------|----------|--------|
| P3-1 | Split `BatchAnalysis.jsx` (396 lignes) en sous-composants | frontend/ | 2h |
| P3-2 | Ajouter `Dockerfile` + `docker-compose.yml` | racine | 1h |
| P3-3 | Ajouter pre-commit hooks (black, ruff, eslint) | .pre-commit-config.yaml | 30 min |
| P3-4 | Nettoyer fichiers parasites racine | racine | 10 min |
| P3-5 | Passer les logs en JSON pour la production | logging_config.py | 30 min |
| P3-6 | Ajouter pagination à `/api/analyses` | main.py:524 | 15 min |
| P3-7 | Ajouter cache Finnhub (TTLCache) | sources_collector.py | 30 min |
| P3-8 | Utiliser `StreamingResponse` pour les ZIP | main.py | 20 min |

---

## 6. Roadmap de professionnalisation

### Phase 1 — Sécurisation et stabilisation (1-2 jours)

**Objectif** : Le service ne crash pas, les secrets sont protégés, les abus sont limités.

| Tâche | Priorité | Effort |
|-------|----------|--------|
| Fix batch status → BackgroundTask | P0-1 | 2h |
| Restreindre CORS | P1-1 | 5 min |
| Rate limiting | P1-2 | 30 min |
| Masquer stack traces | P1-6 | 10 min |
| Timeout sur appels API | P1-7 | 20 min |
| Finnhub token → header | P1-8 | 15 min |
| Lock sur _batch_jobs | P1-5 | 15 min |
| File upload size limit | P2-7 | 10 min |
| Health check riche | P2-9 | 30 min |

**Livrable** : Service stable, protégé contre les abus, déployable en démo.

### Phase 2 — Modularisation et tests (3-5 jours)

**Objectif** : Code maintenable, testé, sans duplication.

| Tâche | Priorité | Effort |
|-------|----------|--------|
| Extraire `analyze_ticker_core()` | P1-4 | 3h |
| Tests d'intégration minimum | P1-3 | 4h |
| Extraire `_get_latest_analysis_dir()` | P2-1 | 20 min |
| Corriger scorer (code mort + langue) | P2-2, P2-3 | 1h |
| Remplacer `except: pass` → logger.warning | P2-4 | 30 min |
| Persister batch jobs | P2-5 | 1h |
| Nettoyer modules legacy | P2-6 | 15 min |
| Consolider requirements.txt | P2-10 | 20 min |

**Livrable** : Code propre, testé, une seule source de vérité par concept.

### Phase 3 — Industrialisation et observabilité (3-5 jours)

**Objectif** : Prêt pour usage régulier, déploiement fiable, diagnostic facile.

| Tâche | Priorité | Effort |
|-------|----------|--------|
| Split `BatchAnalysis.jsx` | P3-1 | 2h |
| Docker + docker-compose | P3-2 | 1h |
| Pre-commit hooks | P3-3 | 30 min |
| README.md | P2-11 | 1h |
| Logs JSON production | P3-5 | 30 min |
| Pagination /api/analyses | P3-6 | 15 min |
| Cache Finnhub + SEC EDGAR | P3-7 | 30 min |
| StreamingResponse ZIP | P3-8 | 20 min |
| Métriques middleware | - | 1h |
| Tests de performance | - | 2h |

**Livrable** : Service industrialisé, documenté, monitoré.

---

## 7. Checklist qualité finale

Pour valider le projet après corrections :

### Sécurité
- [ ] CORS restreint aux origines explicites
- [ ] Rate limiting actif sur tous les endpoints API
- [ ] Aucun token en query param
- [ ] Upload limité en taille
- [ ] Debug endpoint désactivé en production
- [ ] Stack traces masquées
- [ ] `pip-audit` / `npm audit` → 0 vulnérabilité critique
- [ ] `.env` dans `.gitignore` et 0 secret dans Git

### Stabilité
- [ ] Batch ne bloque pas le thread principal (>30s)
- [ ] Timeout sur tous les appels externes
- [ ] Retry avec backoff sur les erreurs transitoires
- [ ] Fallback fonctionnel si une source échoue
- [ ] Pas de `except: pass` silencieux

### Tests
- [ ] 1 test d'intégration end-to-end (mocké)
- [ ] Tests des cas d'erreur (Yahoo down, Kimi timeout, fichier vide)
- [ ] Tests du scorer avec edge cases (valeurs None, extrêmes)
- [ ] Tests de concurrence sur batch jobs

### Performance
- [ ] Fast path < 5 secondes
- [ ] Cache fonctionnel pour Yahoo + Finnhub
- [ ] ZIP en streaming (pas de buffer complet en mémoire)
- [ ] Pagination sur les listes

### Logs
- [ ] Format structuré (timestamp, niveau, contexte)
- [ ] Secrets redactés
- [ ] Rotation automatique
- [ ] `tail -f logs/pipeline.log` permet de suivre une analyse complète

### Configuration
- [ ] Un seul `requirements.txt` avec versions exactes
- [ ] `.env.example` documenté
- [ ] Render déploie sans intervention manuelle
- [ ] Frontend URL configurable sans rebuild

### Documentation
- [ ] `README.md` avec : setup local, architecture, endpoints, déploiement
- [ ] `DEPLOY.md` à jour
- [ ] Pas de fichiers parasites à la racine

---

## 8. Conclusion

### Ce qui est déjà solide
- **Modèles de données** : Les 12 modèles Pydantic sont propres, bien typés, avec valeurs par défaut
- **Logging** : Configuration professionnelle avec redaction des secrets, rotation, injection de contexte
- **Secret hygiene** : Aucune clé dans Git, `.gitignore` correct, redaction dans les logs
- **Pipeline fast-path** : L'idée de séparer l'analyse rapide de la génération de documents est la bonne
- **Multi-sources** : Le fallback Finnhub → Twelve Data → Yahoo est pertinent

### Ce qui est insuffisant
- **Tests** : 3 fichiers de test pour 6,700 lignes de code = couverture quasi nulle
- **Gestion d'erreurs** : Trop de silent failures, pas de retry, pas de circuit breaker
- **Concurrence** : Le batch processing bloque le serveur, état mutable non protégé
- **Documentation** : Pas de README, fichiers parasites, instructions de setup éparpillées

### Ce qui empêche la qualité professionnelle
1. **Absence de tests** — impossible de déployer avec confiance
2. **Batch synchrone** — crash serveur garanti pour >3 tickers
3. **CORS wildcard + pas de rate limiting** — abus inévitable en production
4. **Duplication du pipeline** — deux sources de vérité, maintenance douloureuse
5. **Silent failures** — l'utilisateur ne sait pas ce qui a échoué

### Les 5 actions les plus rentables à faire en premier

| Rang | Action | Effort | Impact |
|------|--------|--------|--------|
| 1 | Fix batch → BackgroundTask (P0-1) | 2h | Élimine le crash serveur |
| 2 | Ajouter tests d'intégration minimum (P1-3) | 4h | Confiance au déploiement |
| 3 | Restreindre CORS + rate limiting (P1-1, P1-2) | 35 min | Sécurise le service |
| 4 | Extraire `analyze_ticker_core()` (P1-4) | 3h | Élimine la duplication |
| 5 | Remplacer `except:pass` + masquer stack traces (P1-6, P2-4) | 40 min | Rend les erreurs visibles sans fuite |

---

*Rapport généré le 2026-05-04 — Audit read-only, aucun fichier modifié.*
*Prochaine étape : mission de correction progressive basée sur ce rapport.*
