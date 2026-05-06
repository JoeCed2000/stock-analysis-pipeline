---
name: env-loading-pattern
description: "Standard pattern for loading .env files in Python scripts. Two rules: never use os.environ.setdefault(), and never call os.getenv() at module level for .env values."
version: 1.0.0
metadata:
  hermes:
    tags: [env, dotenv, python, secrets, configuration]
    priority: critical
---

# .env Loading Pattern

## The Two Rules

### Rule 1: Use `os.environ[k] = v`, NEVER `os.environ.setdefault()`

```python
# ❌ WRONG — stale env vars from Hermes agent environment persist
os.environ.setdefault(k.strip(), v.strip())

# ✅ CORRECT — .env always wins
os.environ[k.strip()] = v.strip()
```

**Why**: `setdefault()` keeps the FIRST value. Hermes agent environments often have stale env vars from previous sessions or cron runs. The .env file is the source of truth — it must ALWAYS win.

### Rule 2: Never `os.getenv()` at module level for .env values

```python
# ❌ WRONG — runs at import time, before main() loads .env
UPLOAD_SECRET = os.getenv("DOSSIER_UPLOAD_SECRET", "")

def upload_file(...):
    headers = {"X-Secret": UPLOAD_SECRET}  # Always empty string!

# ✅ CORRECT — function called AFTER .env is loaded
def get_secret():
    return os.getenv("DOSSIER_UPLOAD_SECRET", "")

def upload_file(...):
    secret = get_secret()  # Reads fresh value
```

**Why**: Python executes module-level code at import time. If `.env` is loaded in `main()`, any `os.getenv()` at module level sees the PRE-loading environment (empty).

## Complete Pattern

```python
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

def load_env():
    """Load .env — called once at startup."""
    env_path = PROJECT_DIR / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()  # Force override

def get_config(key: str, default: str = "") -> str:
    """Read a config value AFTER .env is loaded."""
    return os.getenv(key, default)


# ── main ──
if __name__ == "__main__":
    load_env()
    secret = get_config("MY_SECRET")
    # ... use secret
```

## Checklist

Before running any Python script that reads `.env`:
- [ ] `.env` is in `.gitignore` (verified)
- [ ] No `os.getenv()` at module level for .env values
- [ ] Uses `os.environ[k] = v` (not `setdefault`)
- [ ] Config values read via function, not global variable
- [ ] `.env` loaded before any config access
