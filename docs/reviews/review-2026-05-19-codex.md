# Codex Review — Spécifications SA v1.1

| Métadonnée | Valeur |
|---|---|
| Reviewer | Codex CLI (gpt-5.5, v0.130.0) |
| Date | 2026-05-19 |
| Session | 019e3f12-231e-7230-b8bf-695b7f64e65d |
| Fichiers revus | spec-fonctionnelle.md, spec-technique.md, ADR-001, ADR-002, 08_matrice_tracabilite.md |
| Tokens | 53,145 |
| Verdict | **NEEDS FIXES** → corrigé (voir commits 5110931, d306338, <ce commit>) |

## Top 3 Risques identifiés

### 1. 🔴 Routes admin/debug publiques (RÉSOLU)
**Problème :** 15 routes write/admin sans auth alors que la spec exige X-API-Key.
**Fix :** `_require_auth` (CED_CONTROL_KEY) câblé sur 15 routes. Rate limiter 3-tiers. Bypass same-origin pour le frontend. Commit 5110931.

### 2. 🟡 Scope vs traceability incohérent (RÉSOLU)
**Problème :** Traduction FR/JP, batch UI, feedback correction dans le scope mais matrice ❌.
**Fix :** IN-005 → sélection langue EN/JP via LLM. Batch UI → v1.2. Matrice mise à jour. Commit <ce commit>.

### 3. 🟡 Auditabilité sous-spécifiée (RÉSOLU)
**Problème :** Scoring sans INSUFFISANT, sources ≥ 1 vs ≥ 3, pas de provenance.
**Fix :** INSUFFISANT ajouté aux seuils. Source count clarifié (≥1 pour data, ≥3 pour scoring). BR-002 référencé. Commit <ce commit>.

## Incohérences corrigées

| # | Incohérence | Correction |
|---|---|---|
| 1 | ZIP = PDF+XLSX+JSON+sources vs acceptance sans XLSX | XLSX retiré du scope (non implémenté) |
| 2 | Scoring BUY/HOLD/SELL vs BR-002 INSUFFISANT | INSUFFISANT ajouté aux seuils de scoring |
| 3 | sources ≥ 1 vs BR-002 ≥ 3 | Clarifié : ≥1 pour données, ≥3 pour scoring |
| 4 | Diagramme "30 routes" vs audit 29 | Corrigé → 29 routes |
| 5 | "6 API externes" vs diagramme avec 5 | Alpha Vantage ajouté au diagramme |
| 6 | Rate limiter "absent" dans la spec | Corrigé : 3-tiers documenté |
| 7 | Auth "X-API-Key pour upload seulement" | Corrigé : 15 routes protégées |

## Points positifs (non modifiés)

- ✅ ADR-001 et ADR-002 bien structurés, justifications claires
- ✅ Pipeline 9 étapes bien documenté, correspond au code
- ✅ Gestion des erreurs exhaustive (9 cas documentés)
- ✅ Sources de données avec rate limits et fallbacks
- ✅ Architecture diagramme lisible
- ✅ Tests documentés avec commandes exactes

## Actions restantes (post-review)

1. **UC-001-ERR** : Ajouter test ticker invalide (ZZZZYX → message erreur < 30s)
2. **BR-005** : Implémenter feedback → réanalyse loop
3. **NFR-002** : Tester latence affichage PDF < 2s
4. **BL-SA-003** : Anti-hallucination URL check (toutes les URLs du PDF vérifiées)
5. **EF-005** : Implémenter paramètre `lang` (EN/JP) dans le prompt LLM deep-dive
