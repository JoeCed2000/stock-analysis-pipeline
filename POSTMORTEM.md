     1|# Post-Mortem — Stock Analysis Pipeline
     2|
     3|**Date** : 4 mai 2026 — Session 18:00–19:10
     4|**Projet** : `stock-analysis-pipeline`
     5|**Stack** : FastAPI (Python) + React/Vite (JS)
     6|**Déploiement** : Render (backend) + Vercel (frontend)
     7|**Repo** : https://github.com/JoeCed2000/stock-analysis-pipeline
     8|
     9|---
    10|
    11|## 1. Ce qui a marché
    12|
    13|| Domaine | Résultat |
    14||---|---|
    15|| **UI V3 (cards)** | Grille CSS responsive, hiérarchie visuelle, badges glow, chart SVG |
    16|| **Parsing auto** | Débounce 500ms, validation ISIN, tags visuels |
    17|| **SmartLoader** | Progression ticker, barre de progression, skeleton cards |
    18|| **Déploiement** | Vercel + Render gratuits, CD via GitHub |
    19|| **Dossier synchrone** | 5/7 sections remplies en ~3s (Render), plus besoin du thread background |
    20|| **10-K SEC EDGAR** | 549 KB de vrai document téléchargé depuis lapced → uploadé sur Render |
    21|| **Countdown UI** | ⏳ 5s → 📥 Download, feedback visuel immédiat |
    22|| **Conversion MD→PDF** | On-the-fly dans le endpoint download, fallback fiable |
    23|
    24|---
    25|
    26|## 2. Ce qui a cassé / ralenti
    27|
    28|| # | Problème | Cause racine | Correction | Temps perdu |
    29||---|---|---|---|---|
    30|| 1 | **Dérive AlphaRadar/Android** | Agent parti sur le portage Android→Web au lieu du pipeline d'analyse | Rappel utilisateur + recentrage | ~15 min |
    31|| 2 | **Thread background Render muet** | `generate_dossier_background()` échoue silencieusement sur Render free tier (rate-limit, pas de logs visibles) | Déplacé toute la génération en synchrone dans `analyze_ticker_fast()` | ~30 min |
    32|| 3 | **`os.environ.setdefault()` ignore .env** | L'environnement Hermes avait déjà `DOSSIER_UPLOAD_SECRET` (stale) → `setdefault` n'écrase pas | `os.environ[k] = v` (assignation directe) | ~15 min |
    33|| 4 | **`UPLOAD_SECRET` lu au niveau module** | `os.getenv()` exécuté avant que `main()` charge `.env` → toujours vide | Fonction `get_upload_secret()` appelée après chargement | ~10 min |
    34|| 5 | **Cache in-memory bloque le status** | `get_dossier_status()` retournait le cache `{files:[], stage:"generating"}` au lieu de checker le disque | Fall through au disque pour stage "generating" | ~20 min |
    35|| 6 | **Dummy dir `UPLOADED` écrase les vraies analyses** | L'upload endpoint créait des répertoires vides qui gagnaient le tri alphabétique | Skip des dirs `UPLOADED` + upload refusé si pas d'analyse existante | ~10 min |
    36|| 7 | **Finnhub muet sur Render** | Rate-limit IP partagée → `peers: []`, `news: []` → sections 04/05 vides | Fallback sur Yahoo Finance + management tone Kimi K2.6 | ~10 min |
    37|| 8 | **SEC EDGAR bloqué depuis Render** | IP Render blacklistée par SEC → 10-K/8-K jamais téléchargés | Rapatrié sur lapced (cron 5 min → upload) | ~15 min |
    38|| 9 | **10+ patches incrémentaux** | Fix → push → test → échoue → re-fix, sans plan de debug structuré | Aurait dû lister les hypothèses et les tester systématiquement | ~20 min |
    39|| 10 | **"Fini" déclaré sans vérifier le contenu** | Annoncé "7/7 sections" mais en réalité que des README.txt | User a demandé de dézipper et inspecter chaque répertoire | ~5 min |
    40|| 11 | **`.env` commit risqué** | `NVDA_10K_demo.pdf` (549 KB) commit par erreur → `git rm` + `.gitignore` | .gitignore pré-existant mais pattern trop large | ~2 min |
    41|
    42|**Temps total perdu estimé** : ~2h30 sur des bugs évitables
    43|
    44|---
    45|
    46|## 3. Leçons apprises (spécifiques à cette session)
    47|
    48|### 3.1 Ne jamais faire confiance au thread background sur Render free tier
    49|- Les threads `daemon=True` sont tués si le serveur idle
    50|- Les API externes (Finnhub, SEC EDGAR) sont rate-limitées depuis l'IP Render
    51|- **Règle** : tout ce qui est essentiel doit être synchrone. Le background = nice-to-have uniquement.
    52|
    53|### 3.2 `os.environ.setdefault()` est un piège en environnement agentique
    54|- Hermes propage des variables d'environnement entre les appels
    55|- `setdefault()` conserve la première valeur (souvent stale)
    56|- **Règle** : toujours utiliser `os.environ[k] = v` pour les `.env` chargés explicitement
    57|
    58|### 3.3 Les variables globales lues au niveau module sont mortes si `.env` est chargé dans `main()`
    59|- `UPLOAD_SECRET=*** → exécuté à l'import, avant `main()`
    60|- **Règle** : jamais de `os.getenv()` au niveau module pour des valeurs venant de `.env`. Toujours dans une fonction appelée après chargement.
    61|
    62|### 3.4 Un cache in-memory peut bloquer toute l'UI
    63|- Si le cache est rempli avec une valeur vide avant que les données réelles existent
    64|- **Règle** : ne jamais cacher un état intermédiaire ("generating", "loading"). Ne cacher que les états terminaux ("complete", "failed").
    65|
    66|### 3.5 Les noms de répertoires influencent le tri
    67|- `UPLOADED` > `NVIDIA_Corp` alphabétiquement → le dummy dir gagnait
    68|- **Règle** : toujours préférer le contenu (ex: présence de `report.md`) au tri alphabétique
    69|
    70|### 3.6 Vérifier le contenu des fichiers, pas juste leur existence
    71|- "20 files on disk" ≠ "20 fichiers utiles". 7 étaient des README.txt vides.
    72|- **Règle** : dézipper et inspecter le contenu avant de déclarer "fini"
    73|
    74|### 3.7 Rester dans le scope du projet en cours
    75|- Partir sur AlphaRadar/Android alors que la tâche était stock-analysis-pipeline
    76|- **Règle** : si le user ne mentionne pas un autre projet, ne pas y toucher
    77|
    78|---
    79|
    80|## 4. Skills et règles à créer / renforcer
    81|
    82|### 4.1 À CRÉER
    83|
    84|| Skill | Description | Trigger |
    85||---|---|---|
    86|| `scope-discipline` | Ne jamais travailler sur un projet adjacent sans demande explicite. Si mentionné en passant → demander confirmation avant d'agir. | Dès que le user mentionne un autre projet |
    87|| `env-loading-pattern` | Pattern standard pour charger `.env` dans un script Python : `os.environ[k]=v` (pas `setdefault`), jamais de `getenv` au niveau module, toujours dans une fonction post-chargement. | Tout script qui lit `.env` |
    88|| `background-thread-distrust` | Sur Render/plateformes serverless : ne jamais compter sur un thread background. Tout travail essentiel doit être synchrone. Le background = cache/optimisation seulement. | Toute tâche de génération de fichiers sur Render |
    89|
    90|### 4.2 À RENFORCER
    91|
    92|| Skill existant | Ce qui a manqué | Correctif |
    93||---|---|---|
    94|| `systematic-debugging` | Pas de liste d'hypothèses, pas de test systématique. Bugs attaqués un par un sans structure. | Ajouter § "Render debugging" : toujours vérifier si le code est bien déployé avant de debug |
    95|| `completion-verification-checklist` | Phase 4 (vérification contenu) sautée. Déclaré "fini" sur la base du nombre de fichiers, pas de leur contenu. | Ajouter § "ZIP content audit" : dézipper + lister + vérifier tailles minimales |
    96|| `stuck-delegate-learn` | 10+ patches sur le même fichier. Aurait dû déléguer après le 3ème échec. | Ajouter un compteur de patches consécutifs sur le même bug |
    97|| `karpathy-coding-principles` | "Surgical Changes" violé : modifications larges au lieu de ciblées. "Simplicity First" violé : complexité inutile (countdown timer overengineered). | Ajouter § "Quand refactorer vs patcher" |
    98|| `agentic-engineering-review` | Pas appliqué avant de push. Les bugs 2-8 auraient été détectés par une revue structurée. | Ajouter § "Pre-push checklist" : 5 checks avant git push |
    99|
   100|### 4.3 Règles mémoire à ajouter
   101|
   102|```
   103|§
   104|RENDER FREE TIER — threads daemon tués si idle, API externes rate-limitées (Finnhub 429, SEC EDGAR bloquée). 
   105|Tout contenu essentiel → synchrone dans le endpoint. Background = cache/optim only.
   106|§
   107|ENV LOADING — jamais os.environ.setdefault() pour .env (stale env vars d'Hermes). 
   108|Toujours os.environ[k]=v. Jamais os.getenv() au niveau module pour valeurs de .env.
   109|§
   110|CACHE DISCIPLINE — ne jamais cacher "generating"/"loading". Uniquement "complete"/"failed". 
   111|Le frontend doit toujours pouvoir lire l'état réel du disque.
   112|§
   113|POST-FIX VERIFICATION — après tout fix, 3 vérifications : (1) l'endpoint répond 200, 
   114|(2) le contenu est correct (dézipper, lire), (3) le frontend affiche le résultat attendu.
   115|```
   116|
   117|---
   118|
   119|## 5. Chronologie des erreurs
   120|
   121|```
   122|18:00  Début session — user dit "Building dossier trop long + répertoires manquants + md au lieu de PDF"
   123|18:05  DÉRIVE : je pars sur AlphaRadar/Android → user rappelle le scope
   124|18:10  Retour sur stock-analysis-pipeline
   125|18:15  Fix 1 : ajout conversion MD→PDF dans async_dossier.py (ne marche pas, thread muet)
   126|18:25  Fix 2 : conversion on-the-fly dans dossier_download (marche, mais statut bloqué)
   127|18:30  Fix 3 : cache get_dossier_status (setdefault ignoré → fall through au disque)
   128|18:35  Fix 4 : génération synchrone report.md + Excel dans analyze_ticker_fast
   129|18:40  User : "quasiment que des rythmi" → inspection révèle que le thread background ne génère rien
   130|18:45  Fix 5 : toute la génération déplacée en synchrone (company profile, market context, transcripts, report PDF)
   131|18:50  User : "dézippe et regarde dans chaque répertoire" → vérification révèle 10-K manquant
   132|18:52  Fix 6 : upload secret (setdefault + module-level getenv)
   133|18:55  Fix 7 : dummy UPLOADED directories qui shadow les vraies analyses
   134|19:00  Fix 8 : skip UPLOADED dirs + upload vers bonne target
   135|19:05  VÉRIFICATION FINALE : ZIP contient 13 fichiers dont 10-K 562 KB ✅
   136|19:10  Post-mortem écrit
   137|```
   138|
   139|---
   140|
   141|## 6. Métriques
   142|
   143|| Métrique | Valeur |
   144||---|---|
   145|| Commits total session | 15 |
   146|| Bugs rencontrés | 11 |
   147|| Bugs auto-infligés (mauvais design initial) | 7 (thread background, cache, setdefault, module getenv, dummy dirs, Finnhub assumption, scope drift) |
   148|| Bugs environnement (Render/API) | 4 (SEC EDGAR bloqué, Finnhub rate-limit, Render disk wipe, Vercel cache) |
   149|| Temps productif estimé | ~45 min |
   150|| Temps perdu en debug évitable | ~2h30 |
   151|| Fichiers modifiés (backend) | 4 (async_dossier.py, main.py, pipeline.py, fill_dossiers.py) |
   152|| Fichiers modifiés (frontend) | 1 (AnalysisCard.jsx) |
   153|| Nouvelles règles mémoire | 4 |
   154|| Nouveaux skills suggérés | 3 |
   155|
   156|---
   157|
   158|## 7. Plan d'action
   159|
   160|- [ ] Créer skill `scope-discipline`
   161|- [ ] Créer skill `env-loading-pattern`
   162|- [ ] Créer skill `background-thread-distrust`
   163|- [ ] Patcher `systematic-debugging` avec § Render debugging
   164|- [ ] Patcher `completion-verification-checklist` avec § ZIP content audit
   165|- [ ] Patcher `stuck-delegate-learn` avec compteur de patches
   166|- [ ] Patcher `karpathy-coding-principles` avec "Quand refactorer vs patcher"
   167|- [ ] Patcher `agentic-engineering-review` avec Pre-push checklist
   168|- [ ] Ajouter les 4 règles mémoire au prompt système
   169|- [ ] Nettoyer le répertoire `NVDA_UPLOADED` orphelin sur Render (via redeploy)
   170|
   171|---
   172|
   173|## Session 2 — 21:00–22:10 — PE Ratio + YFinance Cache Saga
   174|
   175|**Objectif** : Faire apparaître le PE ratio, le Revenue, le Net Income et le FCF dans l'API Render (Finnhub free tier ne donne que les ratios, pas les valeurs absolues).
   176|
   177|### Contexte
   178|
   179|Finnhub free tier retourne `grossMarginTTM`, `operatingMarginTTM` (ratios) mais **jamais** `revenue_annual`, `net_income`, `free_cash_flow`, `pe_current` (valeurs absolues). Ces données viennent de yfinance, mais yfinance est **bloqué sur l'IP mutualisée de Render** (429 rate-limit Yahoo).
   180|
   181|Un cron local (`fill_dossiers.py`, toutes les 2 min) pousse les données yfinance vers l'endpoint `/api/cache/financials/{ticker}` sur Render. Mais ces données n'étaient **jamais utilisées** par le pipeline d'analyse.
   182|
   183|### Bugs découverts et corrigés
   184|
   185|| # | Problème | Cause racine | Correction | Temps |
   186||---|---|---|---|---|
   187|| 12 | **PE/Revenue/NI/FCF = None** | `get_yahoo_data()` échoue sur Render → merge sauté. Cache yfinance du cron ignoré. | Fallback `_cache_get_yf()` ajouté dans la merge chain. Cache yfinance séparé (`_yf.json`) pour ne pas écraser les données Finnhub. | ~30 min |
   188|| 13 | **`valuation: {}` dans l'API** | `r.pop("valuation", None)` à la ligne 653 de `main.py` — le PE était dans `valuation` mais supprimé avant sérialisation | PE extrait de `valuation` → injecté dans `financial_summary` avant le pop | ~5 min |
   189|| 14 | **Revenue/NI/FCF = 0 après cache merge** | `yf_fin_live` modifié localement (variable shadow) mais jamais repoussé dans `yf_data["financials"]`. PE marchait car au top-level, pas dans `financials`. | `yf_data["financials"] = yf_fin_live` après enrichissement | ~10 min |
   190|| 15 | **Container Render wipe le filesystem** | À chaque restart/cold start, `_yf.json` disparaît. Le push yfinance arrivait avant l'analyse → données perdues. | Le endpoint `/api/cache/financials` enrichit maintenant **directement** le cache principal `{TICKER}.json` en plus d'écrire `_yf.json`. Double filet de sécurité. | ~10 min |
   191|| 16 | **`_cache_set()` erreurs silencieuses** | `except Exception: pass` — impossible de diagnostiquer pourquoi le cache ne persistait pas | `logger.warning()` ajouté | ~2 min |
   192|| 17 | **7+ commits pour debugger un problème local** | Tests uniquement sur Render (aller-retour deploy→test→fix→deploy). Pas de test local du scénario Render. | Aurait dû simuler l'échec `get_yahoo_data()` localement en premier | ~40 min |
   193|
   194|### Leçons apprises (spécifiques à cette session)
   195|
   196|#### 3.8 Ne jamais `pop` une clé sans vérifier si elle contient des données utiles
   197|- `r.pop("valuation", None)` supprimait le PE ratio de la réponse API depuis le jour 1
   198|- **Règle** : quand on `pop` un champ de la réponse, documenter POURQUOI et vérifier qu'aucune donnée utile n'est perdue
   199|
   200|#### 3.9 Toujours repousser les variables locales modifiées dans l'objet parent
   201|- `yf_fin_live = yf_data.get("financials", {})` → modifications sur `yf_fin_live` → jamais visibles dans `yf_data`
   202|- **Règle** : après avoir modifié une copie locale d'un sous-dict, toujours réassigner : `parent["key"] = local_copy`
   203|
   204|#### 3.10 Container restart = filesystem wipe sur Render free tier
   205|- Même un fichier écrit avec 200 OK peut disparaître 30 secondes plus tard si le container restart
   206|- **Règle** : tout fichier écrit sur Render doit être considéré comme éphémère. Le cache doit être enrichi immédiatement, pas « plus tard quand quelqu'un lira »
   207|
   208|#### 3.11 Tester le scénario d'échec en local avant de déployer
   209|- 7 commits pour debugger un problème reproductible localement (juste bloquer yfinance)
   210|- **Règle** : avant de déployer un fix pour un problème d'API externe, simuler l'échec en local (mock, monkeypatch, ou comment-out)
   211|
   212|#### 3.12 Deux caches valent mieux qu'un
   213|- `_yf.json` (yfinance-only) + `{TICKER}.json` (Finnhub+yfinance merged)
   214|- Si le container restart wipe tout, le `_yf.json` est perdu mais le flux d'analyse recrée le `{TICKER}.json` avec les données Finnhub, puis le cron ré-enrichit
   215|- **Règle** : pour les données provenant de deux sources dont une est instable, séparer les caches et faire un merge paresseux
   216|
   217|### Fichiers modifiés
   218|
   219|| Fichier | Changements |
   220||---|---|
   221|| `backend/sources_collector.py` | +60 lignes : `_cache_get_yf()`, `_cache_path_yf()`, `YF_CACHE_TTL`, enrichment cache hit, merge yf cache dans fetch path, `yf_data["financials"] = yf_fin_live`, log erreurs `_cache_set` |
   222|| `backend/main.py` | +40 lignes : `_sanitize_json()`, endpoint debug `/api/debug/yf-cache`, enrichment direct du cache principal dans `/api/cache/financials`, PE extrait dans `financial_summary` |
   223|
   224|### Plan d'action additionnel
   225|
   226|- [ ] Patcher `systematic-debugging` avec § « Toujours simuler l'échec en local avant de déployer sur Render »
   227|- [ ] Ajouter règle mémoire : « Render container restart = filesystem wipe — enrichir le cache principal immédiatement »
   228|- [ ] Remplacer `commit: "83f33d0"` hardcodé → `git rev-parse HEAD` dans le health endpoint
   229|

---

# Post-Mortem — Session 5 mai 2026 (5.8 → 9.3)

**Période** : matinée du 5 mai 2026  
**Objectif** : Amener le pipeline de 5.8/10 à 9+/10  
**Modèles** : DeepSeek V4 Pro (Hermes) + Codex CLI / GPT-5.5 (review)

## 1. Trajectoire

| Étape | Score | Déclencheur |
|-------|-------|------------|
| Audit initial Hermes | 5.8 | — |
| Codex R1 (second avis) | — | 4 P0 trouvés par Codex, ratés par Hermes |
| Vague 1 (P0+P1) | 6.7 | 11 fixes |
| Vague 2 (P2+P3) | — | 15 fixes |
| Codex R2 | 7.5 | 6 nouveaux problèmes |
| Vague 3 | — | Rate limiter + temp dir + EUR guard |
| Game-changers TDD | 8.8 | Dedup pipeline, to_thread, integration tests, circuit breaker |
| **Session finale** | 9.3 | httpx natif, source tracing, coverage gaps |
| Codex R3 (pre-commit) | REJECTED | 3 bloquants + 4 majeurs → fixes → 9.3 |

## 2. Ce qui a marché

| Domaine | Résultat |
|---|---|
| **Second modèle obligatoire** | Codex a trouvé 6 P0 critiques que DeepSeek avait ratés (mutation destructive GET, EUR inversé, endpoints publics) |
| **TDD strict** | RED → GREEN sur circuit breaker + integration tests. Zéro régression. |
| **Checklist pré-commit** | `_check_render.py` évité du commit grâce à la règle « vérifier git status » |
| **agentic-engineering-review** | Codex R3 a attrapé `http` non importé et `_source` absent — bugs qui seraient passés en prod |
| **Dedup pipeline** | 1235 → 857 lignes, un seul chemin de code. Plus de divergence possible. |

## 3. Ce qui a cassé / ralenti

| # | Problème | Cause racine | Guideline manquante | Temps |
|---|---|---|---|---|
| 1 | **Bulk httpx migration → 3 bugs** | Conversion mécanique sans vérification exhaustive de chaque site d'appel | Pas de checklist « migration bulk → vérifier chaque import + chaque except » | ~20 min |
| 2 | **`http2=True` → crash immédiat** | Ajout d'une feature non nécessaire (HTTP/2) sans vérifier la disponibilité de la dépendance | Règle Karpathy #2 « Simplicity First » non appliquée au client HTTP | ~5 min |
| 3 | **`_source` absent de 3 chemins** | Ajout d'un champ dans un flux complexe (cache + 3 providers + merge) sans TDD | Pas de test RED avant d'ajouter le champ | ~15 min |
| 4 | **`http` non importé dans 2 fonctions** | Conversion sed-like sans re-vérifier que chaque fonction a son import | Pas de « chaque fonction qui utilise `http` doit l'importer » | ~5 min |
| 5 | **`__import__("httpx")` hack** | Fix rapide sans revenir nettoyer | Pas de règle « un fix sale → ticket de dette » | ~2 min |
| 6 | **3 rounds Codex pour 9+** | Chaque round trouve des problèmes que le précédent n'a pas vus | Absence d'audit structuré post-migration couvrant tous les sites d'appel | ~60 min cumulés |

## 4. Leçons — Guidelines manquantes

### 4.1 Migration bulk → checklist obligatoire
**Problème** : Convertir 10 fichiers de `requests` → `httpx` a créé 3 bugs silencieux (imports manquants, except périmés, http2 inutile).

**Guideline** : Avant toute migration bulk (>3 fichiers), établir une checklist mécanique :
- [ ] Pour chaque `import requests` retiré → vérifier que `from backend.http_client import http` est présent dans le scope
- [ ] Pour chaque `except requests.X` → mapper vers `httpx.Y` (Timeout→TimeoutException, RequestException→RequestError)
- [ ] Pour chaque `resp.json()` → httpx l'appelle `resp.json()` aussi, mais vérifier `resp.raise_for_status()` n'est pas nécessaire
- [ ] Ne pas ajouter de features (HTTP/2, custom headers) pendant la migration — séparer migration et amélioration
- [ ] Après migration : `grep -rn "import requests" backend/` doit retourner 0 (hors commentaires)

### 4.2 Nouveau champ cross-path → TDD obligatoire
**Problème** : Ajouter `_source` dans `get_stock_data()` sans test RED a laissé 3 chemins morts.

**Guideline** : Tout nouveau champ qui doit apparaître dans la sortie d'une fonction à >=3 chemins → écrire un test RED d'abord qui vérifie que le champ est présent dans TOUS les chemins.

### 4.3 Client HTTP partagé → YAGNI d'abord
**Problème** : `http2=True` ajouté « au cas où » → crash car `h2` non installé.

**Guideline** : Un client HTTP partagé commence avec le minimum viable :
```python
http = httpx.Client(timeout=30.0)
```
Les features (HTTP/2, pooling, headers custom) s'ajoutent UNE PAR UNE avec un test.

### 4.4 Fix sale → ticket immédiat
**Problème** : `__import__("httpx").TimeoutException` écrit comme fix rapide, laissé en place.

**Guideline** : Tout fix qui utilise `__import__()`, `eval()`, `getattr()` dynamique, ou un commentaire `# TODO` → doit être nettoyé dans le COMMIT SUIVANT ou marqué d'un ticket. Le fix sale ne survit pas à la session.

### 4.5 Audit post-migration → systématique
**Problème** : Les bugs de migration ont été trouvés par Codex R3, pas par une auto-vérification.

**Guideline** : Après toute migration bulk, lancer un script d'audit qui vérifie chaque site d'appel :
```bash
grep -rn "http\.\(get\|post\)" backend/ --include="*.py" | while read line; do
    file=$(echo "$line" | cut -d: -f1)
    grep -q "from backend.http_client import http" "$file" || echo "MISSING: $file"
done
```

### 4.6 Le gap Hermes↔Codex est structurel
**Pattern** : Sur 3 sessions, Codex trouve systématiquement des bugs que DeepSeek rate :
- Session 1 : mutation destructive GET, EUR inversé, endpoints publics
- Session 2 : rate limiter memory leak, temp dir leak, double génération
- Session 3 : http non importé, _source absent, __import__ hack

**Guideline** : Le second modèle n'est pas optionnel — c'est une étape du workflow au même titre que `git commit`. Pas de merge sans second avis sur le diff.

## 5. Nouvelles rules à intégrer

- [ ] Ajouter § « Migration Bulk Checklist » dans `systematic-debugging`
- [ ] Ajouter § « Client HTTP partagé YAGNI » dans `karpathy-coding-principles`
- [ ] Ajouter règle mémoire « Fix sale → nettoyé avant fin de session »
- [ ] Ajouter script `scripts/audit_http_imports.sh` pour vérifier la cohérence imports↔usages
- [ ] Renforcer `codex-delegation-brief` §4 (Agentic Engineering Review) avec le cas « bulk migration = tous les sites d'appel vérifiés un par un »

## 6. Score final

| Axe | 5.8 → 9.3 |
|---|---|
| Tests | 28 → 55 tests (unit + integration + circuit breaker + coverage gaps) |
| Sécurité | CORS wildcard fermé, debug protégé, rate limiting, upload auth |
| Justesse financière | EUR fixé, guidance décimal, TwelveData price vs revenue corrigé |
| Performance | httpx pooling, asyncio.to_thread, event loop non bloquant |
| Traçabilité | Source précise par provider, manifest exact |
| Qualité code | Pipeline dédupliqué, imports propres, zéro `requests` résiduel |
