# SA UAT Test Strategy

Généré par web-recette-autonome v2.0.0 — 2026-05-14 23:00  
Basé sur docs/qa/functional-map.md

## 1. Stratégie de couverture V1

### Smoke tests (chaque déploiement)
| Test | Justification |
|---|---|
| API health → 200 | Backend vivant |
| Frontend charge → 200 | StaticFiles OK |
| Console errors = 0 | Bundle JS correct |
| Cache-Control présent | CDN revalidation |

### Parcours critiques (chaque changement)
| Parcours | Pourquoi critique |
|---|---|
| Ticker parse → tags → Analyze | Porte d'entrée utilisateur |
| AnalysisCard avec score/décision | Valeur métier |
| View Full Report → PDF | Livrable principal |
| Download Dossier → ZIP | Livrable secondaire |

### Non-régression (bugs historiques)
| Bug | Test |
|---|---|
| SEC EDGAR pas sync → score faux | Vérifier score > 0 après analyse |
| VITE_API_URL = /api → Failed to fetch | Console errors check |
| Dist rebuild sans env var → bundle cassé | Vérifier API_BASE dans bundle |
| CDN cache stale → vieux JS | Cache-Control header check |

### États
| État | Test |
|---|---|
| Empty | Effacer ticker → tags disparaissent |
| Invalid | Ticker invalide → pas de crash |
| Loading | SmartLoader visible pendant analyse |
| Success | Score, décision, métriques affichés |

## 2. Exclus de la V1

| Test | Justification |
|---|---|
| Analyse multi-tickers (batch complet) | Trop lent (>10 min), déjà couvert par single |
| ISIN parsing | Peu utilisé, complexe |
| Mode sombre/clair | Pas implémenté |
| Mobile viewport | App desktop-first |
| Visual regression (screenshots comparés) | V2 |
| Accessibilité WCAG | V2 |
| Performance (LCP, TTI) | V2 |
| Feedback panel submit | Feature Nami, non critique pour recette Ced |
| Admin stats détaillées | Admin only, P2 |

## 3. V2 (plus tard)

- Visual regression : comparer PDF généré vs modele.pdf
- Performance : temps de chargement, score Lighthouse
- Multi-browser : Firefox, WebKit
- Mobile : viewport 375px
- CI/CD : GitHub Actions
- Rapports historiques : comparer run N vs N-1
- Tests de charge : 10 tickers simultanés

## 4. Commandes

```bash
# Recette rapide (30-90s)
.venv/bin/pytest tests_e2e/ -v -k "not analysis_completes and not download_dossier"

# Recette complète (5-10 min)
.venv/bin/pytest tests_e2e/ -v

# Rapport HTML
.venv/bin/pytest tests_e2e/ -v --html=e2e/reports/latest/report.html

# Avec capture d'échecs
.venv/bin/pytest tests_e2e/ -v --screenshot only-on-failure --tracing retain-on-failure
```

## 5. Critères d'acceptation par parcours

### P1 — Analyse ticker
- ✅ Le tag ticker apparaît après saisie
- ✅ Le bouton "Analyze N ticker" est cliquable
- ✅ Le SmartLoader apparaît pendant l'analyse
- ✅ La carte de résultat apparaît avec score /40
- ✅ La décision (BUY/HOLD/SELL) est visible
- ✅ Le sélecteur de trimestre fonctionne
- ✅ 0 erreur console critique

### P2 — View Full Report
- ✅ Le bouton "Deep-Dive PDF" est cliquable
- ✅ Une requête vers /api/report/{ticker}/pdf est déclenchée
- ✅ Le PDF s'ouvre (200 ou 202 + poll)

### P3 — Download Dossier
- ✅ Le bouton "Download Dossier" est visible
- ✅ Le compteur de sections s'incrémente (X/7)
- ✅ Le bouton devient actif quand le dossier est prêt
