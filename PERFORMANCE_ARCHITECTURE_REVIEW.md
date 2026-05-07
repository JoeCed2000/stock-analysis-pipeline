# Revue architecture performance

## Limites structurelles actuelles

| Probleme structurel | Effort | Risque | Gain potentiel | Recommandation |
|---|---|---|---|---|
| `analyze_ticker_fast` fait encore trop de travail synchrone | Moyen/eleve | Moyen | Tres fort | Re-separer analyse rapide, generation dossier, deep-dive, validation |
| Le status batch declenche le traitement | Moyen | Moyen | Tres fort | Introduire un vrai job runner local/persistant ou background task robuste |
| Le download peut generer/traduire/convertir/zipper | Moyen/eleve | Moyen | Fort | Download doit servir des artefacts deja verifies, ou retourner 202/409 avec statut clair |
| Cache sources fragmente | Moyen | Faible/moyen | Fort en reseau reel | Cache par provider : SEC CIK/submissions, transcript search, yfinance quarter, IR links |
| Pas de manifest d'artefacts comme index | Moyen | Faible/moyen | Moyen/fort | Ecrire un manifest apres generation ; status/list/download lisent le manifest |
| Fallbacks transcript sequentiels | Moyen | Eleve | Fort en reseau reel | Parallelisation bornee avec selection deterministe par qualite/source |
| Tests integration non bornes | Moyen | Faible | Fort pour productivite | Markers slow, mocks reseau obligatoires, timeouts courts, CI separe |
| Frontend polling simple | Faible/moyen | Faible | Moyen UX | Backoff/jitter, arret sur etat terminal explicite, affichage verification detaille |

## Ce qui devrait devenir async

- Generation dossier complete.
- Generation earnings deep-dive.
- Traduction dossier.
- Conversion PDF de documents secondaires.
- Batch multi-ticker.

Le chemin HTTP devrait lancer ou consulter un job, pas porter le job complet.

## Ce qui devrait etre cache

- Resolution ticker/ISIN et existence Yahoo.
- SEC CIK et submissions.
- Yfinance quarter data.
- Resultats transcript discovery par ticker/quarter/source.
- Investor relations URL.
- Artefact PDF issu d'un MD/TXT avec hash de contenu.
- Font resolution PDF.

## Ce qui devrait etre batch/worker

- Analyses multi-tickers.
- Deep-dive IA.
- PDF/ZIP final.
- Validation visuelle/textuelle PDF.

## Dette qui limite la scalabilite

- `pipeline.py` orchestre collecte, calcul, rendu, fichiers et validation dans un seul flux.
- `main.py` contient beaucoup de logique de domaine et d'I/O au lieu de deleguer a des services metiers mesurables.
- Les erreurs reseau sont souvent avalees, ce qui rend le profiling de latence moins precis.
- Les dossiers disque sont la source de verite implicite, mais sans index robuste.

## Ordre recommande

1. Instrumentation structurée par etape : duree, source, cache hit, taille payload.
2. Job store pour generation dossier/deep-dive, meme minimal fichier JSON.
3. Manifest d'artefacts verifies.
4. Cache SEC/transcript/IR.
5. Parallelisation transcript providers avec rate limit.
6. Benchmarks HTTP locaux avec `TestClient` + mocks lents.
7. Refactor pipeline en services isolables.

