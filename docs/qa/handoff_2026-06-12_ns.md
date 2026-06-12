# NS Handoff — 12/06/2026 (session marathon SA pipeline)

## État au moment du handoff
- **Backend prod** : `1f17bde` servi (local + sa.cedlabusa.net), service `sa-backend` actif
- **Branche** : `kanban/spec-fonctionnelle-sa`, working tree propre (hors dossiers non suivis d'autres agents)
- **EN COURS** : dernière passe « pro » NVDA quarter=2026Q2 déclenchée ~16h05, génération LLM active
  (artefacts précédents dans `analyses/2026-06-12_140805_NVDA_NVIDIA_Corp/07_final_report/bak.pro/`)

## PREMIÈRE ACTION DE LA PROCHAINE SESSION
Vérifier le PDF final (`analyses/2026-06-12_140805_NVDA_NVIDIA_Corp/07_final_report/earnings_deep_dive.pdf`) :
- titre FY2027 Q1, EPS YoY rempli (~+214% GAAP), Net Cash N-1 (−42.4B), ligne Total segments remplie,
  count "Not disclosed" en forte baisse (restants légitimes = guidance non publiée)
- écrire `deep_dive_validation.json` via `validate_deep_dive(md)` (le chemin async ne l'écrit pas)
- Press Release : multi-query déployé mais pas encore observé "trouvée" — vérifier page 1/20

## Travail du jour (~27 commits, tous déployés)
1. Gate pre-render two-stage (bloque sur contenu normalisé) + verdict fallback + consensus-aware wording
2. Registry phase_set_at + feedback pipeline event loop (auto-remédiation VÉRIFIÉE en prod)
3. Mitigation répétition DeepSeek (retry temp 0.7 + salvage + statut `salvaged`)
4. 29 échecs QA P1→P3 soldés (`docs/qa/pre_existing_failures_2026-06-11.md` à jour) ; 954 tests, 0 erreur collection
5. Cookies SA : review conforme à `Desktop/cookies_status_corrections.txt` (codé par autre agent, 56/56)
6. Company overview : tofu ZWSP, revenue TTM base-mixte, backfill profil, exchange/CEO renderer
7. Deep-dive : tofu U+2011 (274×), press release quarter-aware GÉNÉRIQUE (hardcode NVDA supprimé),
   garde snapshot anti-dégradation (ratio 70% + champs critiques nommés)
8. No-NA policy (Ced) : EPS YoY date-match + fallback GAAP, Net Cash via LT+Current debt,
   Total segments dérivé, backlog reformulé — TOUS PROUVÉS EN LIVE, à confirmer dans le PDF final

## Pièges appris aujourd'hui
- `pytest | tail` masque l'exit code → TOUJOURS `set -o pipefail`
- GET /api/report/.../pdf ne régénère QUE si le PDF est absent du dossier résolu (mv → bak d'abord)
- Le cache yahoo peut être empoisonné par un fetch dégradé → reseed via `get_yahoo_data()` direct
- Insérer une clé dans `current_values` de `_extract_quarterly_comparison` désynchronise l'appariement
- `analyses/tmp*` = résidus tests (conftest nettoie) ; DeepDiveRequest VALIDE output_dir sous analyses/
- earnings_history yfinance = 4 trimestres SANS le year-ago → match par date, pas par index

## Restants connus (non bloquants)
- Press release "Unavailable" si la recherche ne trouve pas la bonne période (comportement honnête voulu)
- Cellules guidance non publiées par la société = légitimes
- `_generate_section` (generator.py) = code mort sans appelant
- JP : génération séparée EN/JP décidée (pas de bilingue) — modèle Nami `docs/specs/modele.pdf` (emojis ✓)
