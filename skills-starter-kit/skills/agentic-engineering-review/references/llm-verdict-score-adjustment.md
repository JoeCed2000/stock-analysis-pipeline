# LLM Verdict → Quantitative Score Adjustment

Pattern: multi-agent LLM analysis produces a qualitative verdict, which is converted into a numerical adjustment and applied to a quantitative scoring system.

## Use Case

Hedge Fund API (22 AI investor agents) analyzes a stock ticker. The verdict (BUY/SELL/HOLD) and confidence are transformed into a `score_impact` value (±20% max) that adjusts AlphaRadar's quantitative convergence score (0-100).

## Architecture

```
22 agents analyze ticker → PortfolioManager synthesizes → verdict + confidence
                                                              ↓
                                              score_impact = direction × confidence × max_impact
                                                              ↓
                                              final_score = clamp(base_score × (1 + score_impact), 0, 100)
```

## Implementation

### 1. Verdict Extraction (API layer)

```python
def extract_verdict(agent_signals: dict) -> dict:
    """Count agent votes, determine verdict and confidence."""
    votes = {"bullish": 0, "bearish": 0, "neutral": 0}
    
    for analyst, signal in agent_signals.items():
        # Agents use "signal" key (not "action")
        action = signal.get("signal", "").lower()
        if action in ("bullish", "buy", "long"):
            votes["bullish"] += 1
        elif action in ("bearish", "sell", "short"):
            votes["bearish"] += 1
        else:
            votes["neutral"] += 1
    
    total = sum(votes.values()) or 1
    bullish_pct = votes["bullish"] / total
    bearish_pct = votes["bearish"] / total
    
    # Verdict threshold: 60% majority
    if bullish_pct >= 0.6:
        verdict = "BUY"
    elif bearish_pct >= 0.6:
        verdict = "SELL"
    else:
        verdict = "HOLD"
    
    # Confidence = how decisive the vote was
    confidence = max(bullish_pct, bearish_pct, 0.5)
    
    # Score impact: ±20% × confidence
    max_impact = 0.20
    if verdict == "BUY":
        score_impact = confidence * max_impact
    elif verdict == "SELL":
        score_impact = -confidence * max_impact
    else:
        score_impact = 0.0
    
    return {
        "verdict": verdict,
        "confidence": confidence,
        "score_impact": score_impact,
        "agent_votes": votes,
    }
```

### 2. Score Adjustment (scoring engine)

```python
def evaluate(asset, ai_score_impact: float | None = None) -> Score:
    # ... existing quantitative scoring ...
    clamped = max(0, min(100, raw_score))
    
    # AI hedge fund adjustment
    if ai_score_impact is not None and -0.20 <= ai_score_impact <= 0.20:
        adjusted = clamped * (1 + ai_score_impact)
        clamped = max(0, min(100, int(round(adjusted))))
    
    return Score(score=clamped, ...)
```

### 3. API Integration (backend router)

```python
@router.get("/api/ai/verdict/{ticker}")
async def get_ai_verdict(ticker: str):
    # 1. Check if ML API is reachable
    health = await client.get(f"{ML_API}/api/health")
    if health.status_code != 200:
        return {"status": "unavailable", "message": "ML API not running"}
    
    # 2. Call ML analysis (long operation)
    response = await client.post(
        f"{ML_API}/api/analyze",
        json={"ticker": ticker},
        timeout=600.0  # 10 min for multi-agent analysis
    )
    
    # 3. Cache result (1 hour TTL)
    _cache[ticker] = {"result": response.json(), "timestamp": time.time()}
    
    return response.json()
```

### 4. Frontend Display

```jsx
function VerdictBadge({ ticker, verdict, onAnalyze }) {
  const v = verdicts?.[ticker]
  if (!v) return <button onClick={() => onAnalyze(ticker)}>🤖 Analyze</button>
  if (v.status === 'unavailable') return <span title={v.message}>⚪</span>
  
  const emoji = { BUY: '🟢', SELL: '🔴', HOLD: '🟡' }
  return (
    <span title={`${v.verdict} (${Math.round(v.confidence * 100)}% conf, ${v.score_impact > 0 ? '+' : ''}${Math.round(v.score_impact * 100)}% impact)`}>
      {emoji[v.verdict]} {v.verdict}
    </span>
  )
}
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| 60% majority threshold | Avoids noise — requires clear consensus |
| ±20% max impact | Significant but doesn't override quantitative signals |
| 1-hour cache TTL | Analysis is expensive (5-10 min), markets don't change that fast |
| Asynchronous trigger | User clicks button, analysis runs in background, result cached |
| Unavailable state | ML API may be down — graceful degradation, not crash |

## Pitfalls

- **Agent signal keys vary**: Some agents use `signal`, some use `action`. Check both.
- **Long analysis time**: 20+ agents × LLM calls = 5-10 minutes. Never block the main request.
- **Cold start**: First analysis of a ticker is slow. Subsequent requests hit cache (1 hour).
- **API key propagation**: `source .env && cmd` in background doesn't propagate. Export explicitly.
- **Import slowness on NTFS**: LangChain imports take 20s+. Budget extra startup time.
