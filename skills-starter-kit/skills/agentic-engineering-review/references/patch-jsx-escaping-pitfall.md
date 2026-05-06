# Pitfall: Patch Tool Escapes Quotes & Backslashes

## Symptom A — JSX quotes
After using `patch()` to modify a React JSX/TSX file, the build fails with:
```
Expecting Unicode escape sequence \uXXXX
```
The file contains `\"` (backslash-escaped quotes) in JSX attributes instead of plain `"`.

## Symptom B — Regex backslashes (Python raw strings)
After using `patch()` on Python files containing raw regex strings (`r'...'`), patterns silently stop matching. No error is raised — the regex simply returns no results.
```
# Before patch:  r'\bLLM\b'      → matches "LLM" as a word
# After patch:   r'\\bLLM\\b'    → matches literal "\bLLM\b" — never matches real text
```

## Root Cause
The `patch()` tool double-escapes backslashes: `\b` → `\\b`. In JSX this produces invalid quote syntax. In Python raw strings this changes `\b` from "word boundary" to "literal backslash + b", breaking the regex silently.

## Detection
```bash
# JSX: check for escaped quotes
grep -n '\\"' src/components/Component.jsx

# Python regex: check for doubled backslashes in raw strings
grep -n '\\\\\\\\[bwsd]' fichier.py  # 4 backslashes in grep = 2 literal
```

## Fix
For regex: do a second patch replacing doubled backslashes with single ones:
```python
patch(path,
    old_string=r"(r'AI\\\\b|artificial intelligence'",  # corrupted
    new_string=r"(r'AI\\b|artificial intelligence'",    # fixed
)
```
Then verify: `grep "r'AI" fichier.py` shows single backslash.

## Prevention
- After every `patch()` on frontend files, run the JSX grep check
- After every `patch()` on Python files containing raw strings, run the regex backslash check
- On NTFS, Vite HMR won't detect the fix — always kill + restart Vite
- Consider `write_file()` for multi-line changes to avoid escaping issues entirely
