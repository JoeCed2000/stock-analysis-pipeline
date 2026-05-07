# Backlog d'optimisation priorise

| Priorite | Optimisation | Gain estime | Effort | Risque | Preuve | Tests requis | Decision |
|----------|--------------|-------------|--------|--------|--------|--------------|----------|
| P0 | Lazy-import du package deep-dive/PDF pour reduire import `backend.main` | Eleve sur cold start/tests ; objectif mesure import avant/apres | Moyen | Moyen | Import `backend.main` 10,769 s ; cProfile imports 1,75 s | `pytest tests/test_main_endpoints.py tests/test_orchestrator.py`, mesure import | Quick win sur |
| P0 | Memoization de `resolve_pdf_fonts` | Faible/moyen sur generation PDF repetee | Faible | Faible | cProfile `resolve_pdf_fonts` 0,184 s pour 2 appels | Tests PDF renderer + benchmark sample PDF | Quick win sur |
| P1 | Ne pas traiter batch pending dans le status endpoint | Eleve en prod | Moyen | Moyen | `batch_status` appelle `to_thread(_process_batch)` dans la requete | Tests batch endpoint avec mock lent | Optimisation moyenne |
| P1 | Manifest d'artefacts dossier pour limiter `rglob` | Moyen maintenant, fort avec croissance | Moyen | Moyen | 741 fichiers, 9 `rglob` | Tests dossier status/download/list | Optimisation moyenne |
| P1 | Pre-generation PDF/ZIP hors download | Fort pour UX download | Moyen/eleve | Moyen | `dossier_download` convertit et zippe dans la requete | Tests download, tests langue, benchmark zip | Optimisation moyenne |
| P2 | Parallele borne transcript providers publics | Potentiellement fort en reseau reel | Moyen | Eleve | Tests transcript dominent 4,07/2,18/1,29 s ; providers en fallback | Tests source priority + timeout | Avec precautions |
| P2 | Cache CIK/SEC submissions | Moyen/fort en reseau reel | Moyen | Faible/moyen | SEC CIK resolu dans plusieurs fonctions | Tests SEC avec mocks | Bon ROI |
| P3 | Queue/worker persistant pour dossier/deep-dive | Tres fort structurel | Eleve | Eleve | Analyse/download melangent job lourd et HTTP | Tests integration + migration UX | Refactor lourd |
| P4 | Micro-optimisations de chaines/tableaux PDF | Faible | Variable | Faible | Rendu PDF pur 0,342 s | Benchmark PDF | A eviter pour le moment |

