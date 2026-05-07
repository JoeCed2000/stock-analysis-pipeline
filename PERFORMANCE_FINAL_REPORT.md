# Rapport final performance

## Resume executif

L'audit a identifie les principaux risques performance du projet : imports backend tres lourds, pipeline d'analyse redevenu synchrone, fallbacks reseau sequentiels, download dossier trop actif, scans disque repetes et tests integration non bornes.

Deux quick wins mesures ont ete appliques :

- lazy-import des modules deep-dive/PDF ;
- cache de resolution des polices PDF.

Gains mesures :

- import `backend.main` : 10,769 s -> 9,335 s, soit 13,3 % ;
- generation PDF sample : 1,91 s -> 1,73 s, soit 9,4 % ;
- profil cProfile sample : 2,107 s -> 1,714 s, soit 18,7 %.

Le gain global cible de 15-30 % sur le pipeline complet n'est pas prouve. Il faudra benchmarker le chemin reseau/IA complet avec mocks ou environnement autorise avant toute affirmation.

## Baseline

Les mesures brutes sont documentees dans `PERFORMANCE_BASELINE.md`.

Preuves principales :

- import backend : 10,769 s avant optimisation ;
- cProfile PDF : imports majoritaires, 1,75 s sur 2,107 s ;
- generation PDF sample : 1,91 s ;
- tests transcript dominants : 4,07 s / 2,18 s / 1,29 s ;
- groupe integration timeout apres 184 s ;
- 741 fichiers et 45 dossiers sous `analyses/`.

## Top 5 bottlenecks

1. Imports top-level deep-dive/PDF au demarrage API.
2. `analyze_ticker_fast` execute generation dossier/PDF/Excel/deep-dive synchronement.
3. Collecte externe en chaine avec retries/fallbacks bloquants.
4. Download dossier qui peut traduire, convertir et zipper dans la requete.
5. Scans disque recursifs et absence de manifest d'artefacts.

## Optimisations appliquees

| Fichier | Changement | Justification |
|---|---|---|
| `backend/earnings_deep_dive/__init__.py` | Exports lourds rendus lazy via `__getattr__` | Eviter de charger generator/mapper/pdf_renderer au simple import |
| `backend/main.py` | Import direct des schemas deep-dive ; `generate_deep_dive` importe localement | Reduire cold start FastAPI |
| `backend/pipeline.py` | Import direct des schemas ; generator/mapper/renderer importes seulement dans la generation deep-dive | Eviter de charger ReportLab et generator sur import pipeline |
| `backend/earnings_deep_dive/pdf_renderer.py` | `resolve_pdf_fonts` decore avec `@lru_cache(maxsize=4)` | Eviter resolution/registration fonts repetee dans un meme process |
| `tests/test_performance_imports.py` | Tests de non-regression import/cache | Verrouiller le gain et eviter retour aux imports lourds |

## Optimisations non appliquees

- Parallelisation transcript providers : risque de changer la priorite source et de surcharger des providers externes.
- Queue/job runner : changement architectural plus large.
- Manifest complet dossier : bon ROI, mais necessite tests fonctionnels download/status.
- Cache SEC/transcript : necessite politique TTL/provenance.

## Parallelisation

Deja presente :

- `run_analysis_parallel` par ticker, max 4 workers.
- Finnhub fetch en parallele de l'extraction 10-K.
- Traduction de fichiers en pool borne a 4.

Candidates :

- sources financieres independantes avec bulkhead ;
- transcript discovery avec score de qualite/source ;
- generation PDF secondaires hors requete ;
- batch/deep-dive via worker.

Non recommande sans refonte :

- `parallelStream` equivalent ou parallelisation ad hoc dans le chemin HTTP ;
- parallelisation sans rate limit des providers externes ;
- download ZIP qui demarre de nouveaux travaux lourds.

## Resultats chiffrés

Voir `PERFORMANCE_RESULTS.md` pour le tableau avant/apres.

Le gain est positif mais partiel. Les optimisations restantes les plus prometteuses sont architecturales, pas des micro-optimisations.

## Verification

Commandes qui passent :

```text
pytest tests/test_performance_imports.py -q
2 passed in 8.99s
```

```text
py_compile backend/earnings_deep_dive/__init__.py backend/main.py backend/pipeline.py backend/earnings_deep_dive/pdf_renderer.py tests/test_performance_imports.py
exit 0
```

Commandes avec echecs/limites :

```text
pytest tests/test_performance_imports.py tests/test_main_endpoints.py tests/test_orchestrator.py -q
1 failed, 5 passed in 17.21s
```

```text
pytest tests/test_earnings_pdf_renderer.py tests/test_pdf_model_validation.py --durations=20 -q
3 failed, 3 passed in 6.64s
```

```text
python -m compileall backend tests
timeout apres 184 s
```

## Risques restants

- Les echecs PDF/validation preexistants doivent etre corriges pour revenir a une base verte.
- Le test endpoint download doit etre aligne avec le gate `download_enabled`.
- Les performances reseau/IA reelles ne sont pas encore mesurees.
- Le workspace reste sale avec beaucoup de changements hors mission performance.

## Prochaines etapes recommandees

1. Corriger les echecs fonctionnels existants PDF/download gate.
2. Ajouter une instrumentation par etape dans `analyze_ticker_fast`.
3. Creer un benchmark HTTP local avec mocks lents pour `/api/analyze`, `/api/dossier/status`, `/api/dossier/download`.
4. Sortir la generation dossier/deep-dive du chemin synchrone HTTP.
5. Ajouter un manifest d'artefacts verifies pour remplacer les scans recursifs repetes.

