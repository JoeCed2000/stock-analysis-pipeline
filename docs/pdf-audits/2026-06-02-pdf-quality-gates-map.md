# Cartographie gates qualité PDF financier professionnel — SA Pipeline

Date: 2026-06-02
Scope: Deep Dive EN/JP + Company Overview, client-facing production PDFs.

## Résumé

Le pipeline possède déjà un `pre_render_validator.py` très riche (RULES 1-42) qui valide le contenu structuré avant rendu PDF. Cette couche ne suffit pas pour une qualité PDF professionnelle, car les défauts audités le 2026-06-01 apparaissent **après** le rendu ou sur les artefacts finaux:

- PDF JP retourné comme JSON `202 generating` au lieu d'un PDF réel.
- `NaN`, `source: yfinance`, `S1`, placeholders et traces internes visibles dans le PDF.
- Liens/sources insuffisants dans les PDF finaux.
- Company Overview incohérent avec le snapshot Yahoo local (ex: market cap NVDA delta -39.4%).
- Sections attendues absentes du texte extrait.
- Validation visuelle/screenshot absente du runtime.

Conclusion: il faut deux couches distinctes.

1. **Pre-render gate**: contenu sectionnel avant PDF (`pre_render_validator.py`).
2. **Post-render PDFQA gate**: artefact final, langage, sources, markers, pages, screenshots, cohérence chiffres (`pdf_quality_gate.py`).

## État actuel factuel

### Pre-render existant

Fichier: `backend/earnings_deep_dive/pre_render_validator.py`

- RULES 1-42 présentes.
- Tests existants: `tests/spec_v27_*.py`.
- Attention: plusieurs règles documentées comme BLOCKING sont encore partiellement en `warning`, notamment certaines règles historiques et sous-règles:
  - RULE 2 FY label: warnings.
  - RULE 3 EPS/Revenue contradictions: warnings.
  - RULE 5 forbidden markers: warning.
  - RULE 12/13/15/17/18/19/26/27/30/37/40/41: mélanges error/warning selon sous-règles.

Cette réalité contredit partiellement `docs/corrections_coverage.md`, qui dit “All gates severity=error”. La cartographie doit donc se baser sur le code vivant, pas uniquement la doc.

### Post-render manquant

Avant cette passe, aucun module runtime ne correspondait aux règles PDFQA documentées:

- Recherche `PDFQA-|pdf_quality|forbidden_counts|jp_ratio|page_char_min`: pas d’implémentation Python.
- Les règles étaient uniquement spécifiées dans `docs/pdf-audits/2026-06-01-sa-pdf-qa-gate-rules.md`.
- L’audit brut existe: `docs/pdf-audits/2026-06-01-sa-pdf-pro-qa-raw.json`.

## Gates PDF professionnel à appliquer

### PDFQA-001 — Envelope ticker

But: chaque ticker demandé doit avoir un objet d’audit et un `analysis_dir` absolu.

Bloque si:
- ticker absent;
- `analysis_dir` absent ou relatif.

### PDFQA-002 — Artefacts requis

But: chaque livraison client doit contenir `deep_en`, `deep_jp`, `company`, sauf skip explicite documenté.

Bloque si:
- artefact requis absent sans raison de skip.

### PDFQA-003 — Fichier réel et PDF valide

But: empêcher les faux PDF / JSON 202 / fichiers corrompus.

Bloque si:
- `exists=false`;
- `is_pdf=false`;
- taille trop faible (`deep_* < 10KB`, `company < 8KB`);
- erreurs d’extraction PDF présentes.

### PDFQA-004 — Page count sanity

But: détecter PDF vide/trop court/trop long.

Bloque si:
- deep EN hors 10–40 pages;
- deep JP hors 10–45 pages;
- company hors 3–12 pages.

### PDFQA-005 — Langue attendue

But: vérifier EN/JP réels, pas seulement route `lang`.

Bloque si:
- `deep_jp.jp_ratio < 0.30`;
- `deep_en.jp_ratio > 0.05`.

### PDFQA-006 — Personnalisation Nami

But: éviter fuite de personnalisation dans PDF générique.

Bloque en mode `generic` si:
- `Nami`, `Nami-san`, `Namiさん`, `Nami様` visibles.

Autorise uniquement en mode `nami_personalized` explicite.

### PDFQA-007 — Null/debug markers

But: interdire `DATA NOT AVAILABLE` et artifacts techniques visibles.

Bloque si:
- `NaN`, `null`, `None`, `undefined`, `DATA NOT AVAILABLE` visibles.

### PDFQA-008 — Labels internes/source provider

But: remplacer les labels bruts par sources lisibles.

Bloque si:
- `source: yfinance`, raw provider keys, `LLM synthesis`, `S1`/`S2` visibles en PDF client.

### PDFQA-009 — Missing-data placeholders

But: les données manquantes doivent être expliquées, pas affichées comme placeholder brut.

Bloque pour:
- `DATA NOT AVAILABLE`, `No data`, `Not available`.

Warning pour:
- `not disclosed`, `unavailable`, selon contexte.

### PDFQA-010 — Sections financières attendues

But: un PDF financier pro doit couvrir les blocs essentiels.

Bloque si deep dive manque:
- Financial Metrics;
- Valuation;
- Operating Metrics;
- Cash Flow;
- Capital Efficiency;
- Management;
- Risks;
- Sources.

### PDFQA-011 — Sources/liens

But: assurer traçabilité externe minimale.

Bloque si:
- deep dive a moins de 5 URLs;
- company overview a moins de 1 URL/source registry explicite.

### PDFQA-012 — Rendered-page smoke

But: imposer une preuve visuelle minimale pour recette.

Warning si:
- aucune page rendue PNG attachée à l’audit.

À renforcer plus tard en defect pour delivery client finale.

### PDFQA-013 — Cohérence chiffres key_financials vs source canonique

But: exactitude chiffres et cohérence avec Yahoo/local ledger.

Bloque si:
- `abs(delta_pct) > 10%` pour une métrique clé (`market_cap`, `pe_forward`, `beta`, etc.).

Exemple audit: NVDA Company Overview market cap -39.4%, P/E forward +109.8%, beta -24.2% => blocage.

## Quarterly/yearly et contradictions

Ces contrôles existent déjà majoritairement en pre-render:

- Period consistency: RULE 11.
- EPS/Revenue reconciliation: RULE 13.
- Operating metrics contradictions: RULE 16.
- Cash Flow signs: RULE 17.
- Guidance reconciliation: RULE 19.
- Verdict/valuation/data quality: RULE 21-23.
- Company Overview layer separation: RULE 32.

Risque restant: plusieurs contradictions historiques sont encore en `warning`, donc visibles potentiellement dans des PDF générés. À traiter dans `impl-1`/`pdf-1`: décider quelles sous-règles doivent redevenir bloquantes avec tests.

## Implémentation ajoutée

Module: `backend/earnings_deep_dive/pdf_quality_gate.py`

Tests: `tests/spec_v27_pdf_quality_gate.py`

Le module consomme le shape déjà produit par `docs/pdf-audits/*raw.json` et retourne:

- `PdfQualityResult.passed`
- `defects`
- `warnings`
- `allowed`
- `format_pdf_quality_result()` pour logs/API.

## Next steps

1. Exécuter tests ciblés `tests/spec_v27_pdf_quality_gate.py`.
2. Valider le module sur l’audit réel `docs/pdf-audits/2026-06-01-sa-pdf-pro-qa-raw.json`.
3. Brancher le gate dans les endpoints de téléchargement PDF ou dans la pipeline de génération selon audience mode.
4. Refaire une recette prod/browser sur tickers réels.
