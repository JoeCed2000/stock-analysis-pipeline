# Inventaire des échecs préexistants de la suite complète — 11/06/2026

> **STATUT 12/06/2026 — INVENTAIRE SOLDÉ.** Les 29 échecs restants (32 − 3
> corrigés le 11/06) ont été traités le 12/06, ordre P1 → P3 :
> - **P1 (13)** : tests validator ×5, fixture scoring ×4, company_overview ×2
>   (`67ceaed`) ; intégration deep-dive #25 — vrai défaut produit, wording
>   beat/miss sans consensus dans le mapper (`aeafcaf`) ; harnais
>   pdf_model_validation #27 (`6e16298`).
> - **P2 (12)** : main_endpoints #20-21, quarterly flaky #23, codex #29,
>   valuation #30 (`be53fc8`) ; translator #28 — alias `ja` produit
>   (`7095228`) ; integration #18-19, smoke API #10-12, smoke live #13-15
>   (`7c37f91`).
> - **P3 (2)** : performance #31 — vraie régression cold-start corrigée,
>   yfinance lazy dans market_data (`f75ad7d`) ; camoufox #32 + les 4 scripts
>   navigateur hors-inventaire déplacés vers `scripts/manual_browser_probes/`
>   (`bc3985d`) — `pytest tests/` collecte 954 tests sans erreur.
> - Les smoke live (#10-15) s'auto-skippent sans backend joignable et exigent
>   `SA_RUN_LIVE_SMOKE=1` pour les chemins qui déclenchent de vraies
>   générations LLM.

## Contexte

Comparaison de deux runs complets de `pytest tests/` (hors 4 scripts navigateur
`test_nodriver_sa.py`, `test_patchright_*.py` qui échouent à la collecte) :

| Run | Code | Résultat |
|---|---|---|
| Baseline | `f2d0f5c` (worktree propre) | 38 failed, 832 passed, 7 skipped |
| Hotfix NVDA | working tree pré-`78e75e3` | 34 failed, 846 passed, 7 skipped |

**32 échecs sont communs aux deux runs** → préexistants, non causés par le hotfix
NVDA. Les 2 seuls échecs spécifiques au hotfix (`test_pdf_commentary` format
verbeux obsolète) ont été corrigés dans `78e75e3`. Aucun des 32 ne bloque le
chemin critique NVDA (deep-dive, renderer, validation markdown, mapping
EPS/revenue/net cash, label FY2027 Q1, saut de page Sources) — les 3 qui le
touchaient ont été corrigés dans `78e75e3` / `1d99db1` (voir statuts).

**Recommandation : traiter le reste dans une PR séparée `test/qa-regression-cleanup`,
ordre P1 → P3.** Aucun P0 (aucun échec ne reflète un défaut produit actif sur le
chemin client NVDA).

Légende : Baseline = présent sur `f2d0f5c` ; Hotfix = présent sur le working tree
hotfixé ; Impact NVDA = bloque le hotfix NVDA.

## Synthèse par catégorie

| Catégorie | Nb | Priorité | Nature dominante |
|---|---|---|---|
| validator | 5 | P1 | Assertions obsolètes vs renommage/sévérités du validateur |
| scoring fixture | 4 | P1 | Modèle `Scoring` 6 catégories vs fixture à l'ancien schéma |
| api_pipeline_smoke | 3 | P2 | 422/timeout — dérive contrat payload + jobs async réels |
| smoke live NVDA | 3 | P2 | `AnalysisResult.score` n'existe plus + réseau live |
| company_overview | 2 | P1 | Libellés provenance « Blocked » non rendus |
| integration | 2 | P2 | 422 vs 200/429 — même dérive payload que smoke |
| main_endpoints | 2 | P2 | `asyncio.get_event_loop` en thread (Python 3.12) |
| quarterly_comparison | 2 | P1/P2 | 1 corrigé (colonne Quality) ; 1 flaky ordre-dépendant |
| earnings deep-dive | 2 | P1/— | 1 intégration à trier ; 1 corrigé (meta effort) |
| pdf_commentary | 1 | — | Corrigé dans `78e75e3` (page Sources) |
| pdf_model_validation | 1 | P1 | Harnais de comparaison au modèle 14 pages en dérive |
| translator / codex_provider | 2 | P2 | Attentes prompt/défauts obsolètes |
| performance / camoufox | 2 | P3 | Parsing stdout pollué ; plugin async manquant |
| valuation_context_support | 1 | P2 | Heuristique support/mixed |

## Détail des 32 échecs

### Catégorie : validator — P1 (qualité du gate de validation, pas de défaut produit actif)

| # | Test | Erreur | Baseline | Hotfix | Impact NVDA | Prio |
|---|---|---|---|---|---|---|
| 1 | `tests/test_validator.py::TestQuarterPresence::test_quarter_none_flagged` | `assert not True` — quarter manquant est devenu warning, le test attend un échec bloquant | oui | oui | non | P1 |
| 2 | `tests/test_validator.py::TestForbiddenMarkers::test_not_available_in_section_flagged` | `assert not True` — check renommé `forbidden_marker_leak`, test cherche `not_available` | oui | oui | non | P1 |
| 3 | `tests/test_validator.py::TestForbiddenMarkers::test_data_not_available_flagged` | `_has_warning(..., "not_available", "Cash Flow")` False — même renommage | oui | oui | non | P1 |
| 4 | `tests/test_validator.py::TestForbiddenMarkers::test_french_not_available_flagged` | idem (`DONNÉE NON DISPONIBLE` flaggé sous `forbidden_marker_leak`) | oui | oui | non | P1 |
| 5 | `tests/test_validator.py::TestEdgeCases::test_all_checks_pass` | `assert 1 == 0` — nouveau warning `eps_revenue_estimate_actual_proximity` non prévu par la fixture | oui | oui | non | P1 |

Note : le validateur FONCTIONNE (il flague bien les marqueurs, avec d'autres noms
de checks/sévérités). Mettre les tests au contrat actuel, ou restaurer les noms si
le renommage était involontaire.

### Catégorie : scoring fixture — P1

| # | Test | Erreur | Baseline | Hotfix | Impact NVDA | Prio |
|---|---|---|---|---|---|---|
| 6 | `tests/test_pipeline_regression_fixture.py::TestStructuralInvariants::test_score_exists_and_in_range` | `'Scoring' object has no attribute 'profitability'` | oui | oui | non | P1 |
| 7 | `tests/test_pipeline_regression_fixture.py::TestStructuralInvariants::test_score_components_sum_to_total` | idem | oui | oui | non | P1 |
| 8 | `tests/test_pipeline_regression_fixture.py::TestStructuralInvariants::test_decision_maps_to_score_band` | idem | oui | oui | non | P1 |
| 9 | `tests/test_pipeline_regression_fixture.py::TestWarnings::test_score_above_minimum` | idem | oui | oui | non | P1 |

Note : le modèle `Scoring` est passé aux 6 catégories canoniques
(financial_health, growth, …) ; la fixture de régression utilise l'ancien schéma.

### Catégorie : api_pipeline_smoke — P2 (nécessite stack réelle ; dérive payload à confirmer)

| # | Test | Erreur | Baseline | Hotfix | Impact NVDA | Prio |
|---|---|---|---|---|---|---|
| 10 | `tests/test_api_pipeline_smoke.py::TestAPIPipelineSmoke::test_async_analyze_and_poll` | `Job 4ab2bffec7ac timed out after 180s` | oui | oui | non | P2 |
| 11 | `tests/test_api_pipeline_smoke.py::TestAPIPipelineSmoke::test_pdf_endpoint_returns_pdf` | `PDF endpoint failed: 202` (job encore en cours) | oui | oui | non | P2 |
| 12 | `tests/test_api_pipeline_smoke.py::TestAPIAnalyzeSync::test_sync_analyze_returns_result` | `assert None == 'AAPL'` | oui | oui | non | P2 |

### Catégorie : smoke live NVDA — P2 (réseau live + dérive modèle)

| # | Test | Erreur | Baseline | Hotfix | Impact NVDA | Prio |
|---|---|---|---|---|---|---|
| 13 | `tests/test_live_nvda_smoke.py::TestLiveNVDA::test_live_score_in_range` | `'AnalysisResult' object has no attribute 'score'` | oui | oui | non | P2 |
| 14 | `tests/test_live_nvda_smoke.py::TestLiveNVDA::test_live_pdf_generated` | `AssertionError: No PDF` | oui | oui | non | P2 |
| 15 | `tests/test_live_nvda_smoke.py::TestLiveNVDA::test_live_decision_maps_to_score` | `'AnalysisResult' object has no attribute 'score'` | oui | oui | non | P2 |

Note : malgré « NVDA » dans le nom, ces tests valident l'ancien pipeline
d'analyse complet (score/décision), pas le deep-dive earnings — aucun lien avec
le hotfix.

### Catégorie : company_overview — P1 (libellés provenance client-facing)

| # | Test | Erreur | Baseline | Hotfix | Impact NVDA | Prio |
|---|---|---|---|---|---|---|
| 16 | `tests/test_company_overview_pdf.py::TestCompanyOverviewPdfCanonicalProvenance::test_canonical_metric_ignores_legacy_financial_value_when_provenance_blocks` | `'Under review' == 'Blocked: mismatch_blocked'` | oui | oui | non | P1 |
| 17 | `tests/test_company_overview_pdf.py::TestCompanyOverviewPdfCanonicalProvenance::test_kpi_renderer_uses_provenance_without_hidden_yahoo_fallback` | `'Blocked: mismatch_blocked'` absent du tableau KPI rendu | oui | oui | non | P1 |

Note : hors chemin NVDA earnings (le mode earnings-focus retire la company
overview des PDF earnings), mais touche les libellés de provenance d'autres PDF.

### Catégorie : integration — P2

| # | Test | Erreur | Baseline | Hotfix | Impact NVDA | Prio |
|---|---|---|---|---|---|---|
| 18 | `tests/test_integration.py::TestAnalyzeEndpoint::test_analyze_handles_missing_data_gracefully` | `assert 422 == 200` | oui | oui | non | P2 |
| 19 | `tests/test_integration.py::TestRateLimit::test_rate_limit_analyze_endpoint` | `Expected 429 in responses, got: {422}` | oui | oui | non | P2 |

### Catégorie : main_endpoints — P2

| # | Test | Erreur | Baseline | Hotfix | Impact NVDA | Prio |
|---|---|---|---|---|---|---|
| 20 | `tests/test_main_endpoints.py::test_process_pdf_failure_is_idempotent_and_creates_single_task` | `RuntimeError: There is no current event loop in thread 'MainThread'` | oui | oui | non | P2 |
| 21 | `tests/test_main_endpoints.py::test_process_pdf_failure_other_statuses_still_create_tasks` | idem | oui | oui | non | P2 |

### Catégorie : quarterly_comparison

| # | Test | Erreur | Baseline | Hotfix | Impact NVDA | Prio |
|---|---|---|---|---|---|---|
| 22 | `tests/test_quarterly_comparison.py::test_cash_flow_rows_use_prior_year_yoy_and_quality` | attendait la colonne Quality supprimée par la révision client | oui | oui | **corrigé dans `78e75e3`** | — |
| 23 | `tests/test_quarterly_comparison.py::test_extract_quarterly_comparison_gracefully_handles_missing_prior_year` | `assert result["roe_prior_year"] is None` → 0.080… ; **passe en isolation** → flaky ordre-dépendant (état global pollué par un autre test) | oui | oui | non | P2 |

### Catégorie : earnings deep-dive

| # | Test | Erreur | Baseline | Hotfix | Impact NVDA | Prio |
|---|---|---|---|---|---|---|
| 24 | `tests/test_earnings_deep_dive.py::test_generate_deep_dive_writes_report_and_meta` | `assert 'medium' == 'low'` — attente obsolète sur l'effort par défaut | oui | oui | **corrigé dans `1d99db1`** | — |
| 25 | `tests/test_earnings_deep_dive_integration.py::test_pipeline_adds_earnings_deep_dive_when_transcript_text_exists` | `assert False is True` — le pipeline n'ajoute pas le deep-dive dans la fixture d'intégration | oui | oui | non | P1 |

Note #25 : adjacent au deep-dive mais c'est le chemin d'intégration pipeline
complet (mocké), pas la génération directe utilisée pour le PDF client NVDA —
celle-ci est couverte par `test_hotfix_acceptance.py` (14 tests) et validée par
génération réelle. À trier en premier dans la PR séparée.

### Catégorie : pdf_commentary

| # | Test | Erreur | Baseline | Hotfix | Impact NVDA | Prio |
|---|---|---|---|---|---|---|
| 26 | `tests/test_pdf_commentary.py::test_sources_start_on_their_own_page` | `Sources page not found` — Sources démarrait en milieu de page | oui | oui | **corrigé dans `78e75e3`** (PageBreak) | — |

### Catégorie : pdf_model_validation — P1

| # | Test | Erreur | Baseline | Hotfix | Impact NVDA | Prio |
|---|---|---|---|---|---|---|
| 27 | `tests/test_pdf_model_validation.py::test_pdf_validation_passes_structured_fixture_with_model_categories` | `Missing required section/category: Earnings Documents` + `page count 9 differs from model 14` — dérive structurelle du harnais vs `docs/specs/modele.pdf` ; échoue aussi avec `SA_EARNINGS_FOCUS=false` | oui | oui | non | P1 |

### Catégorie : autres — P2/P3

| # | Test | Erreur | Baseline | Hotfix | Impact NVDA | Prio |
|---|---|---|---|---|---|---|
| 28 | `tests/test_translator.py::test_translate_text_uses_local_codex_provider` | attend `'Japanese'` dans le prompt, le prompt dit `translating to ja` | oui | oui | non | P2 |
| 29 | `tests/test_codex_provider.py::test_codex_provider_defaults_to_spark_low` | attend `model_reasoning_effort=low` par défaut, le défaut est `medium` | oui | oui | non | P2 |
| 30 | `tests/test_valuation_context_support.py::test_valuation_support_stays_supportive_when_support_leads` | `'mixed' == 'supportive'` — heuristique de classement support | oui | oui | non | P2 |
| 31 | `tests/test_performance.py::test_cold_import_consistent_across_runs` | `could not convert string to float: '[main] ulimit NOFILE raised…\n0.809'` — stdout pollué par la bannière ulimit | oui | oui | non | P3 |
| 32 | `tests/test_camoufox_sa.py::test` | `async def functions are not natively supported` — plugin pytest async absent | oui | oui | non | P3 |

## Hors inventaire (rappel)

4 fichiers échouent à la **collecte** (lancement navigateur à l'import) et sont
exclus des runs : `test_nodriver_sa.py`, `test_patchright_sa.py`,
`test_patchright_sa2.py`, `test_patchright_full_flow.py`. À déplacer hors de
`tests/` ou à protéger par un skip conditionnel dans la PR séparée.
