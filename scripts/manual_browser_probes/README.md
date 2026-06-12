# Manual browser probes — Seeking Alpha access

Scripts d'exploration manuelle (camoufox / nodriver / patchright) pour tester
l'accès Seeking Alpha et le contournement PerimeterX.

**Ce ne sont pas des tests pytest** : ils s'exécutent au niveau module
(`asyncio.run(...)` à l'import) et lancent un vrai navigateur. Ils vivaient
dans `tests/` sous le préfixe `test_` et cassaient la collecte pytest
(4 erreurs de collection documentées dans
`docs/qa/pre_existing_failures_2026-06-11.md`, section « Hors inventaire »).

Usage :

```bash
source backend/.venv/bin/activate
python scripts/manual_browser_probes/camoufox_sa.py
```

Dépendances optionnelles non installées par défaut : `camoufox`, `nodriver`,
`patchright`.
