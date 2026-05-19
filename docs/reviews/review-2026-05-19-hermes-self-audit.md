# Self-Audit — Spécifications SA v1.1 (Hermes)

| Métadonnée | Valeur |
|---|---|
| Reviewer | Hermes (self-audit, V2 checklist) |
| Date | 2026-05-19 |
| Fichiers revus | spec-fonctionnelle.md, spec-technique.md, ADR-001, ADR-002, 08_matrice_tracabilite.md |
| Méthode | Code inspection + grep + endpoint audit |
| Verdict | **NEEDS FIXES** (1 bloqueur) |

## 🔴 Bloqueurs

### 1. BR-009 Cache invalidation — spéciFIÉ mais NON IMPLÉMENTÉ
**Spec (§5)** : "Cache > 1h ou refresh forcé → Invalider et re-collecter"
**Réalité** : Zéro mécanisme de cache avec TTL dans le codebase. Pas de classe Cache, pas de timestamp de fraîcheur, pas d'invalidation horaire.
**Impact** : Les données yfinance peuvent être servies indéfiniment sans revalidation. Le cache existe peut-être au niveau yfinance lib mais n'est pas contrôlé par le pipeline.
**Action** : Implémenter un cache avec TTL 1h dans le pipeline avant la collecte de données.

## 🟡 Avertissements

### 2. Traceability matrix — décalage vs code
- **EF-005 (lang)** : Matrice dit ✅ mais pointe vers `generator.py` — le code est dans `earnings_deep_dive/prompts.py`. L'implémentation existe mais la référence est fausse.
- **API-001 GET /api/health** : Matrice dit ⚠️ (test manquant) — mais le health check est vérifié quotidiennement par le cron auto-recovery. Un test unitaire manque.
- **NFR-008 Coverage ≥ 60%** : Non mesuré. 32 fichiers de test existent mais pytest --cov n'a pas été exécuté récemment (timeout à 120s).

### 3. Previous Codex review — 5 actions restantes (review-2026-05-19)
| # | Action | Statut |
|---|---|---|
| 1 | UC-001-ERR: Test ticker invalide | ❓ Non vérifié |
| 2 | BR-005: Feedback → réanalyse loop | ❓ Non vérifié |
| 3 | NFR-002: Latence PDF < 2s | ❓ Non vérifié |
| 4 | BL-SA-003: Anti-hallucination URL check | ❓ Non vérifié |
| 5 | EF-005: paramètre `lang` | ✅ Implémenté (prompts.py) |

### 4. Spec status inconsistency
La spec se déclare "Brouillon en review externe" (ligne 11) alors qu'une review Codex a déjà été faite et appliquée. Devrait être "Review externe complétée — corrections appliquées" ou similaire.

## ✅ Points confirmés

- ✅ Auth 15/27 routes protégées (X-API-Key)
- ✅ Pipeline 9 étapes documenté et implémenté
- ✅ Scoring 40 points avec BUY/HOLD/SELL + INSUFFISANT
- ✅ PDF 5 sections obligatoires
- ✅ Support EN/JP/bilingual (prompts.py + translator.py)
- ✅ Rate limit backoff (BR-006, BR-007)
- ✅ Health check + auto-recovery
- ✅ Feedback endpoint (POST/GET)
- ✅ Batch API (upload/analyze/status/download)
- ✅ 7 incohérences Codex review corrigées
- ✅ 4 fichiers docs créés (spec fonc, spec tech, ADR-001, ADR-002)

## Score

| Catégorie | Score | Note |
|---|---|---|
| Spécification | 8/10 | Complète, 13 sections, 427 lignes |
| Traçabilité | 6/10 | Décalage EF-005, plusieurs ⚠️ |
| Implémentation | 8/10 | BR-009 manquant |
| Tests | 5/10 | Coverage non mesuré, 2 ❌ dans matrice |
| Documentation | 9/10 | Complète, manque section "pourquoi ce projet" |
| **Global** | **7/10** | 1 bloqueur (BR-009), spec à mettre à jour |

## Recommandations

1. 🔴 **Implémenter BR-009** — cache avec TTL 1h (bloqueur)
2. 🟡 **Mettre à jour le statut de la spec** — retirer "Brouillon en review externe"
3. 🟡 **Corriger référence EF-005** dans la matrice de traçabilité
4. 🟡 **Mesurer la couverture** avec pytest --cov
5. 🟡 **Vérifier les 4 actions restantes** de la review Codex 2026-05-19
