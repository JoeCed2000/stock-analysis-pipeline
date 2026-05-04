# Post-Mortem — Stock Analysis Pipeline

**Date** : 4 mai 2026 — Session 18:00–19:10
**Projet** : `stock-analysis-pipeline`
**Stack** : FastAPI (Python) + React/Vite (JS)
**Déploiement** : Render (backend) + Vercel (frontend)
**Repo** : https://github.com/JoeCed2000/stock-analysis-pipeline

---

## 1. Ce qui a marché

| Domaine | Résultat |
|---|---|
| **UI V3 (cards)** | Grille CSS responsive, hiérarchie visuelle, badges glow, chart SVG |
| **Parsing auto** | Débounce 500ms, validation ISIN, tags visuels |
| **SmartLoader** | Progression ticker, barre de progression, skeleton cards |
| **Déploiement** | Vercel + Render gratuits, CD via GitHub |
| **Dossier synchrone** | 5/7 sections remplies en ~3s (Render), plus besoin du thread background |
| **10-K SEC EDGAR** | 549 KB de vrai document téléchargé depuis lapced → uploadé sur Render |
| **Countdown UI** | ⏳ 5s → 📥 Download, feedback visuel immédiat |
| **Conversion MD→PDF** | On-the-fly dans le endpoint download, fallback fiable |

---

## 2. Ce qui a cassé / ralenti

| # | Problème | Cause racine | Correction | Temps perdu |
|---|---|---|---|---|
| 1 | **Dérive AlphaRadar/Android** | Agent parti sur le portage Android→Web au lieu du pipeline d'analyse | Rappel utilisateur + recentrage | ~15 min |
| 2 | **Thread background Render muet** | `generate_dossier_background()` échoue silencieusement sur Render free tier (rate-limit, pas de logs visibles) | Déplacé toute la génération en synchrone dans `analyze_ticker_fast()` | ~30 min |
| 3 | **`os.environ.setdefault()` ignore .env** | L'environnement Hermes avait déjà `DOSSIER_UPLOAD_SECRET` (stale) → `setdefault` n'écrase pas | `os.environ[k] = v` (assignation directe) | ~15 min |
| 4 | **`UPLOAD_SECRET` lu au niveau module** | `os.getenv()` exécuté avant que `main()` charge `.env` → toujours vide | Fonction `get_upload_secret()` appelée après chargement | ~10 min |
| 5 | **Cache in-memory bloque le status** | `get_dossier_status()` retournait le cache `{files:[], stage:"generating"}` au lieu de checker le disque | Fall through au disque pour stage "generating" | ~20 min |
| 6 | **Dummy dir `UPLOADED` écrase les vraies analyses** | L'upload endpoint créait des répertoires vides qui gagnaient le tri alphabétique | Skip des dirs `UPLOADED` + upload refusé si pas d'analyse existante | ~10 min |
| 7 | **Finnhub muet sur Render** | Rate-limit IP partagée → `peers: []`, `news: []` → sections 04/05 vides | Fallback sur Yahoo Finance + management tone Kimi K2.6 | ~10 min |
| 8 | **SEC EDGAR bloqué depuis Render** | IP Render blacklistée par SEC → 10-K/8-K jamais téléchargés | Rapatrié sur lapced (cron 5 min → upload) | ~15 min |
| 9 | **10+ patches incrémentaux** | Fix → push → test → échoue → re-fix, sans plan de debug structuré | Aurait dû lister les hypothèses et les tester systématiquement | ~20 min |
| 10 | **"Fini" déclaré sans vérifier le contenu** | Annoncé "7/7 sections" mais en réalité que des README.txt | User a demandé de dézipper et inspecter chaque répertoire | ~5 min |
| 11 | **`.env` commit risqué** | `NVDA_10K_demo.pdf` (549 KB) commit par erreur → `git rm` + `.gitignore` | .gitignore pré-existant mais pattern trop large | ~2 min |

**Temps total perdu estimé** : ~2h30 sur des bugs évitables

---

## 3. Leçons apprises (spécifiques à cette session)

### 3.1 Ne jamais faire confiance au thread background sur Render free tier
- Les threads `daemon=True` sont tués si le serveur idle
- Les API externes (Finnhub, SEC EDGAR) sont rate-limitées depuis l'IP Render
- **Règle** : tout ce qui est essentiel doit être synchrone. Le background = nice-to-have uniquement.

### 3.2 `os.environ.setdefault()` est un piège en environnement agentique
- Hermes propage des variables d'environnement entre les appels
- `setdefault()` conserve la première valeur (souvent stale)
- **Règle** : toujours utiliser `os.environ[k] = v` pour les `.env` chargés explicitement

### 3.3 Les variables globales lues au niveau module sont mortes si `.env` est chargé dans `main()`
- `UPLOAD_SECRET = os.getenv(...)` → exécuté à l'import, avant `main()`
- **Règle** : jamais de `os.getenv()` au niveau module pour des valeurs venant de `.env`. Toujours dans une fonction appelée après chargement.

### 3.4 Un cache in-memory peut bloquer toute l'UI
- Si le cache est rempli avec une valeur vide avant que les données réelles existent
- **Règle** : ne jamais cacher un état intermédiaire ("generating", "loading"). Ne cacher que les états terminaux ("complete", "failed").

### 3.5 Les noms de répertoires influencent le tri
- `UPLOADED` > `NVIDIA_Corp` alphabétiquement → le dummy dir gagnait
- **Règle** : toujours préférer le contenu (ex: présence de `report.md`) au tri alphabétique

### 3.6 Vérifier le contenu des fichiers, pas juste leur existence
- "20 files on disk" ≠ "20 fichiers utiles". 7 étaient des README.txt vides.
- **Règle** : dézipper et inspecter le contenu avant de déclarer "fini"

### 3.7 Rester dans le scope du projet en cours
- Partir sur AlphaRadar/Android alors que la tâche était stock-analysis-pipeline
- **Règle** : si le user ne mentionne pas un autre projet, ne pas y toucher

---

## 4. Skills et règles à créer / renforcer

### 4.1 À CRÉER

| Skill | Description | Trigger |
|---|---|---|
| `scope-discipline` | Ne jamais travailler sur un projet adjacent sans demande explicite. Si mentionné en passant → demander confirmation avant d'agir. | Dès que le user mentionne un autre projet |
| `env-loading-pattern` | Pattern standard pour charger `.env` dans un script Python : `os.environ[k]=v` (pas `setdefault`), jamais de `getenv` au niveau module, toujours dans une fonction post-chargement. | Tout script qui lit `.env` |
| `background-thread-distrust` | Sur Render/plateformes serverless : ne jamais compter sur un thread background. Tout travail essentiel doit être synchrone. Le background = cache/optimisation seulement. | Toute tâche de génération de fichiers sur Render |

### 4.2 À RENFORCER

| Skill existant | Ce qui a manqué | Correctif |
|---|---|---|
| `systematic-debugging` | Pas de liste d'hypothèses, pas de test systématique. Bugs attaqués un par un sans structure. | Ajouter § "Render debugging" : toujours vérifier si le code est bien déployé avant de debug |
| `completion-verification-checklist` | Phase 4 (vérification contenu) sautée. Déclaré "fini" sur la base du nombre de fichiers, pas de leur contenu. | Ajouter § "ZIP content audit" : dézipper + lister + vérifier tailles minimales |
| `stuck-delegate-learn` | 10+ patches sur le même fichier. Aurait dû déléguer après le 3ème échec. | Ajouter un compteur de patches consécutifs sur le même bug |
| `karpathy-coding-principles` | "Surgical Changes" violé : modifications larges au lieu de ciblées. "Simplicity First" violé : complexité inutile (countdown timer overengineered). | Ajouter § "Quand refactorer vs patcher" |
| `agentic-engineering-review` | Pas appliqué avant de push. Les bugs 2-8 auraient été détectés par une revue structurée. | Ajouter § "Pre-push checklist" : 5 checks avant git push |

### 4.3 Règles mémoire à ajouter

```
§
RENDER FREE TIER — threads daemon tués si idle, API externes rate-limitées (Finnhub 429, SEC EDGAR bloquée). 
Tout contenu essentiel → synchrone dans le endpoint. Background = cache/optim only.
§
ENV LOADING — jamais os.environ.setdefault() pour .env (stale env vars d'Hermes). 
Toujours os.environ[k]=v. Jamais os.getenv() au niveau module pour valeurs de .env.
§
CACHE DISCIPLINE — ne jamais cacher "generating"/"loading". Uniquement "complete"/"failed". 
Le frontend doit toujours pouvoir lire l'état réel du disque.
§
POST-FIX VERIFICATION — après tout fix, 3 vérifications : (1) l'endpoint répond 200, 
(2) le contenu est correct (dézipper, lire), (3) le frontend affiche le résultat attendu.
```

---

## 5. Chronologie des erreurs

```
18:00  Début session — user dit "Building dossier trop long + répertoires manquants + md au lieu de PDF"
18:05  DÉRIVE : je pars sur AlphaRadar/Android → user rappelle le scope
18:10  Retour sur stock-analysis-pipeline
18:15  Fix 1 : ajout conversion MD→PDF dans async_dossier.py (ne marche pas, thread muet)
18:25  Fix 2 : conversion on-the-fly dans dossier_download (marche, mais statut bloqué)
18:30  Fix 3 : cache get_dossier_status (setdefault ignoré → fall through au disque)
18:35  Fix 4 : génération synchrone report.md + Excel dans analyze_ticker_fast
18:40  User : "quasiment que des rythmi" → inspection révèle que le thread background ne génère rien
18:45  Fix 5 : toute la génération déplacée en synchrone (company profile, market context, transcripts, report PDF)
18:50  User : "dézippe et regarde dans chaque répertoire" → vérification révèle 10-K manquant
18:52  Fix 6 : upload secret (setdefault + module-level getenv)
18:55  Fix 7 : dummy UPLOADED directories qui shadow les vraies analyses
19:00  Fix 8 : skip UPLOADED dirs + upload vers bonne target
19:05  VÉRIFICATION FINALE : ZIP contient 13 fichiers dont 10-K 562 KB ✅
19:10  Post-mortem écrit
```

---

## 6. Métriques

| Métrique | Valeur |
|---|---|
| Commits total session | 15 |
| Bugs rencontrés | 11 |
| Bugs auto-infligés (mauvais design initial) | 7 (thread background, cache, setdefault, module getenv, dummy dirs, Finnhub assumption, scope drift) |
| Bugs environnement (Render/API) | 4 (SEC EDGAR bloqué, Finnhub rate-limit, Render disk wipe, Vercel cache) |
| Temps productif estimé | ~45 min |
| Temps perdu en debug évitable | ~2h30 |
| Fichiers modifiés (backend) | 4 (async_dossier.py, main.py, pipeline.py, fill_dossiers.py) |
| Fichiers modifiés (frontend) | 1 (AnalysisCard.jsx) |
| Nouvelles règles mémoire | 4 |
| Nouveaux skills suggérés | 3 |

---

## 7. Plan d'action

- [ ] Créer skill `scope-discipline`
- [ ] Créer skill `env-loading-pattern`
- [ ] Créer skill `background-thread-distrust`
- [ ] Patcher `systematic-debugging` avec § Render debugging
- [ ] Patcher `completion-verification-checklist` avec § ZIP content audit
- [ ] Patcher `stuck-delegate-learn` avec compteur de patches
- [ ] Patcher `karpathy-coding-principles` avec "Quand refactorer vs patcher"
- [ ] Patcher `agentic-engineering-review` avec Pre-push checklist
- [ ] Ajouter les 4 règles mémoire au prompt système
- [ ] Nettoyer le répertoire `NVDA_UPLOADED` orphelin sur Render (via redeploy)

---

## Session 2 — 21:00–22:10 — PE Ratio + YFinance Cache Saga

**Objectif** : Faire apparaître le PE ratio, le Revenue, le Net Income et le FCF dans l'API Render (Finnhub free tier ne donne que les ratios, pas les valeurs absolues).

### Contexte

Finnhub free tier retourne `grossMarginTTM`, `operatingMarginTTM` (ratios) mais **jamais** `revenue_annual`, `net_income`, `free_cash_flow`, `pe_current` (valeurs absolues). Ces données viennent de yfinance, mais yfinance est **bloqué sur l'IP mutualisée de Render** (429 rate-limit Yahoo).

Un cron local (`fill_dossiers.py`, toutes les 2 min) pousse les données yfinance vers l'endpoint `/api/cache/financials/{ticker}` sur Render. Mais ces données n'étaient **jamais utilisées** par le pipeline d'analyse.

### Bugs découverts et corrigés

| # | Problème | Cause racine | Correction | Temps |
|---|---|---|---|---|
| 12 | **PE/Revenue/NI/FCF = None** | `get_yahoo_data()` échoue sur Render → merge sauté. Cache yfinance du cron ignoré. | Fallback `_cache_get_yf()` ajouté dans la merge chain. Cache yfinance séparé (`_yf.json`) pour ne pas écraser les données Finnhub. | ~30 min |
| 13 | **`valuation: {}` dans l'API** | `r.pop("valuation", None)` à la ligne 653 de `main.py` — le PE était dans `valuation` mais supprimé avant sérialisation | PE extrait de `valuation` → injecté dans `financial_summary` avant le pop | ~5 min |
| 14 | **Revenue/NI/FCF = 0 après cache merge** | `yf_fin_live` modifié localement (variable shadow) mais jamais repoussé dans `yf_data["financials"]`. PE marchait car au top-level, pas dans `financials`. | `yf_data["financials"] = yf_fin_live` après enrichissement | ~10 min |
| 15 | **Container Render wipe le filesystem** | À chaque restart/cold start, `_yf.json` disparaît. Le push yfinance arrivait avant l'analyse → données perdues. | Le endpoint `/api/cache/financials` enrichit maintenant **directement** le cache principal `{TICKER}.json` en plus d'écrire `_yf.json`. Double filet de sécurité. | ~10 min |
| 16 | **`_cache_set()` erreurs silencieuses** | `except Exception: pass` — impossible de diagnostiquer pourquoi le cache ne persistait pas | `logger.warning()` ajouté | ~2 min |
| 17 | **7+ commits pour debugger un problème local** | Tests uniquement sur Render (aller-retour deploy→test→fix→deploy). Pas de test local du scénario Render. | Aurait dû simuler l'échec `get_yahoo_data()` localement en premier | ~40 min |

### Leçons apprises (spécifiques à cette session)

#### 3.8 Ne jamais `pop` une clé sans vérifier si elle contient des données utiles
- `r.pop("valuation", None)` supprimait le PE ratio de la réponse API depuis le jour 1
- **Règle** : quand on `pop` un champ de la réponse, documenter POURQUOI et vérifier qu'aucune donnée utile n'est perdue

#### 3.9 Toujours repousser les variables locales modifiées dans l'objet parent
- `yf_fin_live = yf_data.get("financials", {})` → modifications sur `yf_fin_live` → jamais visibles dans `yf_data`
- **Règle** : après avoir modifié une copie locale d'un sous-dict, toujours réassigner : `parent["key"] = local_copy`

#### 3.10 Container restart = filesystem wipe sur Render free tier
- Même un fichier écrit avec 200 OK peut disparaître 30 secondes plus tard si le container restart
- **Règle** : tout fichier écrit sur Render doit être considéré comme éphémère. Le cache doit être enrichi immédiatement, pas « plus tard quand quelqu'un lira »

#### 3.11 Tester le scénario d'échec en local avant de déployer
- 7 commits pour debugger un problème reproductible localement (juste bloquer yfinance)
- **Règle** : avant de déployer un fix pour un problème d'API externe, simuler l'échec en local (mock, monkeypatch, ou comment-out)

#### 3.12 Deux caches valent mieux qu'un
- `_yf.json` (yfinance-only) + `{TICKER}.json` (Finnhub+yfinance merged)
- Si le container restart wipe tout, le `_yf.json` est perdu mais le flux d'analyse recrée le `{TICKER}.json` avec les données Finnhub, puis le cron ré-enrichit
- **Règle** : pour les données provenant de deux sources dont une est instable, séparer les caches et faire un merge paresseux

### Fichiers modifiés

| Fichier | Changements |
|---|---|
| `backend/sources_collector.py` | +60 lignes : `_cache_get_yf()`, `_cache_path_yf()`, `YF_CACHE_TTL`, enrichment cache hit, merge yf cache dans fetch path, `yf_data["financials"] = yf_fin_live`, log erreurs `_cache_set` |
| `backend/main.py` | +40 lignes : `_sanitize_json()`, endpoint debug `/api/debug/yf-cache`, enrichment direct du cache principal dans `/api/cache/financials`, PE extrait dans `financial_summary` |

### Plan d'action additionnel

- [ ] Patcher `systematic-debugging` avec § « Toujours simuler l'échec en local avant de déployer sur Render »
- [ ] Ajouter règle mémoire : « Render container restart = filesystem wipe — enrichir le cache principal immédiatement »
- [ ] Remplacer `commit: "83f33d0"` hardcodé → `git rev-parse HEAD` dans le health endpoint
