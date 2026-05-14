# SA Functional Map — Stock Analysis Pipeline

Généré par web-recette-autonome v2.0.0 — 2026-05-14 23:00
Sources : wiki (COMMANDS.md, AGENTS.md, AGENTS.md), code (backend/main.py, frontend/src/*), runtime (localhost:8780), openapi.json

## 1. Fonctionnalités principales

### Core
| ID | Fonctionnalité | Source | Criticité | Couvert ? |
|---|---|---|---|---|
| F1 | Analyse de ticker (single) | Wiki + Code | P0 | ✅ P0 |
| F2 | Scoring /40 (8 critères) | Code | P0 | ✅ P0 |
| F3 | Génération PDF (Deep-Dive) | Code | P0 | ✅ P0 |
| F4 | Génération ZIP (Dossier 7 sections) | Code | P0 | ✅ P0 |
| F5 | Analyse batch (multi-tickers) | Wiki + Code | P1 | ✅ P1 |
| F6 | Upload fichier tickers | Code | P1 | ⚠️ Partiel |
| F7 | Parsing ISIN → ticker | Code | P1 | ❌ Non couvert |

### UI/UX
| ID | Fonctionnalité | Source | Criticité | Couvert ? |
|---|---|---|---|---|
| F8 | Changement langue EN↔JA | Code | P1 | ✅ P1 |
| F9 | Sélecteur trimestre | Code | P1 | ✅ P1 |
| F10 | Section "About" expansible | Code | P1 | ✅ P1 |
| F11 | Feedback panel (Nami) | Code | P2 | ❌ Non couvert |
| F12 | SmartLoader (étapes) | Code | P1 | ⚠️ Implicite |
| F13 | SkeletonCard (loading) | Code | P1 | ⚠️ Implicite |

### Admin
| ID | Fonctionnalité | Source | Criticité | Couvert ? |
|---|---|---|---|---|
| F14 | Dashboard admin (#admin) | Code | P2 | ✅ P1 |
| F15 | Recent searches | Code | P2 | ❌ Non couvert |
| F16 | Search stats | Code | P2 | ❌ Non couvert |
| F17 | Admin feedback list | Code | P2 | ❌ Non couvert |

### Data & Pipeline
| ID | Fonctionnalité | Source | Criticité | Couvert ? |
|---|---|---|---|---|
| F18 | Yahoo Finance enrichment | Code | P0 | ❌ Non couvert |
| F19 | SEC EDGAR enrichment | Code | P0 | ❌ Non couvert |
| F20 | Finnhub data | Code | P1 | ❌ Non couvert |
| F21 | Cache financials | Code | P1 | ❌ Non couvert |
| F22 | Data quality flag | Code (commit 66b7d47) | P1 | ❌ Non couvert |
| F23 | Traceability report | Code | P2 | ❌ Non couvert |
| F24 | Sources manifest | Code | P2 | ❌ Non couvert |

## 2. Parcours utilisateur

| ID | Parcours | Pages | Criticité | Test |
|---|---|---|---|---|
| P1 | Analyse ticker → résultat | Home → Loading → Card | P0 | test_p0_analysis_completes |
| P2 | Voir rapport PDF | Card → PDF new tab | P0 | test_p0_view_full_report |
| P3 | Télécharger dossier ZIP | Card → Download | P0 | test_p0_download_dossier |
| P4 | Changer langue | Home | P1 | test_p1_language_switch |
| P5 | Changer trimestre | Card → Quarter change | P1 | test_p1_quarter_selector |
| P6 | Mode batch | Home → Batch UI | P1 | test_p1_batch_mode |
| P7 | Page admin | Home → #admin | P1 | test_p1_admin_page |
| P8 | Saisie ticker → tags | Home | P0 | test_p0_ticker_parse |
| P9 | Soumettre feedback | Card → Feedback | P2 | ❌ Non couvert |
| P10 | Upload fichier tickers | Batch → Upload | P1 | ❌ Non couvert |

## 3. États

| État | Couvert ? |
|---|---|
| Loading (SmartLoader + SkeletonCard) | ✅ P0 (implicite) |
| Success (AnalysisCard avec données) | ✅ P0 |
| Error (message utilisateur) | ⚠️ Partiel |
| Empty (pas de ticker saisi) | ✅ |
| Invalid ticker | ✅ |
| Timeout (>10 min) | ❌ Non couvert |
| API down (backend off) | ❌ Non couvert |

## 4. Dépendances

- Backend : uvicorn port 8780, workers=4
- Frontend : React/Vite, dist/ monté via StaticFiles
- APIs externes : Yahoo Finance, SEC EDGAR, Finnhub
- Cache : analyses/ directory, cache financier
- Tunnel : Cloudflare named tunnel → sa.cedlabusa.net

## 5. Risques de régression

| Risque | Probabilité | Impact |
|---|---|---|
| Dist reconstruit sans VITE_API_URL | 🔴 Haute (déjà arrivé 3x) | P0 — boutons cassés |
| CDN cache stale bundle | 🟡 Moyenne | P0 — prod KO |
| SEC EDGAR → scorer pas sync | 🔴 Haute (bug précédent) | P0 — score faux |
| yfinance data manquante → DATA NOT AVAILABLE | 🟡 Moyenne | P1 — PDF incomplet |
| Tunnel Cloudflare en mode quick | 🟢 Basse | P0 — prod 530 |
| PDF renderer emojis/callout boxes | 🟡 Moyenne | P2 — qualité visuelle |

## 6. Fonctionnalités détectées dans le code mais NON documentées

- F17 Admin feedback list — endpoint /api/admin/feedback existe mais pas dans COMMANDS.md
- F22 Data quality flag — champ `data_quality` dans AnalysisResult, non documenté
- F23 Traceability report — endpoint /api/traceability/{ticker}, non documenté

## 7. Fonctionnalités documentées mais NON confirmées runtime

- Aucune pour le moment (tout le documenté a été vérifié)
