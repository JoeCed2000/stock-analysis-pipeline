# HTMX: `name` Attribute Required for Form Element Serialization

## Pitfall

**`hx-include` serializes form elements by their `name` attribute, NOT by `id`.** 

A `<select>` (or `<input>`, `<textarea>`) with only an `id` will NOT send its value when referenced by `hx-include="#id"`. The value is silently dropped, and the backend receives the default/empty parameter.

## Symptom

- Backend receives empty/default value for the parameter (`project=""`, `filter=""`, etc.)
- UI shows "No project selected" / "No input provided" even though the user selected something
- `curl` with explicit `?param=value` works, but HTMX-driven clicks don't

## Diagnostic

```bash
# Check the HTML source for the element referenced by hx-include
curl -s "http://127.0.0.1:PORT/page" | grep -A5 'id="element-id"'

# ❌ Missing name attribute
<select id="pp-project" style="...">

# ✅ Correct — name attribute present
<select id="pp-project" name="project" style="...">
```

## Root Cause

HTMX's `hx-include` uses the same serialization logic as HTML forms. An element without a `name` attribute cannot contribute to the query string / form body — there's no key to assign the value to.

## Fix

Add `name="<parameter_name>"` to the element:

```html
<select id="pp-project" name="project" ...>
```

The `name` MUST match the backend parameter name (e.g., FastAPI's `project: str = ""`).

## Rule

**Every form element referenced by `hx-include` MUST have a `name` attribute.** The `name` is what maps the element's value to the query parameter. `id` alone is insufficient.

## Real Case

- **Project**: CedControlCenter, Pre-Push Validator widget
- **Date**: 2026-05-05
- **Symptom**: "Aucun projet sélectionné" despite selecting "Stock Analysis" from dropdown
- **Element**: `<select id="pp-project">` — no `name` attribute
- **Fix**: Added `name="project"` → HTMX now sends `?project=Stock+Analysis`
- **Endpoint**: `/partials/pre-push-result` (FastAPI: `project: str = ""`)
