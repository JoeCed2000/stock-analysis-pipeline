# AI Debate Microservice Pattern

## Use Case

You have a backend that scores opportunities (AlphaRadar, trading dashboard, alert system)
and you want to enrich each opportunity with a **multi-agent debate** (Bull vs Bear → 
Portfolio Manager). Both a web frontend and a mobile app need this capability. Instead of
duplicating agentic logic in both codebases, run a single shared microservice.

## Architecture

```
┌──────────────┐       ┌──────────────────┐       ┌──────────┐
│ Python Web   │──────>│ POST /api/ai/    │──────>│ DeepSeek │
│ (AlphaRadar) │       │ debate           │       │ API      │
└──────────────┘       │                  │       └──────────┘
                       │ HMAC auth        │
┌──────────────┐       │ Rate limit       │
│ Android APK  │──────>│ Private IP OK    │
└──────────────┘       └──────────────────┘
```

## Key Design Decisions

### 1. Direct httpx instead of langchain
On constrained systems (WSL/NTFS, small venvs), `pip install langchain-openai` can hang or
fail. Use `httpx` to call the provider API directly — it's already installed in most projects.

```python
# Direct DeepSeek call (no langchain dependency)
payload = {
    "model": "deepseek-chat",
    "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
    "temperature": 0.3, "max_tokens": 800,
}
resp = httpx.post("https://api.deepseek.com/v1/chat/completions",
    json=payload, headers={"Authorization": f"Bearer {key}"}, timeout=30.0)
data = resp.json()["choices"][0]["message"]["content"]
```

### 2. HMAC token auth (not OAuth, not JWT)
A simple shared secret, compared with `hmac.compare_digest()` (timing-safe).
Mobile app stores the secret; backend verifies it. Zero infrastructure.

```python
AI_ANALYSIS_SECRET = os.environ.get("AI_ANALYSIS_SECRET", "")
if not hmac.compare_digest(token, AI_ANALYSIS_SECRET):
    raise HTTPException(403, "Invalid analysis token")
```

Without a secret configured, the endpoint is open to localhost only (existing middleware).

### 3. Rate limiting per ticker (not per IP)
Mobile and web share the same cooldown. 5 minutes between analyses for the same ticker
prevents API cost spikes.

```python
_last_call: dict[str, float] = {}
if time.time() - _last_call.get(ticker, 0) < 300:
    raise HTTPException(429, "Rate limit")
```

### 4. Private network IP allowed only for AI routes
The existing `localhost_only` middleware blocks non-loopback. Add an exception for
`/api/ai/` routes when the client IP is in a private network (192.168.x.x, 10.x.x.x)
AND a secret is configured. This enables mobile access without opening the entire API.

```python
allow_private = (
    AI_ANALYSIS_SECRET
    and request.url.path.startswith("/api/ai/")
    and ipaddress.ip_address(client_host).is_private
)
```

### 5. Fallback when API fails
If DeepSeek is unreachable, return a neutral HOLD (score 50) instead of crashing.
The caller gets a valid response with an error flag in reasoning.

## Agent Flow

```
Asset data → Bull agent (BUY case) ──┐
                                     ├─→ Portfolio Manager → Verdict
Asset data → Bear agent (SELL case) ─┘      (BUY/SELL/HOLD + score + reasoning)
```

Each agent call is ~2-4 seconds. Total debate: ~5-10 seconds.

## Response Format

```json
{
  "ticker": "NVDA",
  "bull": {"agent": "bull", "action": "BUY", "score": 78, "reasoning": "...", "risks": [...]},
  "bear": {"agent": "bear", "action": "SELL", "score": 65, "reasoning": "...", "risks": [...]},
  "final": {"agent": "portfolio_manager", "action": "HOLD", "score": 60, "reasoning": "...", "risks": [...]},
  "debate_rounds": 1,
  "elapsed_ms": 4800
}
```

## Mobile Integration

Android/Kotlin calling this endpoint:

```kotlin
val client = OkHttpClient()
val request = Request.Builder()
    .url("http://192.168.1.X:7864/api/ai/debate")
    .header("Authorization", "Bearer $secret")
    .header("Content-Type", "application/json")
    .post(jsonBody)
    .build()
val response = client.newCall(request).execute()
```

## Security Notes

- The DeepSeek API key **never leaves the server**. Mobile sends only ticker + signals.
- The HMAC secret is a random 32-byte token stored in `.env` (gitignored).
- Rate limit prevents abuse even if the secret is leaked.
- No user data exposed — the endpoint accepts ticker/signals only, no PII.
