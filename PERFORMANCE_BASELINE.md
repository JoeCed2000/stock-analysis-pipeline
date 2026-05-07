# Baseline performance

## Environnement de mesure

- OS hote : Windows, execution projet via WSL Ubuntu quand necessaire.
- Dossier : `C:\Users\cedon\Documents\Codex\stock-analysis-pipeline`.
- Date de mesure : 2026-05-07.
- Reseau : aucun endpoint externe volontairement appele pendant les benchmarks. Les mesures sont locales/offline.
- Etat du depot : sale avant audit ; les resultats incluent cet etat courant.

## Commandes et resultats bruts

### 1. Generation PDF d'exemple

Commande :

```bash
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && /usr/bin/time -f 'elapsed=%e user=%U sys=%S maxrss=%MKB' .venv/bin/python scripts/generate_sample_earnings_pdf.py"
```

Resultat :

```text
Generated reports/generated/final-report-en.pdf
Generated reports/generated/final-report-jp.pdf
Generated reports/generated/final-report.pdf
elapsed=1.91 user=0.41 sys=0.18 maxrss=68216KB
```

Lecture :

- Le rendu de l'echantillon est stable et local.
- La memoire max observee est d'environ 68 MB.
- Cette mesure ne couvre pas les appels reseau ni l'IA, seulement generation fixture/PDF.

### 2. Profil cProfile de la generation PDF d'exemple

Commande :

```bash
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && .venv/bin/python -m cProfile -s cumtime scripts/generate_sample_earnings_pdf.py | head -60"
```

Resultat cle :

```text
1057675 function calls in 2.107 seconds
importlib _find_and_load: 1.752 s cumule
pdf_renderer.py import: 0.874 s
generator.py import: 0.771 s
schemas.py import: 0.696 s
render_earnings_deep_dive_pdf: 0.342 s pour 2 appels
resolve_pdf_fonts: 0.184 s pour 2 appels
posix.stat: 0.800 s cumule
```

Lecture :

- Le cout dominant est l'import/resolution de modules, pas le rendu PDF pur.
- Les `stat` filesystem et la resolution de fonts/imports sont visibles.
- Hypothese forte : les imports top-level du package deep-dive degradent aussi le demarrage API.

### 3. Import backend FastAPI

Commande :

```bash
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && /usr/bin/time -f 'elapsed=%e user=%U sys=%S maxrss=%MKB' .venv/bin/python -c 'import time; t=time.perf_counter(); import backend.main; print(f\"import_backend_main_seconds={time.perf_counter()-t:.3f}\")'"
```

Resultat :

```text
import_backend_main_seconds=10.769
elapsed=11.04 user=1.75 sys=1.22 maxrss=100536KB
```

Lecture :

- Le temps de demarrage/import de l'application est tres eleve pour un service FastAPI.
- La memoire max observee est d'environ 100 MB des le chargement.
- Ce cout affecte le cold start, la collection pytest et tout worker qui importe `backend.main`.

### 4. Tests cibles PDF/transcript/dossier

Commande :

```bash
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && .venv/bin/python -m pytest tests/test_earnings_pdf_renderer.py tests/test_pdf_model_validation.py tests/test_transcript_finder.py tests/test_async_dossier.py --durations=20 -q"
```

Resultat :

```text
3 failed, 13 passed in 13.76s
Slowest:
4.07s test_find_transcripts_uses_rapidapi_as_primary
2.18s test_find_transcripts_falls_back_to_alpha_vantage_when_rapidapi_empty
1.29s test_find_transcripts_falls_back_to_fool_when_structured_sources_fail
0.82s test_pdf_validation_blocks_generic_phrases_and_empty_tables
0.79s test_pdf_validation_passes_structured_fixture_with_model_categories
```

Echecs observes :

- `test_pdf_renderer_generates_extractable_text_and_tables` : libelle source Seeking Alpha attendu non extrait.
- `test_pdf_renderer_generates_language_specific_japanese_report` : texte japonais attendu non extrait.
- `test_pdf_validation_passes_structured_fixture_with_model_categories` : URL transcript non detectee + page count 4 vs 14.

Lecture :

- Les tests transcript dominent les temps de cette selection.
- Les echecs PDF sont un risque de regression fonctionnelle existant, a traiter hors optimisation ou avec prudence si les changements touchent le renderer.

### 5. Tests endpoints/orchestration

Commande :

```bash
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && .venv/bin/python -m pytest tests/test_main_endpoints.py tests/test_orchestrator.py --durations=20 -q"
```

Resultat :

```text
1 failed, 3 passed in 16.08s
Slowest test body: 0.20s
Failure: dossier_download retourne 409 car download_enabled/verifie manquant dans le mock de statut.
```

Lecture :

- Le temps total du process est disproportionne par rapport aux tests eux-memes ; cela renforce le diagnostic d'import backend lourd.
- Il existe une regression/test mismatch sur le gate de download verifie.

### 6. Tests dossier/integration/coverage

Commande :

```bash
wsl.exe --% -d Ubuntu -e sh -lc "cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && .venv/bin/python -m pytest tests/test_dossier_language_zip.py tests/test_integration.py tests/test_coverage_gaps.py --durations=20 -q"
```

Resultat :

```text
Timeout apres 184 s.
```

Lecture :

- Le groupe n'est pas exploitable comme test rapide de regression dans l'etat actuel.
- Il faut isoler les tests qui declenchent reseau/generation lourde ou ajouter des mocks/timeouts plus stricts.

### 7. Comptage statique des zones I/O/reseau/concurrence

Commande :

```powershell
$patterns=@('http\.get','requests\.','yf\.Ticker','finnhub\.Client','ThreadPoolExecutor','threading\.Thread','asyncio\.to_thread','rglob\(','md_to_pdf\(','render_earnings_deep_dive_pdf','translate_text\(')
foreach($p in $patterns){ (Select-String -Path backend\*.py,backend\earnings_deep_dive\*.py,backend\sources\*.py -Pattern $p).Count }
```

Resultat :

```text
http.get: 27
requests.: 2
yf.Ticker: 4
finnhub.Client: 1
ThreadPoolExecutor: 7
threading.Thread: 1
asyncio.to_thread: 2
rglob(: 9
md_to_pdf(: 15
render_earnings_deep_dive_pdf: 5
translate_text(: 3
```

Lecture :

- Le backend a de nombreux points I/O et rendu, avec une partie deja parallele mais dispersee.
- Le risque principal est l'orchestration : trop de travail couteux dans les requetes API.

### 8. Taille locale du corpus `analyses`

Commandes :

```powershell
Get-ChildItem analyses -Recurse -File -ErrorAction SilentlyContinue | Measure-Object
Get-ChildItem analyses -Directory -ErrorAction SilentlyContinue | Measure-Object
```

Resultat :

```text
741 fichiers
45 dossiers
```

Lecture :

- Les endpoints qui scannent recursivement `analyses/` ont deja une base non triviale.
- Le cout croitra avec chaque analyse si aucun index/manifest n'est maintenu.

## Hypotheses de bottleneck

1. Imports top-level trop lourds : `backend.main` importe `orchestrator`, qui importe `pipeline`, qui importe tout le package `earnings_deep_dive`, donc ReportLab/generator/schemas des le demarrage.
2. Chemin `analyze_ticker_fast` redevenu synchrone et lourd : generation dossier, PDF, Excel, deep-dive et validation sont executes avant retour.
3. Collecte externe trop sequentielle : Finnhub/TwelveData/EODHD/yfinance/SEC/transcripts avec fallbacks en chaine et retries bloquants.
4. Download ZIP trop actif : peut declencher analyse, traduction, conversion PDF et compression en memoire dans la meme requete.
5. Scans disque recursifs repetes : `rglob` sur `analyses/` pour status, download, list, ZIP.
6. Tests/integration non bornes : certains tests ou chemins peuvent declencher des appels lourds et bloquer la suite.
7. Font/PDF resolution repetee : `resolve_pdf_fonts` apparait dans le profil PDF.

## Limites de la baseline

- Pas de benchmark HTTP p95/p99 reel : aucun serveur uvicorn lance pendant cette phase.
- Pas de reseau externe : les mesures ne couvrent pas la vraie latence Finnhub/Yahoo/SEC/LLM.
- Le depot contient des modifications preexistantes ; certains echecs de tests ne proviennent pas de cette mission.
- Les chiffres ne prouvent pas encore un gain de 15-30 %. Ils servent de base avant/apres.

