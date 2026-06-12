# Stock Analysis Pipeline BACKLOG

## PDF Quality
- [x] Fix Verdict empty columns in PDF — column headers aligned with data semantics (commits 869ca70, 51bed92 on kanban/verdict-empty-columns). Reviewed and approved 2026-05-13.
- [x] Fix fiscal label resolution — FY-offset companies mislabeled (NVDA "FY2026 Q1" au lieu de FY2027 Q1) ; fiscal_period_label autoritaire + tag calendaire honnête en fallback (commits 0a60848, 0ec1171, f7a3fc7 on kanban/spec-fonctionnelle-sa). Vérifié en prod 2026-06-12.
- [ ] Vérifier le titre fiscal sur la PROCHAINE génération deep-dive complète (le fix 0a60848 n'a été prouvé qu'en re-render via scripts/render_deep_dive_from_md.py).
- [ ] Press release multi-query : "trouvée" jamais observée (NVDA = Unavailable honnête) — observer sur les prochains tickers.

## Documentation
- [x] Write spec-fonctionnelle.md — 493 lines, 17 sections, French (commit 08937bb on kanban/spec-fonctionnelle-sa). Reviewed and approved 2026-05-13 (2 P1 findings noted: absolute cost claim + missing GWT criteria).
