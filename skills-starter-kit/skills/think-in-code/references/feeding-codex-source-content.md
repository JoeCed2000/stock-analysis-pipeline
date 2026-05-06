# Feeding Source Content to Codex (not just paths)

## The pitfall

When delegating code analysis to Codex, giving it only file paths:
```
Read these files: /path/to/foo.py, /path/to/bar.py
```
...results in Codex spending iterations on `cat`/`read`/`sed` calls to get the content. It may time out before reaching the analysis phase.

## The fix

Concatenate source files and pipe the full content directly to Codex:

```bash
{ echo "=== FILE 1 ===" && cat /path/to/file1.py && echo "=== FILE 2 ===" && cat /path/to/file2.py; } | codex exec --skip-git-repo-check -c model_reasoning_effort="high"
```

Or for multi-language analysis (Kotlin + Python):
```bash
{
  echo "=== KOTLIN SOURCE (reference) ==="
  cat /path/to/AndroidFile1.kt
  cat /path/to/AndroidFile2.kt
  echo "=== PYTHON TARGET ==="
  cat /path/to/python_file1.py
} | codex exec --skip-git-repo-check -c model_reasoning_effort="high"
```

## When to use

✅ Use when:
- Codex needs to analyze multiple files (>3)
- Codex needs to compare two implementations (porting audit)
- Timeout risk: reading files one-by-one burns iterations

❌ Don't use when:
- Single file analysis (direct pipe is fine but overkill)
- Files are huge (>5000 lines combined) — summarize first

## Related

- `think-in-code` skill: use Python scripts for analysis instead of N read_file calls
- `codex` skill: general Codex invocation patterns
