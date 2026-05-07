# Resultats apres optimisation

## Optimisations appliquees

1. Imports deep-dive/PDF rendus lazy :
   - `backend/earnings_deep_dive/__init__.py`
   - `backend/main.py`
   - `backend/pipeline.py`

2. Resolution des polices PDF mise en cache :
   - `backend/earnings_deep_dive/pdf_renderer.py`

3. Tests de garde-fou ajoutes :
   - `tests/test_performance_imports.py`

## Mesures avant/apres

| Scenario | Avant | Apres | Gain | Commentaire |
|---|---:|---:|---:|---|
| Import `backend.main` | 10,769 s | 9,335 s | 13,3 % | Gain reel sur cold start/import pytest, mais encore trop lent |
| RSS max import backend | 100536 KB | 95772 KB | 4,7 % | Petite baisse memoire au demarrage |
| Generation PDF sample (`/usr/bin/time`) | 1,91 s | 1,73 s | 9,4 % | Gain modere ; rendu pur n'etait pas le bottleneck principal |
| Profil cProfile sample | 2,107 s | 1,714 s | 18,7 % | Mesure profiler ; imports passent de 1,752 s a 1,337 s |
| `tests/test_performance_imports.py` | 2 echecs attendus | 2 passed en 8,99 s | N/A | Verifie import lazy + cache font |

## Verification executee

```text
pytest tests/test_performance_imports.py -q
Resultat: 2 passed in 8.99s
```

```text
py_compile backend/earnings_deep_dive/__init__.py backend/main.py backend/pipeline.py backend/earnings_deep_dive/pdf_renderer.py tests/test_performance_imports.py
Resultat: exit 0
```

## Tests relances avec echecs existants

```text
pytest tests/test_performance_imports.py tests/test_main_endpoints.py tests/test_orchestrator.py -q
Resultat: 1 failed, 5 passed in 17.21s
```

Echec :

- `test_dossier_download_finds_existing_uppercase_directory_for_lowercase_request` : le mock de statut retourne `ready=True` sans `download_enabled=True`, alors que le code bloque maintenant le download non verifie.

```text
pytest tests/test_earnings_pdf_renderer.py tests/test_pdf_model_validation.py --durations=20 -q
Resultat: 3 failed, 3 passed in 6.64s
```

Echecs :

- Source Seeking Alpha candidate non extraite dans le texte PDF.
- Texte japonais `総合評価` non extrait.
- Validation fixture : URL transcript non detectee et page count 4 vs 14.

```text
python -m compileall backend tests
Resultat: timeout apres 184 s
```

## Interpretation

Le gain mesure est positif mais ne prouve pas encore un gain global de 15-30 % sur le pipeline complet. Les deux quick wins reduisent surtout le cout de demarrage/import et une partie du cout PDF local.

Le bottleneck principal restant est architectural : l'analyse, la generation dossier, la recherche transcript, le rendu PDF, la validation et parfois la traduction restent trop souvent dans des chemins HTTP synchrones.

## Decision rollback

Rollback possible facilement :

- Revenir aux imports top-level dans `backend/earnings_deep_dive/__init__.py`, `backend/main.py`, `backend/pipeline.py`.
- Retirer `@lru_cache` sur `resolve_pdf_fonts`.
- Supprimer `tests/test_performance_imports.py`.

Je ne recommande pas le rollback : les gains sont positifs, le risque fonctionnel direct est faible, et les tests de garde-fou passent.

