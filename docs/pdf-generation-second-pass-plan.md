# Plan seconde passe - fidélité PDF et revue qualité

Date : 2026-05-06

## Objectif

Amener le pipeline vers un PDF final réellement conforme au modèle, avec :

- traduction par Codex local uniquement ;
- documents du ZIP cohérents avec la langue demandée ;
- PDF deep-dive non dégradé par la conversion Markdown ;
- polices proches du modèle ;
- traçabilité provider correcte ;
- base saine pour la prochaine passe "tous les chiffres attendus".

## Corrections réalisées dans cette passe

1. Traduction Codex stricte
   - `backend/translator.py`
   - Ajout `TranslationUnavailableError`.
   - `translate_text(..., strict=True)` échoue si Codex ne produit pas de traduction.
   - `backend/main.py` utilise le mode strict pour les ZIP non anglais.

2. Protection du PDF deep-dive structuré
   - `backend/main.py`
   - Ajout `_should_convert_dossier_text_to_pdf`.
   - `earnings_deep_dive.md` ne peut plus écraser `earnings_deep_dive.pdf` si le PDF structuré existe.

3. Polices modèle
   - `backend/earnings_deep_dive/pdf_renderer.py`
   - Résolution de `Arial`, `Arial-Bold`, `MS-PGothic` depuis assets ou polices Windows locales.
   - Fallback conservé si police indisponible.

4. Traçabilité provider
   - `backend/earnings_deep_dive/generator.py`
   - Meta passée à `Codex CLI local`.

5. Sécurité provider Codex
   - `backend/codex_provider.py`
   - Remplacement de `tempfile.mktemp` par `tempfile.mkstemp`.

## Tests ajoutés ou renforcés

- `tests/test_translator.py`
  - Codex local utilisé.
  - Fallback non strict conservé.
  - Mode strict échoue si Codex indisponible.

- `tests/test_dossier_language_zip.py`
  - Le PDF deep-dive structuré n'est pas écrasé.
  - Les Markdown classiques restent reconvertis en PDF après traduction.

- `tests/test_earnings_pdf_renderer.py`
  - Résolution des polices modèle.

- `tests/test_codex_provider.py`
  - Interdiction de `mktemp`.

- `tests/test_earnings_deep_dive.py`
  - Meta provider Codex.

## Prochaine passe obligatoire pour "en tous points identique"

1. Renderer de layout fidèle au modèle
   - Reproduire les 14 pages du modèle, pas une page par section.
   - Utiliser les positions/tailles/couleurs extraites de `pdf-analysis.json`.
   - Caler marges 72 pt et typographies page par page.

2. Matrice de données complète
   - Lister tous les chiffres attendus par section.
   - Mapper les champs existants.
   - Ajouter champs manquants au DTO uniquement si source disponible.
   - Toute donnée absente doit rester explicitement non disponible.

3. ZIP language-native
   - Générer les PDFs structurés directement dans la langue demandée.
   - Éviter de dépendre d'une traduction Markdown pour les documents critiques.

4. Tests visuels
   - Ajouter assertions sur nombre de pages cible, polices, sections par page et seuils de diff.

5. Revue exhaustive post-conformité
   - Qualité code.
   - Sécurité.
   - Tests.
   - Données financières.
   - Gaps métier.
   - Maintenabilité.
