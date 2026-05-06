# JS FormData: Blob vs File Pitfall

## The Bug

```js
// ❌ BROKEN — Blob has no .name property
const blob = new Blob([content], { type: 'text/plain' });
blob.name = 'input.txt';  // This does NOT work — Blob.name is read-only or non-existent
const formData = new FormData();
formData.append('file', blob);  // Backend receives a file named "blob" (or no name)
```

A `Blob` object does NOT have a `.name` property. Setting `blob.name = 'input.txt'` does nothing. When `FormData.append('file', blob)` is called, the file is sent with a default/generic filename (like `"blob"`), and the backend multipart parser often rejects it or returns empty results.

## The Fix

```js
// ✅ CORRECT — File extends Blob and HAS a .name
const file = new File([content], 'input.txt', { type: 'text/plain' });
const formData = new FormData();
formData.append('file', file);  // Backend receives a proper file named "input.txt"
```

`File` extends `Blob` with a `.name` property. Always use `new File()` when you need a FormData upload from in-memory content.

## Detection

- Frontend sends a file to backend via FormData
- Backend multipart endpoint returns 400 or empty results
- The `catch` block in the frontend is silent (no error visible to user)
- Console shows no error (if catch is silent)

**Red flags:**
- `new Blob([...])` anywhere near a file upload
- `blob.name = ...` pattern
- `FormData.append('file', blob)` where `blob` is a `Blob`, not a `File`
- `catch (e) { /* silently ignore */ }` or empty catch blocks

## Combined Anti-Pattern: Silent Catch + Blob

```js
// ❌ DOUBLE FAILURE — Blob has no name + catch swallows the error
try {
  const blob = new Blob([value]);
  blob.name = 'input.txt';  // no-op
  const data = await uploadTickerFile(blob);  // backend rejects, throws
} catch (e) {
  // silently ignore parse errors
}
// → User clicks Parse, NOTHING happens, no feedback
```

Fix both:
1. `new File([value], 'input.txt', { type: 'text/plain' })`
2. `console.error('Parse error:', e)` instead of silent catch

## Observed

2026-05-04: `stock-analysis-pipeline` frontend Quick Analysis tab — textarea → parse button. User reported "Le parse ne fait rien". Root cause: `new Blob([value])` created a file without a name, backend `/api/batch/upload` rejected it, silent catch hid the error.
