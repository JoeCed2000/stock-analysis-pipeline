# NS Handoff — 12/06/2026 soir (vérification PDF NVDA + fix label fiscal)

## État au moment du handoff
- **Backend prod** : `f7a3fc7` servi (local + sa.cedlabusa.net, health 200), branche `kanban/spec-fonctionnelle-sa` poussée
- **Unité systemd canonique** : `stock-pipeline.service` (host 0.0.0.0:8780). `sa-backend.service` **stoppée + désactivée** (avec accord Ced) — les deux étaient enabled, le perdant du port crash-loopait toutes les 6 s en ré-important backend.main (ingestion 20 PDFs + patchright à chaque respawn)
- **Tests** : 980 passed, 8 skipped, 0 failed (suite complète, 16 min 27)
- **Working tree** : propre (hors dossiers non suivis d'autres agents)

## Checklist du handoff précédent — TOUTE VERTE ✅
Vérifiée sur le PDF servi en prod (dossier `2026-06-12_185336_NVDA`, 332 KB, 20 pages) :
- Titre **FY2027 Q1** ✓ (était FY2026 Q1 — défaut corrigé, voir bug ci-dessous)
- EPS YoY **+214.5%** ✓ · Net Cash N-1 **$42.4B** (p4) ✓ · ligne **Total segments** remplie ($81.6B, 100%, p8) ✓
- "Not disclosed" : **7** (restants légitimes : revenue estimate sans consensus, guidance non publiée)
- `deep_dive_validation.json` écrit, `passed: true` ✓
- Press release : toujours "Unavailable" (honnête, multi-query n'a pas trouvé pour NVDA)

## Travail du soir (3 commits, déployés)
1. `0a60848` fix(sa): résolution label fiscal — `_is_forward_quarter` rejetait "FY2027 Q1" (année fiscale comparée à l'année calendaire) ; `_resolve_deep_dive_quarter` préfère désormais `yf_data.financials.fiscal_period_label` (doctrine mapper) ; `_period_from_filing` rend un tag calendaire honnête (`2026Q1`) au lieu d'usurper `FY2026 Q1`
2. `0ec1171` test(sa): test d'intégration rendu hermétique (comparison + fetch trimestre mockés, Verdict fake avec HOLD explicite, eps_estimate fake pour le gate consensus) + test B14 aligné sur la règle raffinée a813f33 (snapshot eps_yoy = fallback même-base valide)
3. `f7a3fc7` feat(sa): `scripts/render_deep_dive_from_md.py` — re-render un PDF depuis le md existant SANS re-payer le LLM (miroir du bloc de rendu de GET /api/report/{ticker}/pdf, backup du PDF existant, validation two-stage)
4. Cache yahoo NVDA reseedé (était empoisonné par le fetch dégradé de 18h53 — le piège exact du handoff précédent)
5. PDF du dossier 18h53 re-rendu en place avec le bon titre, servi par l'API (200, 332413 B)

## PREMIÈRE ACTION DE LA PROCHAINE SESSION
Rien d'urgent en attente. À la prochaine génération deep-dive (n'importe quel ticker) :
- confirmer que le titre fiscal est correct DÈS la génération (le fix 0a60848 n'a été prouvé qu'en re-render)
- observer si le press release multi-query trouve enfin une source ("trouvée" jamais observée à ce jour)

## Pièges appris ce soir
- Un dossier PLUS RÉCENT peut supplanter celui du handoff — toujours vérifier `/api/dossier/{ticker}/status` (champ `directory`) avant de travailler un dossier
- `_is_forward_quarter` : ne jamais comparer une année fiscale (FY2027) à l'année calendaire — NVDA/AAPL tournent jusqu'à 1 an en avance
- Une passe manuelle `generate_deep_dive` avec `output_dir` pointant sur `07_final_report` crée un `07_final_report/07_final_report/` imbriqué ET ne rend pas le PDF (le rendu vit dans l'endpoint, pas dans le generator)
- L'endpoint GET pdf ne re-render JAMAIS depuis un md existant : il régénère tout (LLM) ou refuse (422). D'où `scripts/render_deep_dive_from_md.py`
- pypdf extrait les tables en colonne-major — vérifier les valeurs par recherche de substrings, pas par lignes
- `logs/pipeline.log` avec "Canonical analyses dir" répété toutes les ~6 s = un 2e process importe backend.main (ici : double unité systemd sur le même port)

## Restants connus (non bloquants)
- Press release "Unavailable" pour NVDA (comportement honnête voulu)
- Revenue estimate "Not disclosed" (pas de consensus externe disponible)
- Dossier `2026-06-12_140805_NVDA` : artefacts de la passe 15h59 remis en place (étaient imbriqués), pas de PDF — supplanté par 185336, aucune action requise
- JP : génération séparée EN/JP décidée (pas de bilingue) — modèle Nami `docs/specs/modele.pdf`
