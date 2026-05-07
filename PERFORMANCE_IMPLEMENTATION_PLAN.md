# Plan d'implementation securise

## Garde-fous

- Aucun chiffre de gain ne sera annonce sans mesure avant/apres.
- Les corrections de tests fonctionnels existants ne doivent pas etre confondues avec les optimisations.
- Les changements doivent rester petits et reversibles.
- Ne pas toucher au comportement metier, aux contrats publics ni aux donnees financieres.

## Iteration 1 : Quick win import/cold start

Objectif : reduire le cout de `import backend.main`.

Fichiers candidats :

- `backend/earnings_deep_dive/__init__.py`
- `backend/main.py`
- `backend/pipeline.py`

Approche :

1. Remplacer les imports top-level du package `backend.earnings_deep_dive` par des imports directs/lazy.
2. Eviter que `pdf_renderer.py` et `generator.py` soient charges par simple import API quand l'endpoint deep-dive n'est pas appele.
3. Conserver les schemas necessaires a FastAPI depuis `backend.earnings_deep_dive.schemas`.

Verification :

```bash
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && /usr/bin/time -f 'elapsed=%e user=%U sys=%S maxrss=%MKB' .venv/bin/python -c 'import time; t=time.perf_counter(); import backend.main; print(f\"import_backend_main_seconds={time.perf_counter()-t:.3f}\")'"
```

Critere :

- Gain positif mesure sur import.
- Pas de nouvelle regression sur tests endpoints/orchestrator au-dela des echecs deja connus.

## Iteration 2 : Quick win font/PDF

Objectif : eviter de recalculer/rescanner les fonts sur chaque rendu PDF dans un meme process.

Fichier candidat :

- `backend/earnings_deep_dive/pdf_renderer.py`

Approche :

1. Memoizer le resultat de `resolve_pdf_fonts`.
2. Ne pas modifier le rendu visuel, sauf correction deja presente dans le workspace.

Verification :

```bash
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && /usr/bin/time -f 'elapsed=%e user=%U sys=%S maxrss=%MKB' .venv/bin/python scripts/generate_sample_earnings_pdf.py"
```

Critere :

- Gain positif ou neutre.
- Tests PDF renderer lances ; echecs existants documentes.

## Iteration 3 : Ne pas implementer tout de suite

A repousser sans benchmark HTTP/reseau :

- Parallelisation transcript providers.
- Refactor queue/job pour batch et dossier.
- Manifest complet de dossier.
- Cache SEC persistant.

Raison :

Ces changements peuvent modifier la semantique source, les garanties de download ou la charge provider externe. Ils necessitent des benchmarks HTTP et des tests mocks plus complets.

## Benchmarks apres chaque iteration

1. Reprendre la baseline import backend.
2. Reprendre la baseline PDF sample.
3. Relancer tests cibles.
4. Reporter les echecs existants separement.
5. Produire `PERFORMANCE_RESULTS.md`.

