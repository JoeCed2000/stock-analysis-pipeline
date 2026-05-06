# Cross-Codebase Functional Audit Methodology

When porting features or auditing alignment between two codebases (e.g., Android→Python, Kotlin→FastAPI).

## Trigger
- User requests "audit", "alignement", "parité", "portage complet"
- Two codebases implementing the same domain logic in different languages

## Principles
1. **100% autonomous** — no asking permission, no stopping mid-audit
2. **Feature-by-feature** — compare one function/endpoint at a time
3. **Strict alignment** — "assez proche" is not acceptable; match logic exactly
4. **Fix silently** — detect divergence, apply correction, move to next
5. **Report at end** — comprehensive audit report, not piecemeal updates

## Methodology

### Phase 1: Discovery
- Load both codebases' source files into context
- Identify all comparable features (functions, classes, endpoints)
- Use `think-in-code` for efficient multi-file comparison

### Phase 2: Systematic comparison
For EACH feature:
1. Read source code from both codebases
2. Compare: logic, inputs/outputs, error handling, edge cases, state/persistence
3. If aligned → ✅ mark and continue
4. If diverged → note the specific divergence, apply correction

### Phase 3: Correction
- Apply fixes immediately (don't batch)
- Run tests after each fix batch
- Re-run comparison to verify alignment

### Phase 4: Report
Format the final audit report as:

```
# Rapport d'Audit Complet

**Fonctionnalités testées:** N
**Divergences trouvées:** N
**Divergences corrigées:** N

## Journal des corrections

| # | Erreur | Comportement A | Comportement B | Correction |
|---|---|---|---|---|
| 1 | ... | ... | ... | ... |

## Alignements confirmés

| # | Fonctionnalité | Statut |
|---|---|---|
| ... | ... | ✅ |

## Divergences architecturales (intentionnelles)

| Élément | A | B | Justification |
|---|---|---|---|

## Verdict final
> Audit complet terminé et alignement prêt à être déployé.
```

## Common pitfalls
- **Rounding differences** — languages round differently (Kotlin roundSmart vs Python round)
- **Order of operations** — scoring engines may apply penalties/bonuses in different order
- **Null/None handling** — Kotlin's `?.takeIf{}` vs Python's `is not None`
- **Infinity checks** — Python floats can be `inf`, Kotlin protects with `isFinite()`
- **Sorting tiebreakers** — different sort keys produce different rankings
- **Warning messages** — one codebase adds warnings the other omits
- **Signal counting** — what counts as a "confirmation" may differ

## Real example
AlphaRadar Android (Kotlin) → Python (FastAPI): 17 features audited, 6 divergences found, 6 corrected. Key fixes: scoring order, volume finiteness, rounding, anti-FOMO warnings, confirmation caps, sorting tiebreakers.
