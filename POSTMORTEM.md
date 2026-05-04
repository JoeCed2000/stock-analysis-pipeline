# Post-Mortem — Stock Analysis Pipeline

**Date** : 4 mai 2026  
**Projet** : `stock-analysis-pipeline`  
**Stack** : FastAPI (Python) + React/Vite (JS)  
**Déploiement** : Render (backend) + Vercel (frontend)  
**Repo** : https://github.com/JoeCed2000/stock-analysis-pipeline

---

## 1. Ce qui a marché

| Domaine | Résultat |
|---|---|
| **UI V3 (cards)** | Grille CSS responsive, hiérarchie visuelle (Score → Metrics → Insight → Chart → Actions → Conviction), badges glow, chart SVG horizontal |
| **Parsing auto** | Débounce 500ms, validation ISIN checksum, tags visuels avec checkboxes, sélection/déselection |
| **SmartLoader** | Progression ticker (X/N), barre de progression, 4 étapes dynamiques, skeleton cards shimmer — remplace le double spinner brouillon |
| **Déploiement** | Vercel + Render gratuits, déploiement continu via GitHub |
| **Itération rapide** | 6 commits en 2h sur les retours design (polices, largeur cards, overflow) |

---

## 2. Ce qui a cassé / ralenti

| Problème | Cause | Correction |
|---|---|---|
| **Double spinner** | `TickerInput` ET `App` affichaient chacun un spinner indépendant | Supprimé les 2, remplacé par `SmartLoader` unique dans `App` |
| **"G" de Growth coupé** | Labels SVG trop larges pour les barres (8 critères × 20px dans viewBox 200) | Réduit barW=20→18, gap=5→4, police label 9→8, score 10→9 |
| **Titre "Pipeline"** | Nom interne resté dans le code | Renommé "📈 Stock Analysis", centré |
| **Messages redondants** | "Running…" + "Analyzing…" + "Please wait…" + "~20-30 seconds" ×2 | Un seul message : "Analyzing **NVDA** — 1/4 tickers" |
| **Token GitHub expiré** | Premier token créé avec expiration courte, révoqué entre-temps | Recréé sans expiration |
| **`requirements.txt` absent** | Le projet n'avait pas de fichier de dépendances pour Render | Créé avec fastapi, uvicorn, yfinance, finnhub, reportlab, etc. |
| **Imports `backend.*` cassés sur Render** | Root Directory = `backend` rendait `from backend.models` introuvable | Changé Root Directory vide, Start Command avec `PYTHONPATH=.` et `uvicorn backend.main:app` |
| **Cache Vercel a ignoré `VITE_API_URL`** | `vercel --prod -e` n'a pas invalidé le cache de build | `--force` + `.env.production` pour forcer le rebuild |
| **Rate-limit Yahoo Finance** | IP partagée Render → 429 Too Many Requests | Temporaire, se lève seul |

---

## 3. Leçons apprises

1. **Tester le déploiement tôt** — `requirements.txt` manquant, imports cassés, rate-limit : 3 problèmes découverts SEULEMENT au déploiement. Un `pip install` dans un venv frais + `uvicorn` local aurait détecté les 2 premiers.
2. **Variables d'environnement frontend = build-time** — Vite injecte `VITE_*` au build. Sans `.env.production` ou `--force`, le cache Vercel conserve l'ancienne valeur.
3. **Ne jamais faire confiance au hot reload sur NTFS** — Vite HMR sous WSL2/NTFS est peu fiable. Vérifier avec `curl` ou redémarrer le serveur.
4. **Un seul loader, une seule source de vérité** — Les doubles spinners créent de la confusion. Centraliser l'état `loading` dans le parent.
5. **Les tokens GitHub doivent être "No expiration" pour les déploiements** — Sinon ils expirent au pire moment.

---

## 4. Points d'amélioration futurs

- [ ] **Streaming backend** → progression réelle au lieu de simulée (WebSocket ou SSE)
- [ ] **Cache des données financières** → éviter les rate-limits (Redis ou fichier local)
- [ ] **Authentification** → protection des endpoints API
- [ ] **Tests E2E Playwright** → valider le flux complet déploiement inclus
- [ ] **Monitoring** → logs Render + Vercel consolidés
