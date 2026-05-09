# PDF Parity Gap Analysis — Codex Audit 2026-05-09

## Summary Table

| Gap | Priority | File(s) | Fix description |
|---|---:|---|---|
| Sections LLM tronquées dans le markdown puis acceptées comme `ok` | P0 | `generator.py:515-526`, validators | Ne plus tronquer silencieusement; échouer/retry si section sans fin propre |
| Guidance affiche `7499.7%` pour gross margin | P0 | `mapper.py:675-682` | Utiliser `_pct(gross_margin)` au lieu de `float(gm)*100` |
| Données contradictoires entre tables déterministes et prose LLM | P0 | `mapper.py:1305-1481`, `generator.py`, `prompts.py` | Reconciler ou supprimer les claims LLM qui contredisent les valeurs validées |
| Source transcript/cover incorrecte: DuckDuckGo vs Seeking Alpha | P0 | `generator.py:380-416`, `mapper.py:1491-1518`, `pdf_renderer.py:366-420` | Normaliser les sources |
| Questions de section absentes dans le PDF généré | P1 | `pdf_renderer.py:603-620` | ✅ FIXÉ — Rendre `section.question` en dark red |
| Emoji/markers inline supprimés: `👉🧠🎯📌■✔⚠️①` | P1 | `pdf_renderer.py:277-331` | Préserver les markers textuels |
| Prose aplatie en paragraphes massifs | P1 | `pdf_renderer.py:627-629` | Parser les lignes markdown et rendre bullets séparés |
| Geographic Segments extra; modèle l'intègre dans Segments | P1 | `template.py`, `mapper.py:580-593` | Fusionner geographic dans Segments |
| Verdict extra absent du modèle cible | P1 | `template.py`, `mapper.py` | Rendre optionnel |
| Cover différent du modèle | P1 | `pdf_renderer.py:594-601` | Aligner page 1 sur modèle |
| Page count: 9 vs 14 | P1 | `pdf_renderer.py:601-645` | Ajuster page breaks |
| Textes de table/URLs coupés | P1 | `pdf_renderer.py:454-509` | Éviter troncature destructive |
| Footers page number absents du modèle | P2 | `pdf_renderer.py:512-517` | Désactiver footer ou rendre optionnel |
| HR après chaque section non aligné modèle | P2 | `pdf_renderer.py:641-644` | Limiter les séparateurs |
| Styles: couleurs/fonts/spacing | P2 | `pdf_renderer.py:205-274` | Aligner sur modèle |

## Key Findings

- Model PDF: 14 pages, 421KB, rich markers (👉×88, 🧠×10, 🎯×5, ■×16, ✔×7)
- Generated PDF: 9 pages, 219KB, no markers preserved (only ●×52)
- Root cause is split between renderer and LLM prompt/mapper

## Ordered Fix Sequence

1. ✅ P0 data safety: fix gross margin guidance
2. P0: prevent truncated sections, add anti-contradiction validation
3. ✅ P1: render questions dark red
4. P1: preserve inline markers and markdown line breaks
5. P1: restructure sections (merge Geographic, optional Verdict)
6. P1: fix cover/source block
7. P1: adjust page breaks, footer, HR
8. P2: verify final PDF matches model
