# Plan de parallelisation

## 1. Parallellisable immediatement

| Zone | Code concerne | Pourquoi | Type recommande | Limite | Timeout | Erreur | Test |
|---|---|---|---|---|---|---|---|
| Multi-ticker analyse | `backend/orchestrator.py` | Deja independant par ticker | Garder `ThreadPoolExecutor`, ajouter instrumentation duree par ticker | 4 workers actuellement, configurable | Per ticker existant 1200 s a reduire selon job | Erreur par ticker sans tuer le batch | Test existant `test_orchestrator.py` + benchmark 1/2/4 tickers mockes |
| Traduction fichiers dossier | `main.py` 817-835 | Fichiers independants | Conserver pool borne | 4 max actuel | Timeout par fichier a ajouter | Stopper download si une traduction stricte echoue | Test zip langue avec mock `translate_text` lent |
| Conversion PDF fichiers independants | `main.py` 849-864 | MD/TXT independants | Possible pool borne ou pre-generation hors requete | 2-4 max selon CPU | Timeout par fichier | Continuer avec issue explicite ou bloquer selon criticite | Test avec 5 fichiers MD fixture |
| Rendu final EN/JP fixture | `scripts/generate_sample_earnings_pdf.py` | PDFs independants | Pool local si script seulement | 2 | N/A | Fail fast | Benchmark script |

## 2. Parallellisable avec precautions

| Zone | Code concerne | Precautions |
|---|---|---|
| Sources financieres | `sources_collector.get_stock_data` | Rate limits, priorite source, merge deterministe. Lancer en parallele seulement les sources independantes disponibles, avec bulkhead par provider. |
| SEC CIK + 10-K + Finnhub news | `pipeline.analyze_ticker_fast` | Finnhub est deja parallele avec 10-K. SEC CIK/filing pourrait etre cache et reutilise. Attention aux limites SEC. |
| Transcript providers | `transcript_finder.find_transcripts` | Garder ordre de preference. Lancer certains providers publics en concurrence apres echec/timeout court des sources premium, ou lancer en parallele mais choisir le meilleur selon score/source. |
| Deep-dive section generation IA | `earnings_deep_dive.generator` | Cout et limites provider. Necessite schema stable, retries, rate limit, resume partiel. |
| Batch status processing | `main.batch_status` | Ne doit pas transformer un poll en worker long. Preferer background job ou queue ; au minimum verrou par job pour eviter double execution. |

## 3. Non parallellisable actuellement

| Zone | Raison |
|---|---|
| Merge final des donnees financieres | Ordre de precedence source/cache doit rester deterministe. |
| Scoring final | Depend de donnees collectees et management tone. |
| Validation download gate | Doit rester apres generation/validation, sinon risque d'activer download trop tot. |
| ZIP streaming final | L'ordre n'est pas metier, mais l'ecriture ZIP elle-meme est un flux unique. |

## 4. A refondre architecturalement

| Zone | Refonte recommandee | Gain potentiel |
|---|---|---|
| `/api/analyze` | Separateur analyse rapide vs generation dossier/deep-dive en job persistant | Tres fort pour latence utilisateur |
| `/api/batch/{job_id}/status` | Worker/job queue au lieu de processing dans le poll | Tres fort pour stabilite et scalabilite |
| Dossier/download | Manifest d'artefacts verifies + generation prealable | Fort pour download |
| Cache sources | Cache par provider et par artefact, avec TTL et provenance | Fort en cout reseau |
| Tests integration | Markers slow + mocks stricts reseau | Fort pour CI |

