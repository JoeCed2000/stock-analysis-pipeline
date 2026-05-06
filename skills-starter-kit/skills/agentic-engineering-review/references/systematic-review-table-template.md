# Systematic Review Table Template

Use this format for post-porting or cross-codebase review passes where the user demands
a thorough "weak points, critical issues, and gaps" analysis.

## Template

```markdown
## 🔍 [Project] — Revue systématique

**Codebase:** [Lang] ([LOC] LoC) vs [Reference] ([LOC] LoC)
**Tests:** [N] passants, [M] échec

---

### ✅ Parité confirmée (Alignement strict)

| Composant | Fichier | Statut |
|---|---|---|
| [Feature name] | `file.py` | ✅ Identique |
| ... | | |

### ⚠️ Points faibles

| # | Problème | Sévérité | Fichier |
|---|---|---|---|
| 1 | [Description] | 🟠 Majeur | `file.py` |
| ... | | 🟡 Mineur | |

### 🔴 Points critiques

| # | Problème | Impact |
|---|---|---|
| 1 | [Description] | 🔴 UI trompeuse / Crash / Data loss |

### 🔧 Corrections nécessaires

**1. [Fix name] (severity):**
[Code change or description]
```

## Usage

**⚠️ PITFALL — Compacted context is NOT a source of truth.** When resuming a multi-session porting project, the compacted context summary may claim files were \"already created\" or features were \"completed\" when they were NOT. Example: summary said `BatchActions.jsx` was created; `find` + `ls` proved it never existed. **Rule:** before declaring a feature \"done\", verify by searching for the file on disk (`find`, `search_files`, `ls`), checking the browser visually, and hitting the endpoint with `curl`. Never trust a prior session's summary alone.

1. Read both codebases side-by-side (source + target).
2. Cross-reference feature by feature, starting from scoring/logic → data flow → API → UI.
3. Classify each finding: ✅ Confirmed parity, ⚠️ Weak, 🔴 Critical.
4. For frontend: always verify enum↔display mappings (see `enum-display-mapping-pitfall.md`).
5. Present the table first, then the fixes.
6. Run tests after all fixes — table should show [N] passed unchanged at bottom.

## Example (AlphaRadarWeb, 2026-05-03)

Session: portage Android/Kotlin → Python/FastAPI.
Found 11 confirmed, 6 weak, 2 critical (level colors inverted, confidence missing from API).
Table format allowed the user to greenlight "fix everything" immediately.
