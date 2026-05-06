# New Repo Security Audit Checklist

Audit a third-party repo before trusting it with API keys or credentials.

## Checklist

### 1. API Key Flow
- [ ] How is the key read? (`os.environ.get()`, `load_dotenv()`, hardcoded?)
- [ ] Where is the key used? Trace every `api_key` argument to its HTTP destination.
- [ ] Does the key ever leave the intended provider's domain?
- [ ] Any `send_to_own_server()`, `telemetry.ingest()`, or similar pattern?

### 2. Network Calls
```bash
# Find all outbound HTTP calls
grep -rn "requests\.\|httpx\.\|urllib\|aiohttp\|curl" --include="*.py" .
# Categorize each endpoint:
# - Provider API (legitimate) vs third-party (suspicious)
# - Does it send auth headers? What exactly?
```

### 3. Hardcoded Secrets
```bash
# Scan for keys, tokens, passwords
grep -rn "sk-\|api_key\|secret\|password\|token\s*=" --include="*.py" --include="*.env" --include="*.json" .
# Exclude test fixtures with placeholder values
# Flag any non-placeholder match
```

### 4. Dangerous Functions
```bash
# eval/exec/pickle — all red flags in production code
grep -rn "eval(\|exec(\|pickle\.\|__import__\|compile(" --include="*.py" .
# ast.literal_eval() is safe, re.compile() is fine — exclude those
```

### 5. Telemetry & Analytics
```bash
# Data exfiltration vectors
grep -rn "telemetry\|analytics\|track\|logfire\|sentry\|posthog\|datadog\|mixpanel" --include="*.py" .
# Local stats tracking (for display only) is fine — flag network-based tracking
```

### 6. .env & .gitignore
- [ ] `.env` in `.gitignore`? (Must be — line should exist)
- [ ] Any `.env` files already committed? (`git log --all -- .env`)
- [ ] `load_dotenv()` pattern: does it load from current dir, or hardcoded path?

### 7. Dependency Sanity
- [ ] All deps from PyPI/npm/trusted registries?
- [ ] No personal forks or obscure packages?
- [ ] Version pins are reasonable (not 0.0.1 dev releases)?

### 8. Announcements / Update Checks
- [ ] Any background HTTP calls on startup? (announcements, version checks, update pings)
- [ ] What data is sent? (Usually nothing — GET request with no auth)
- [ ] Who owns the endpoint? (Same org as the repo = legitimate; random third-party = red flag)

## Verdict Format

```
✅ SAFE — No risk for API key
⚠️ CAUTION — Minor concerns (list them)
🔴 UNSAFE — Do not use with real credentials
```

## Concrete Example (TradingAgents, 2026-05-03)

- Repo: `TauricResearch/TradingAgents` (57.9k ⭐)
- `tauric.ai/v1/announcements` — GET, no auth, 1s timeout, same org as repo → ✅
- `openrouter.ai/api/v1/models` — GET, no auth, public model list → ✅
- API keys: `os.environ.get()` → LangChain client → provider API directly → ✅
- Zero hardcoded keys, zero telemetry, .env in .gitignore → ✅
- Verdict: **SAFE**
