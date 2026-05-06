---
name: think-in-code
description: Maximise la densité d'information en remplaçant les read_file multi-fichiers par un script Python d'analyse unique. Inspiré du paradigme GenericAgent "Contextual Information Density Maximization".
category: software-development
trigger:
  - analyse multi-fichiers (>3 read_file prévus)
  - exploration de codebase
  - recherche de patterns dans plusieurs fichiers
  - question nécessitant une agrégation de données cross-fichiers
  - AVANT toute exploration de codebase : vérifier le wiki LLM en premier (wiki-first rule)
---

# Think in Code — Context-Aware Multi-File Analysis

## 🔴 RÈGLE WIKI-FIRST — Obligatoire avant toute exploration de codebase

**Avant TOUTE découverte manuelle** (`find`, `search_files`, `read_file` exploratoire), vérifier le wiki LLM :
```
Codex/docs/llm-wiki/
```

Une page projet y donne en **1 seule lecture** :
- Path exact du projet
- Stack technique (langages, frameworks)
- Tous les endpoints API existants
- Architecture (AGENTS.md)
- Conventions et commandes de test
- Fichiers clés

**Wiki path :** `/mnt/c/Users/cedon/Documents/Codex/docs/llm-wiki/projects/<Project_Name>.md`

**En complément, lire `COMMANDS.md` à la racine du projet** (s'il existe) :
- URLs de production (frontend, backend, dashboards)
- Commandes de dev local (ports, flags)
- Commandes de déploiement (Vercel, Render)
- Configuration spécifique (env vars, build/start commands)

**Pattern :**
```python
# Étape 0a — Wiki (1 read_file, ~3s)
read_file("Codex/docs/llm-wiki/projects/Nom_Projet.md")
# → Path, stack, endpoints, architecture, tout est là.

# Étape 0b — COMMANDS.md (1 read_file, ~2s)
read_file("Codex/<Project>/COMMANDS.md")
# → URLs, dev commands, deploy, config

# Seulement si le wiki n'a pas la page :
# → search_files + find + read_file (10-30 appels, ~60s)
```

**Ratio :** 1 `read_file` wiki vs 10-30 appels de discovery manuelle.
Wiki = 50+ pages dont ~15 projets documentés.
Après modification significative, mettre à jour la page wiki correspondante.

## Objectif

Remplacer les lectures séquentielles de fichiers par un script Python unique qui analyse tout en une exécution. Pattern en 2 étapes maximum : découverte (`search_files`) → extraction (`execute_code`).

## Principe (GenericAgent, 2026)

> "Context information density maximization" — la performance long-horizon dépend de la densité d'information utile dans le contexte, pas de sa taille brute.

Chaque `read_file` ajoute du bruit (paths, line numbers, contenu non filtré). Un script d'analyse ne retourne que l'information pertinente. **Mais** : une extraction automatique peut produire des faux négatifs (routes dynamiques, décorateurs multi-lignes, imports aliasés). Toujours valider avec un échantillon brut et indiquer le niveau de confiance.

## Quand utiliser

✅ **Utiliser Think in Code quand :**
- L'opération est **répétitive** (même pattern sur N fichiers)
- L'opération est **filtrable** (critère clair : regex, glob, structure)
- L'opération est **vérifiable** (tu peux valider la sortie sur un échantillon)
- La sortie attendue est **structurée** (tableau, liste, comptage)
- Tu explores une codebase (endpoints, classes, imports, TODO/FIXME)

❌ **Ne PAS utiliser pour :**
- Lire un fichier spécifique déjà connu (1-2 read_file plus rapide)
- Analyse sémantique complexe nécessitant le contexte complet
- Opérations où le coût d'écriture du script > bénéfice
- Quand le risque de faux négatif est inacceptable

## Pattern standard (2 étapes max)

**Étape 1 — Découverte (search_files) :**
```python
search_files(pattern="*.py", target="files", path="src/")
# Ou par contenu
search_files(pattern="@app.route|@router\\.", target="content", path="src/")
```

**Étape 2 — Extraction (execute_code) :**
```python
from hermes_tools import terminal
import json

ROOT = "src/"
PATTERN = r"@app\.route|@router\."
MAX_RESULTS = 50

# Phase 1 : extraction brute (rg --json, --no-messages supprime begin/end/summary)
result = terminal(f'rg --json --no-messages "{PATTERN}" {ROOT} 2>&1')
if result['exit_code'] not in (0, 1):
    raise RuntimeError(f"rg failed: {result['output'][:200]}")

# Phase 2 : parsing ligne par ligne avec tolérance JSON
findings = []
files_with_matches = set()
malformed = 0
files_scanned = None

for raw_line in result['output'].strip().split('\n'):
    line = raw_line.strip()
    if not line:
        continue
    try:
        item = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        malformed += 1
        continue

    # rg --json émet : begin, match, end, summary. --no-messages filtre begin/end.
    event_type = item.get('type')
    data = item.get('data') or {}

    if event_type == 'summary':
        stats = data.get('stats') or {}
        files_scanned = stats.get('searches')
        continue

    if event_type != 'match':
        continue

    path = (data.get('path') or {}).get('text')
    line_number = data.get('line_number')
    line_data = data.get('lines') or {}
    line_text = line_data.get('text')

    # Ignorer les entrées binaires ou sans texte
    if path is None or line_text is None:
        continue

    stripped = line_text.strip()
    lowered = stripped.lower()
    confidence = 'high' if ('@app.route' in lowered or '@router.' in lowered) else 'medium'

    files_with_matches.add(path)

    if len(findings) < MAX_RESULTS:
        findings.append({
            'path': path,
            'line': line_number,
            'match': stripped,
            'confidence': confidence
        })

# Phase 3 : sortie structurée
print(json.dumps({
    'files_scanned': files_scanned if files_scanned is not None else len(files_with_matches),
    'files_with_matches': len(files_with_matches),
    'findings': len(findings),
    'malformed_lines': malformed,
    'confidence': 'high' if findings else 'low',
    'warning': 'Regex only — routes dynamiques, décorateurs multi-lignes, alias peuvent être manqués',
    'results': findings
}, indent=2, ensure_ascii=False))
```

**Pièges corrigés (revue Codex) :**
- `--no-messages` supprime begin/end/summary → pas de faux findings
- `try/except` par ligne → tolère les fragments JSON invalides
- `2>&1` au lieu de `2>/dev/null` → capture et rapporte les erreurs
- `event_type == 'match'` uniquement → ignore begin/end/summary
- Gère `line_text is None` (fichiers binaires)
- Confiance basée sur pattern exact, pas fuzzy match
- `files_scanned` depuis l'événement summary ou fallback sur files_with_matches
- Voir `references/codex-review-findings.md` pour les 20 findings complets

## 🔴 Piège CRITIQUE — `read_file()['content']` contient des numéros de ligne

Dans `execute_code`, `read_file(path)['content']` retourne le contenu **avec des préfixes de numéro de ligne** (`"     1|import ...\n     2|..."`). Si ce contenu est passé à `write_file()`, le fichier est **corrompu** — chaque ligne se retrouve préfixée par son numéro. Le build échoue avec des erreurs de syntaxe.

**❌ Ne JAMAIS faire :**
```python
content = read_file(path)['content']
content = content.replace('old', 'new')
write_file(path, content)  # CORROMPU — line numbers écrits dans le fichier
```

**✅ Utiliser `patch()` ou `terminal()` avec sed pour modifier des fichiers depuis execute_code :**
```python
# Option 1: terminal + sed (fiable, pas de corruption)
terminal(f"sed -i 's/old/new/g' {path}")

# Option 2: Lire via terminal + cat (pas de line numbers)
result = terminal(f"cat {path}")
content = result['output']
# Modifier content...
write_file(path, modified_content)
```

**Si le fichier est déjà corrompu :** `git checkout <file>` pour restaurer.

## 🔴 Piège — `patch()` échappe les backslashes dans les regex Python

**Le patch tool double les backslashes** dans les chaînes Python contenant des regex. Un pattern `r'\b'` (word boundary) devient `r'\\b'` (backslash littéral + b) après un patch, cassant la regex silencieusement.

**Symptôme :** les regex cessent de matcher sans erreur Python — le `\b` est interprété comme `\x08` (backspace) ou un backslash littéral.

**Pattern observé (2026-05-04) :** patch sur `management_analyzer.py` — tous les `\b`, `\w`, `\s` dans les raw strings ont été doublés (`\\b`, `\\w`, `\\s`). Résultat : `_extract_themes` ne détectait plus aucun thème business.

**✅ Vérification après tout patch touchant des regex Python :**
```bash
grep -n '\\\\\\\\[bws]' fichier.py  # 4 backslashes dans le grep = 2 littéraux
```
Si le grep retourne des lignes → les backslashes ont été doublés → corriger immédiatement avec un second patch remplaçant `\\\\` par `\`.

**Pattern de correction :**
```python
# patch() avec old_string contenant les DOUBLES backslashes
patch(path,
    old_string=r"theme_patterns = [\n    (r'AI\\\\b|artificial intelligence'",  # corrompu
    new_string=r"theme_patterns = [\n    (r'AI\b|artificial intelligence'",   # corrigé
)
```

Depuis `execute_code`, `from hermes_tools import patch` puis `patch(path, old, new)` retourne un dict avec des clés non standards (`ok`, `error`, etc.) et les valeurs de succès/échec ne sont pas fiables. **Ne pas se fier au retour pour confirmer qu'un patch a été appliqué.**

**✅ Toujours vérifier après un batch de patches :** relire les fichiers avec `terminal(f"rg 'pattern' {path}")` ou un script de vérification pour confirmer que les changements ont bien été écrits. Le retour de la fonction `patch()` est indicatif, pas définitif.

## Contraintes de sécurité

- **Lecture seule obligatoire** — pas de `write_file`, `patch`, `rm`, `mv`
- **Pas d'import du code applicatif** — ne pas faire `import project.module`
- **Pas d'exécution de tests/builds** depuis ce skill
- **Exclusions explicites** : `.git`, `node_modules`, `dist`, `build`, `__pycache__`, `*.pyc`, `.env*`, `*.key`, `*.pem`, `secrets/`
- **Timeout** : 30s max pour le script d'analyse
- **Limite d'output** : 500 lignes max dans le résultat
- **Redaction** : si une valeur ressemble à un secret (token, password, api_key=...), la remplacer par `[REDACTED]`
- **Ne pas afficher de secrets**, mais l'analyse de code d'authentification (OAuth, JWT, middleware) est autorisée

## 🔴 Piège — `execute_code` utilise le Python système, PAS le venv du projet

`execute_code` lance un script dans un sandbox avec le Python système (`/usr/bin/python3`). Si le projet a un `.venv` avec des dépendances installées (yfinance, fastapi, etc.), les `import` échoueront avec `ModuleNotFoundError`.

**❌ Ne pas faire :**
```python
execute_code("""
import yfinance  # ModuleNotFoundError — pas installé dans le Python système
""")
```

**✅ Utiliser `terminal()` avec le venv du projet :**
```python
terminal(command="cd /path/to/project && PYTHONPATH=. .venv/bin/python -c 'import yfinance; ...'")
```

**Ou installer les dépendances dans le Python système** (déconseillé — préférer le venv).

Ce piège est particulièrement trompeur car `execute_code` fonctionne pour du Python stdlib (json, os, re...) mais échoue silencieusement dès qu'on importe une dépendance projet.

## Stratégie d'outillage

| Étape | Outil | Quand |
|---|---|---|
| Découverte | `rg` / `search_files` | Toujours — rapide, fiable |
| Extraction simple | `rg -o` / `awk` / `sed` | Patterns regex clairs |
| Extraction structurée | `execute_code` + Python stdlib | Parsing complexe, JSON |
| Analyse syntaxique | `ast` (Python), `tree-sitter` | Quand la structure du code compte |

## Format de sortie

```json
{
  "files_scanned": N,
  "files_with_matches": N,
  "findings": N,
  "malformed_lines": N,
  "confidence": "high|medium|low",
  "warning": "limitations connues",
  "results": [
    {"path": "...", "line": N, "match": "...", "confidence": "high"}
  ]
}
```

## Vérification (obligatoire après chaque usage)

Produire un résumé d'une ligne dans la réponse :
> `[think-in-code] N fichiers scannés, M findings, confiance=X, économie estimée ~Y read_file`

## Références

- GenericAgent paper (arXiv:2604.17091) : Contextual Information Density Maximization
- context-mode MCP server : 98% réduction de sortie outil (315KB → 5KB)
- Approche recommandée dans certains workflows agentiques (Codex CLI, Claude Code)
- `references/codex-review-findings.md` — 20 findings de la double revue Codex, tous corrigés
