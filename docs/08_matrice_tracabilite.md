# Matrice de traçabilité — Stock Analysis Pipeline v1.1

## Exigences fonctionnelles → Tests

| ID Exigence | Exigence | Source | § Spec | Test(s) | Statut |
|---|---|---|---|---|---|
| UC-001 | Analyser un ticker | AC-001 | §2 | test_pipeline.py, tests_e2e/test_sa_recette.py | ✅ |
| UC-001-ERR | Ticker invalide | AC-002 | §2 | — | ❌ |
| UC-001-PART | API source partielle | AC-003 | §2 | — | ⚠️ |
| UC-002 | Consulter PDF | AC-004 | §2 | test_renderer.py, tests_e2e/ | ✅ |
| UC-002-MISS | Donnée manquante PDF | AC-005 | §2 | test_renderer.py | ✅ |
| UC-003 | Télécharger ZIP | AC-006 | §2 | test_pipeline.py | ✅ |
| UC-004 | Batch analysis | AC-007 | §2 | — | ⚠️ |
| UC-005 | Feedback | AC-008 | §2 | — | ⚠️ |
| UC-006 | Health check | AC-009 | §2 | — | ⚠️ |
| BR-001 | Pas d'invention | BR-001 | §5 | test_renderer.py | ✅ |
| BR-002 | Score min 3 sources | BR-002 | §5 | test_scorer.py | ✅ |
| BR-003 | PDF 5 sections | BR-003 | §5 | test_renderer.py | ✅ |
| BR-004 | Archivage obligatoire | BR-004 | §5 | test_pipeline.py | ✅ |
| BR-005 | Feedback avant réanalyse | BR-005 | §5 | — | ❌ |
| BR-006 | Rate limit cascade | BR-006 | §5 | — | ⚠️ |
| BR-007 | Timeout source | BR-007 | §5 | — | ⚠️ |
| BR-008 | Batch max 10 | BR-008 | §5 | — | ⚠️ |
| BR-009 | Cache invalidation | BR-009 | §5 | — | ⚠️ |
| PIP-001 → 009 | Pipeline 9 étapes | UC-001 | §3 | test_pipeline.py | ✅ |
| EF-005 | Sélection langue EN/JP/bilingual | UC-001 | §1.2 | generator.py (lang param) | ✅ |
| EF-006 | Batch CSV | UC-004 | §1.2 | — | ⚠️ |

## Exigences non fonctionnelles → Vérification

| ID NFR | Exigence | Cible | Vérification | Statut |
|---|---|---|---|---|
| NFR-001 | Analyse < 5 min | < 300 s | Chrono pipeline | ⚠️ |
| NFR-002 | PDF < 2 s | < 2 s | Latence HTTP | ❌ |
| NFR-003 | API health 99% | Cron 15 min | Auto-recovery script | ✅ |
| NFR-004 | Auth write endpoints | 401 si absent | curl -H (test manuel) | ⚠️ |
| NFR-005 | Pas invention | 0 | Audit visuel PDF | ✅ |
| NFR-006 | Logs structurés | Tous | Vérification logs/main.py | ✅ |
| NFR-007 | Rate limit → retry | Auto | Code sources_collector.py | ✅ |
| NFR-008 | Coverage ≥ 60% | pytest --cov | CI pipeline | ⚠️ |
| NFR-009 | Secrets .env | 0 leak | Scan pre-commit | ✅ |

## Routes API → User Story

| ID API | Route | US liée | Test |
|---|---|---|---|
| API-001 | GET /api/health | UC-006 | ⚠️ |
| API-010 | POST /api/analyze | UC-001 | ✅ |
| API-011 | POST /api/analyze/async | UC-001 | ⚠️ |
| API-020 | GET /api/earnings/quarters/{t} | UC-001 | ⚠️ |
| API-021 | POST /api/earnings/deep-dive | UC-001 | ⚠️ |
| API-023 | GET /api/report/{t}/pdf | UC-002 | ✅ |
| API-031 | GET /api/dossier/{t}/download | UC-003 | ✅ |
| API-040 | POST /api/batch/upload | UC-004 | ⚠️ |
| API-050 | GET /api/sources/{t} | UC-001 | ⚠️ |
| API-060 | POST /api/feedback | UC-005 | ⚠️ |

**Légende :** ✅ Testé / ⚠️ Test manquant ou non automatisé / ❌ Non implémenté

## Résumé

| Catégorie | Total | ✅ | ⚠️ | ❌ |
|---|---|---|---|---|
| Exigences fonctionnelles | 22 | 11 | 9 | 2 |
| Exigences non fonctionnelles | 9 | 5 | 3 | 1 |
| Routes API | 29 | 4 | 6 | 0 |
| Règles métier | 9 | 4 | 4 | 1 |

**Score de couverture v1.1 : 23/40 exigences testées (58 %).** Les ⚠️ sont majoritairement des tests manquants (à implémenter). Les ❌ sont : UC-001-ERR (ticker invalide non testé) et BR-005 (feedback avant réanalyse). Batch UI et feedback UI → v1.2.
