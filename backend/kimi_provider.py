"""Kimi K2.6 LLM provider — free via NVIDIA NIM, 40 RPM, OpenAI-compatible."""
import os
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

KIMI_MODEL = "moonshotai/kimi-k2.6"
KIMI_BASE_URL = "https://integrate.api.nvidia.com/v1"


def _get_kimi_client():
    """Get an OpenAI-compatible client for Kimi K2.6 on NVIDIA NIM."""
    api_key = os.getenv("NVIDIA_API_KEY", "")
    if not api_key:
        return None

    try:
        from openai import OpenAI
        import httpx
        return OpenAI(
            base_url=KIMI_BASE_URL,
            api_key=api_key,
            timeout=httpx.Timeout(120.0, connect=10.0),
            max_retries=0,  # We handle retries ourselves
        )
    except ImportError:
        return None


def kimi_chat(
    prompt: str,
    system: str = "You are a financial analyst. Be concise and data-driven.",
    max_tokens: int = 800,
    temperature: float = 0.3,
) -> Optional[str]:
    """Send a prompt to the best available LLM. Returns None on total failure.
    
    Priority: DeepSeek ($0.27/M) → Gemini (free) → Kimi K2.6 (free via NVIDIA)
    """
    # 1. DeepSeek — paid, fast, reliable (use first when key is set)
    result = _deepseek_chat(prompt, system, max_tokens, temperature)
    if result:
        return result
    
    # 2. Gemini — free, good fallback
    from backend.gemini_provider import gemini_chat as _gemini
    result = _gemini(prompt, system=system, max_tokens=max_tokens)
    if result:
        return result
    
    # 3. Kimi K2.6 — free via NVIDIA, last free option
    client = _get_kimi_client()
    if client is None:
        return _kimi_chat_http(prompt, system, max_tokens, temperature)

    try:
        resp = client.chat.completions.create(
            model=KIMI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["\n\n\n", "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n\nTokens:"],
        )
        return resp.choices[0].message.content
    except Exception as e:
        logger.warning(f"Kimi K2.6 client error: {e}")
        return _kimi_chat_http(prompt, system, max_tokens, temperature)


def _kimi_chat_http(
    prompt: str,
    system: str,
    max_tokens: int,
    temperature: float,
) -> Optional[str]:
    """Fallback HTTP call to Kimi K2.6."""
    api_key = os.getenv("NVIDIA_API_KEY", "")
    if not api_key:
        logger.warning("NVIDIA_API_KEY not set — Kimi K2.6 unavailable")
        return None

    from backend.http_client import http
    try:
        resp = http.post(
            f"{KIMI_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": KIMI_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stop": ["\n\n\n", "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n\nTokens:"],  # Kimi repetition guard
            },
            timeout=120,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        else:
            logger.warning(f"Kimi K2.6 HTTP {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        logger.warning(f"Kimi K2.6 HTTP error: {e}")
        return None


def _deepseek_chat(
    prompt: str,
    system: str,
    max_tokens: int,
    temperature: float = 0.3,
) -> Optional[str]:
    """Fallback to DeepSeek when Kimi is unavailable."""
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return None
    
    from backend.http_client import http
    try:
        resp = http.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=120,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        else:
            logger.warning(f"DeepSeek HTTP {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        logger.warning(f"DeepSeek error: {e}")
        return None


def kimi_analyze_management(mda_text: str, risk_text: str) -> Dict[str, Any]:
    """Analyze management tone from 10-K MD&A and risk factors using Kimi K2.6.
    Returns the same structure as management_analyzer.analyze_management_tone()."""
    if not mda_text or len(mda_text) < 500:
        return {
            "tone": "DATA NOT AVAILABLE",
            "confidence": "DATA NOT AVAILABLE",
            "visibility": "DATA NOT AVAILABLE",
            "concrete_promises": [],
            "defensive_signals": [],
        }

    prompt = f"""Analyze the management discourse in the following 10-K MD&A section.
Return a JSON object with these exact keys:
- "tone": overall tone (one of: "Confident and transparent", "Prudent but positive", "Evasive / vague", "Alarmist / defensive")
- "confidence": management confidence level (one of: "Strong — quantified guidance", "Moderate — qualitative objectives", "Weak — no visibility")
- "visibility": earnings visibility (one of: "Good — precise guidance", "Limited — wide range", "None — suspended guidance")
- "concrete_promises": list of specific, measurable commitments made (max 5)
- "defensive_signals": list of hedging language, caveats, or defensive phrasing (max 5)

MD&A TEXT:
{mda_text[:3000]}

RISK FACTORS (excerpt):
{risk_text[:1500] if risk_text else "Not available"}

Return ONLY valid JSON, no markdown formatting."""

    system = "You are an expert financial analyst specializing in management discourse analysis. You extract structured insights from SEC filings. Respond ONLY with valid JSON."

    response = kimi_chat(prompt, system=system, max_tokens=400, temperature=0.2)

    if not response:
        return {
            "tone": "DATA NOT AVAILABLE — Kimi K2.6 unavailable",
            "confidence": "DATA NOT AVAILABLE",
            "visibility": "DATA NOT AVAILABLE",
            "concrete_promises": [],
            "defensive_signals": [],
        }

    # Extract JSON from response
    try:
        # Kimi sometimes wraps JSON in markdown code blocks
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            response = response.split("```")[1].split("```")[0]
        # Strip trailing noise (repetition bugs)
        response = response.strip().rstrip("!").rstrip()
        # Find the JSON object boundaries
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            response = response[start:end]
        data = json.loads(response.strip())
        return {
            "tone": data.get("tone", "N/A"),
            "confidence": data.get("confidence", "N/A"),
            "visibility": data.get("visibility", "N/A"),
            "concrete_promises": data.get("concrete_promises", []),
            "defensive_signals": data.get("defensive_signals", []),
        }
    except (json.JSONDecodeError, IndexError) as e:
        logger.warning(f"Kimi JSON parse failed: {e}")
        return {
            "tone": f"PARSE ERROR — raw: {response[:100]}",
            "confidence": "DATA NOT AVAILABLE",
            "visibility": "DATA NOT AVAILABLE",
            "concrete_promises": [],
            "defensive_signals": [],
        }


def kimi_extract_risks(risk_text: str) -> list:
    """Extract structured risks from 10-K risk factors using Kimi K2.6."""
    if not risk_text or len(risk_text) < 300:
        return []

    prompt = f"""Extract the top 5 risks from this 10-K Risk Factors section.
Return a JSON array of objects, each with:
- "category": risk category (e.g., "Regulation", "Competition", "Supply Chain", "Geopolitical", "Financial")
- "description": concise one-line description of the risk
- "severity": one of "high", "medium", "low"
- "source": always "SEC 10-K Risk Factors (Kimi K2.6 analysis)"

RISK FACTORS TEXT:
{risk_text[:4000]}

Return ONLY valid JSON array, no markdown."""

    system = "You are a risk analyst. Extract structured risks from regulatory filings. Respond ONLY with a valid JSON array."

    response = kimi_chat(prompt, system=system, max_tokens=500, temperature=0.2)

    if not response:
        return []

    try:
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            response = response.split("```")[1].split("```")[0]
        response = response.strip().rstrip("!").rstrip()
        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            response = response[start:end]
        return json.loads(response.strip())
    except (json.JSONDecodeError, IndexError):
        return []


def kimi_ai_insight(ticker: str, company_name: str, score: int, decision: str) -> str:
    """Generate a one-line AI insight for the analysis card."""
    prompt = f"""Generate a concise, insightful one-liner (max 120 chars) about {company_name} ({ticker}).
Score: {score}/40. Decision: {decision}.
Make it sound like a professional analyst note. No fluff."""

    response = kimi_chat(prompt, system="Be concise. One sentence max.", max_tokens=80, temperature=0.5)
    return response.strip() if response else f"{decision} — score {score}/40"
