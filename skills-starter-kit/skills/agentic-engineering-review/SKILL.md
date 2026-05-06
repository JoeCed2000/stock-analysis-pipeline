---
name: agentic-engineering-review
description: "Revue de code spécifique au code généré par agents (Codex, LLM) — détecte les patterns 'gross' : bloat, copy-paste, abstractions fragiles, corrélations implicites, résistance à la simplification."
category: software-development
trigger:
  - Après toute session Codex ayant produit du code
  - Avant merge de code généré par agent
  - Sur demande explicite "agentic review"
---

# Agentic Engineering Review

Revue de code spécialisée pour le code produit par des agents (Codex, Claude Code, LLM).

## Principes (Karpathy, 2026)

> "Sometimes I get a little bit of a heart attack because it's not super amazing code necessarily all the time and it's very bloaty and there's a lot of copy paste and there's awkward abstractions that are brittle and like it works but it's just really gross."

> "Agentic engineering is about preserving the quality bar of professional software. You're not allowed to introduce vulnerabilities due to vibe coding."

## Checklist de revue

Pour chaque fichier modifié par un agent, vérifier :

### 1. Bloat
- [ ] Code inutilement verbeux ?
- [ ] Fichiers trop longs qui pourraient être splités ?
- [ ] Fonctions qui font trop de choses ?
- [ ] Commentaires évidents ou redondants ?

### 2. Copy-paste
- [ ] Blocs de code dupliqués ?
- [ ] Logique répétée au lieu d'être factorisée ?
- [ ] Strings magiques répétés ?

### 3. Abstractions fragiles
- [ ] Abstraction mal nommée ?
- [ ] Abstraction qui fuit (leaky abstraction) ?
- [ ] Classe/fonction qui fait 2 choses sans lien ?
- [ ] Over-engineering : abstraction pour 1 seul usage ?

### 4. Corrélations fragiles
- [ ] Hypothèses implicites sur les données ?
- [ ] Dépendance à l'ordre d'exécution non documentée ?
- [ ] Valeurs codées en dur (IP, URL, port) — utiliser une couche de config

### 5. Résistance à la simplification
- [ ] Le code pourrait-il être plus simple ?
- [ ] Si on demande "simplifie", l'agent y arrive-t-il ?
- [ ] Y a-t-il des étapes inutiles dans le flux ?

### 6. Détails API triviaux
- [ ] Utilisation correcte de l'API (dim vs axis, reshape vs view) ?
- [ ] Copie mémoire involontaire (view vs copy) ?
- [ ] Paramètres par défaut qui changent le comportement ?

### 7. Sécurité
- [ ] Input validé ?
- [ ] Identifiants externes validés contre source live ? Voir references/input-validation-live-check.md
- [ ] Justesse des données financières ? Voir references/financial-data-correctness.md
- [ ] Secrets exposés dans le code ?
- [ ] Dépendances introduites sans vérification ?

### 8. Tests
- [ ] Tests ajoutés pour le nouveau code ?
- [ ] Tests couvrent les cas d'erreur ?
- [ ] Tests ne sont pas eux-mêmes du "gross code" ?

### 8a. Enum / constant mapping cross-stack
Vérifier que les valeurs numériques d'enum sont identiques entre backend (Python IntEnum), API (JSON), et frontend (React constants/colors). Voir references/enum-display-mapping-pitfall.md.

### 8b. Compréhension du code (MANDATOIRE avant validation)
- [ ] Peux-tu décrire ce que chaque fichier modifié fait, en langage clair ?
- [ ] "Les tests passent" n'est pas une description. Décris le comportement.

### 9. Contrats de composants (frontend)
- [ ] Les props passées à un composant enfant existent-elles dans son interface ?
- [ ] La structure de données attendue par le frontend correspond-elle à ce que l'API renvoie ?
- [ ] Async data contradiction ? Voir references/async-data-contradiction.md

### 10. Recette visuelle & logs (frontend — MANDATOIRE)
- [ ] Page chargée via browser_navigate — pas de page blanche, pas d'erreur CORS
- [ ] browser_console() — pas d'erreur JS non catchée
- [ ] curl 200 ≠ UI fonctionnelle. Seul un snapshot/vision navigateur prouve que ça marche.
- [ ] Placeholder confusion? Voir references/placeholder-confusion.md
- [ ] NTFS Vite HMR pitfall? Voir references/ntfs-vite-hmr.md

## Niveaux de sévérité
- Bloquant / Majeur / Mineur / Info

## Workflow
1. Identifier les fichiers modifiés par l'agent
2. Pour chaque fichier, parcourir la checklist
3. Marquer chaque problème avec sévérité
4. Pour les problèmes bloquants et majeurs, exiger correction avant merge
5. Pour les mineurs, suggérer sans bloquer
6. Produire un rapport de revue concis

## Contraintes
- Cette revue ne remplace pas les tests — elle les complète
- Les problèmes bloquants sont non négociables
- Le réviseur doit justifier chaque problème majeur

## 11. Audit sécu nouveau repo
Voir references/new-repo-security-audit.md

## 12. Langue / i18n — Cohérence de la langue de surface
Toute surface visible (UI, rapports, PDF, données API) doit être dans UNE seule langue. Jamais un mix FR/EN.

## 13. Revue systématique post-portage
Voir references/systematic-review-table-template.md et references/cross-codebase-functional-audit.md

## 14. Frontend layout patterns
Grid > Flexbox pour hauteurs égales. SVG rotated labels: éviter overflow:visible. Voir references/svg-bar-label-spacing.md

## 15. Pre-modification Checklist (MANDATORY)
Backup du fichier avant toute modification: cp fichier fichier.bak

## 16. Pre-push Checklist (MANDATORY)
- Tous les fichiers dans git status sont intentionnels
- Aucun secret dans le diff
- .env et fichiers binaires dans .gitignore
- Au moins une vérification (curl, test suite, browser snapshot)

## 17. Rate limiter design review
- Memory bound (max size + periodic cleanup)
- Whitelist pour health/debug/metrics
- Pas de time.sleep() en async — utiliser asyncio.sleep()
- Test 429 behavior

## 18. Translation / i18n mutation pitfall (CRITICAL)
GET requests must NEVER mutate persistent state. Tout endpoint GET avec ?lang= doit travailler sur une COPIE temporaire.

## 19. Currency / financial data correctness
- Vérifier direction conversion (multiply vs divide)
- Currency guard: ne pas convertir des montants déjà dans la devise cible
- Percentage normalization: Finnhub retourne des pourcentages bruts (15.3), pas des décimales (0.153)

## 20. Double generation / background thread race
- Check if files already exist before spawning background generation
- Atomic writes: écrire dans un fichier temporaire puis rename

## 21. requests → httpx migration pitfalls

When migrating from requests to httpx, check these common failure modes.
Full checklist and 8 real cases in references/httpx-migration-pitfalls.md.

**Bulk migration not done until audit script passes:**
```bash
bash /home/ced/.hermes/skills/software-development/agentic-engineering-review/scripts/audit_http_imports.sh
```

Quick-hits:
- Function-scope imports forgotten: NameError swallowed by broad except
- _source/audit fields not set on cache-hit or fallback return paths
- __import__("httpx").TimeoutException workaround: use explicit import httpx
- http2=True without h2 package: ImportError at client creation
- Mock targets not migrated: patch("requests.get") to patch("backend.http_client.http.get")
- Exception types: requests.Timeout to httpx.TimeoutException, requests.RequestException to httpx.RequestError
- Stale comments referencing HTTP/2 or requests
- Unused from backend.http_client import http left behind

### Audit field completeness (cross-path TDD)

Any pipeline that adds a traceability field like `_source` must set it on EVERY return path.
Cache hit, pure fallback, main path, error path — all must set the field.
A field set only on the happy path creates silent audit gaps.

**Rule**: New field in a function with >=3 return paths → RED test first that verifies the field on ALL paths.

## 22. Cross-model mandatory audit

Règle: ne jamais reviewer avec le même modèle que le codeur.
Un second modèle (Codex/GPT-5.5, Claude, Gemini) doit challenger chaque audit.
Voir skill codex-second-opinion et references/cross-model-audit-case-study.md

---

*Skill version 2.5.0 — updated 2026-05-05 with S21 (httpx migration pitfalls)*