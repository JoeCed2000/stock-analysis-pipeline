# Codex Review Findings — think-in-code Skill

Review date: 2026-05-02. Two rounds: structural (10 findings) + code quality (10 findings). All fixed in final version.

## Round 1: Structural Review

| Severity | Finding | Resolution |
|---|---|---|
| CRITICAL | Pattern standard `find\|xargs\|python3 -c` non exécutable, ne transmet pas le contenu | Remplacé par `rg --json --no-messages` + Python stdlib |
| IMPORTANT | Confusion "réduire contexte" vs "préserver vérité" — pas de gestion des faux négatifs | Ajouté phase de validation, niveau de confiance |
| IMPORTANT | Seuil ">3 read_file" trop mécanique | Remplacé par règle décisionnelle (répétitif, filtrable, vérifiable) |
| IMPORTANT | Contraintes sécurité insuffisantes (pas d'exclusions, timeout, redaction) | Ajouté exclusions, timeout 30s, redaction, pas d'import applicatif |
| IMPORTANT | Règle "pas de lecture .env, secrets, auth" ambiguë | Distingué "ne pas afficher secrets" vs "analyser code auth OK" |
| IMPORTANT | Recommande regex/shell sans mentionner AST/tree-sitter | Ajouté stratégie d'outillage (rg→découverte, AST→conclusion) |
| IMPORTANT | Contradiction "1 script unique" vs workflow réel multi-étapes | Clarifié : 2 étapes max (search_files → execute_code) |
| MINOR | Claims de référence trop assertifs | Adouci en "approche recommandée dans certains workflows" |
| MINOR | Vérification subjective ("comparer mentalement") | Remplacé par résumé obligatoire formaté |
| MINOR | Pas de format de sortie défini | Ajouté JSON structuré obligatoire |

## Round 2: Code Quality Review

| Severity | Finding | Resolution |
|---|---|---|
| CRITICAL | Parse tous les événements rg --json comme matches (begin/end/summary = faux findings) | Filtré par `event_type == 'match'`, ajouté `--no-messages` |
| CRITICAL | Crash sur JSON malformé (list comprehension sans try/except) | `try/except JSONDecodeError` par ligne |
| HIGH | Tout chargé en mémoire (pas de streaming) | Accepté : `terminal()` a déjà une limite de 50KB |
| HIGH | `files_scanned` faux (compte fichiers avec matches, pas scannés) | Utilise l'événement `summary` de rg pour le vrai compte |
| HIGH | Erreurs masquées (`2>/dev/null`) | Remplacé par `2>&1`, vérification exit_code |
| HIGH | Shell string, risque injection si paramétré | Accepté : contexte contrôlé, pas de user input |
| MEDIUM | Fichiers binaires/encodage mal gérés | Gère `line_text is None`, ignore entrées binaires |
| MEDIUM | Détection de confiance naïve (`'route' in line.lower()`) | Confiance basée sur pattern exact (`@app.route` ou `@router.`) |
| MEDIUM | Regex incomplète | Documenté comme limitation, warning dans la sortie |
| LOW | Imports morts (`read_file`, `os`, `re`) | Nettoyés |

## Lessons Learned

1. **rg --json emits 4 event types**: begin, match, end, summary. Must filter by `type == 'match'`.
2. **`--no-messages`** flag filters begin/end but NOT summary — still need summary check for files_scanned.
3. **2>&1 is mandatory** — silent failures produce clean-looking but wrong output.
4. **AST is the right tool for production**, regex is acceptable for discovery/exploration with documented limitations.
