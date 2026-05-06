# Enum↔Display Mapping Pitfall

**Bug class:** When a frontend component maps numeric enum values to colors/labels using a plain object, and the values don't match the backend enum values.

## Concrete example (AlphaRadarWeb, 2026-05-03)

### Backend (Python)

```python
class OpportunityLevel(IntEnum):
    PRIORITY = 3    # Highest
    SERIOUS = 2
    WATCH = 1       # Lowest
```

### Frontend (React JSX) — BROKEN

```jsx
// ❌ INVERTED — PRIORITY(3) gets WATCH blue, WATCH(1) gets PRIORITY red
const levelColors = {
  1: '#f44336', // Priority ?? NON — c'est WATCH
  2: '#ff9800', // Serious
  3: '#2196f3', // Watch ?? NON — c'est PRIORITY
}
```

### Frontend (React JSX) — CORRECT

```jsx
// ✅ Aligned with backend enum values
const levelColors = {
  3: '#f44336', // PRIORITY
  2: '#ff9800', // SERIOUS
  1: '#2196f3', // WATCH
}
```

## Root cause

The developer mapped keys 1,2,3 by assumed order instead of by the actual `IntEnum` values. Since `PRIORITY=3` and `WATCH=1`, the mapping was inverted.

## Detection pattern

1. During cross-codebase audit or agentic review, **find all JSX objects that map numbers to colors/labels**.
2. Cross-reference each numeric key against the backend enum definition.
3. This bug is **silent** — no crash, no error, just wrong colors. Visual inspection won't catch it unless you know what to look for.
4. Add to checklist: "For every `{N: 'color'}` or `{N: 'label'}` mapping in JSX, verify N matches `EnumClass.MEMBER.value` from the backend Pydantic definition."
