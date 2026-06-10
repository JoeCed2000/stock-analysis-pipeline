"""Codex CLI LLM provider — replaces Kimi K2.6 for pipeline NLP tasks.
Uses os.openpty() for PTY (required by Codex CLI).
"""
import os
import json
from typing import Optional
import logging
import pwd
import shutil
import subprocess
import tempfile
import time
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Resolve Codex binary using the real OS login home (not profile-local ~).
# Hermes profiles redirect $HOME, so os.path.expanduser("~") points to
# the profile-local fake home where Codex is NOT installed.
_REAL_HOME = pwd.getpwuid(os.getuid()).pw_dir
_CODEX_CANDIDATES = [
    os.path.join(_REAL_HOME, ".hermes", "node", "bin", "codex"),  # Ced's canonical install
    shutil.which("codex"),                                           # PATH fallback
]
CODEX_BIN = None
for _c in _CODEX_CANDIDATES:
    if _c and os.path.exists(_c):
        CODEX_BIN = _c
        break

if CODEX_BIN is None:
    CODEX_BIN = _CODEX_CANDIDATES[0]  # keep for clearer error message
CODEX_TIMEOUT = 600  # seconds per attempt (agents need time to finish — 10 min)
CODEX_TIMEOUT_FIRST = 300  # first attempt: Spark is slow for large prompts (~5KB)
CODEX_MAX_RETRIES = 2  # total attempts = 1 + MAX_RETRIES = 3
CODEX_RETRY_BACKOFF = [2.0, 4.0]  # seconds between retries (jittered ±50%)

# Global lock to serialize Codex subprocess launches (anti-thundering-herd for EN+JP parallelism)
_codex_launch_lock = __import__("threading").Lock()


def _codex_chat(
    prompt: str,
    system: str = "",
    max_tokens: int = 1000,
    model: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
) -> Optional[str]:
    """Send a prompt to Codex CLI and return the response text.

    Default routing is intentionally Codex Spark-first for SA pipeline stability:
    ``SA_CODEX_MODEL`` defaults to ``gpt-5.3-codex-spark`` and
    ``SA_CODEX_DEFAULT_EFFORT`` defaults to ``low``. Callers may still pass an
    explicit model/effort for higher-synthesis steps such as Company Overview.
    """
    if not os.path.exists(CODEX_BIN):
        logger.warning("Codex CLI not found at %s", CODEX_BIN)
        return None

    selected_model = (model or os.getenv("SA_CODEX_MODEL") or "gpt-5.3-codex-spark").strip()
    selected_effort = (reasoning_effort or os.getenv("SA_CODEX_DEFAULT_EFFORT") or "medium").strip().lower()
    safe_effort = selected_effort if selected_effort in {"minimal", "low", "medium", "high"} else "low"
    full_prompt = f"{system}\n\n{prompt}\n\nReturn ONLY the requested output. No explanations."
    env = os.environ.copy()
    env["HOME"] = _REAL_HOME
    last_error = None

    for attempt in range(CODEX_MAX_RETRIES + 1):
        if attempt > 0:
            backoff = CODEX_RETRY_BACKOFF[min(attempt - 1, len(CODEX_RETRY_BACKOFF) - 1)]
            jitter = backoff * 0.5 * (__import__("random").random())
            wait = backoff + jitter
            logger.info(
                "llm_call retry provider=codex_cli model=%s effort=%s attempt=%d/%d wait_seconds=%.1f",
                selected_model,
                safe_effort,
                attempt + 1,
                CODEX_MAX_RETRIES + 1,
                wait,
            )
            time.sleep(wait)

        fd, output_file = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        timeout = CODEX_TIMEOUT_FIRST if attempt == 0 else CODEX_TIMEOUT
        started = time.monotonic()
        try:
            args = [
                CODEX_BIN,
                "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "--json",
                "-m",
                selected_model,
                "-c",
                f"model_reasoning_effort={safe_effort}",
                "-o",
                output_file,
                "-",
            ]

            logger.info(
                "llm_call start provider=codex_cli model=%s effort=%s attempt=%d/%d max_tokens=%d prompt_chars=%d timeout_seconds=%d",
                selected_model,
                safe_effort,
                attempt + 1,
                CODEX_MAX_RETRIES + 1,
                max_tokens,
                len(full_prompt),
                timeout,
            )
            with _codex_launch_lock:
                proc = subprocess.run(
                    args,
                    input=full_prompt,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    timeout=timeout,
                )
            duration_ms = int((time.monotonic() - started) * 1000)

            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                with open(output_file) as f:
                    response = f.read().strip()
                if response:
                    logger.info(
                        "llm_call success provider=codex_cli model=%s effort=%s attempt=%d/%d duration_ms=%d output_chars=%d",
                        selected_model,
                        safe_effort,
                        attempt + 1,
                        CODEX_MAX_RETRIES + 1,
                        duration_ms,
                        len(response),
                    )
                    return response

            stdout_tail = (proc.stdout or "")[-500:]
            stderr_tail = (proc.stderr or "")[-500:]
            logger.warning(
                "llm_call empty provider=codex_cli model=%s effort=%s attempt=%d/%d duration_ms=%d rc=%d stdout_tail=%r stderr_tail=%r",
                selected_model,
                safe_effort,
                attempt + 1,
                CODEX_MAX_RETRIES + 1,
                duration_ms,
                proc.returncode,
                stdout_tail,
                stderr_tail,
            )
            last_error = f"no_output(rc={proc.returncode})"
        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - started) * 1000)
            logger.warning(
                "llm_call timeout provider=codex_cli model=%s effort=%s attempt=%d/%d duration_ms=%d timeout_seconds=%d",
                selected_model,
                safe_effort,
                attempt + 1,
                CODEX_MAX_RETRIES + 1,
                duration_ms,
                timeout,
                exc_info=True,
            )
            last_error = "timeout"
        except FileNotFoundError:
            logger.exception("llm_call missing_binary provider=codex_cli binary=%s", CODEX_BIN)
            return None
        except Exception as e:
            logger.exception(
                "llm_call exception provider=codex_cli model=%s effort=%s attempt=%d/%d error=%s",
                selected_model,
                safe_effort,
                attempt + 1,
                CODEX_MAX_RETRIES + 1,
                e,
            )
            last_error = str(e)
        finally:
            try:
                os.unlink(output_file)
            except OSError:
                pass

    logger.error(
        "llm_call failed provider=codex_cli model=%s effort=%s attempts=%d last_error=%s",
        selected_model,
        safe_effort,
        CODEX_MAX_RETRIES + 1,
        last_error,
    )
    return None


def codex_analyze_management(mda_text: str, risk_text: str) -> Dict[str, Any]:
    """Analyze management tone AND extract risks in ONE Codex call."""
    if not mda_text or len(mda_text) < 500:
        return {
            "tone": "DATA NOT AVAILABLE",
            "confidence": "DATA NOT AVAILABLE",
            "visibility": "DATA NOT AVAILABLE",
            "concrete_promises": [],
            "defensive_signals": [],
            "risks": [],
        }

    prompt = f"""Analyze this 10-K MD&A section and Risk Factors. Return ONLY a JSON object (no markdown, no explanation) with EXACTLY this structure:

{{{{
  "tone": "<overall tone>",
  "confidence": "<management confidence>",
  "visibility": "<earnings visibility>",
  "concrete_promises": ["<promise 1>", "<promise 2>"],
  "defensive_signals": ["<signal 1>", "<signal 2>"],
  "risks": [
    {{{{"category": "<category>", "description": "<description>", "severity": "high|medium|low", "source": "SEC 10-K Risk Factors"}}}}
  ]
}}}}

TONE OPTIONS: "Confident and transparent", "Prudent but positive", "Evasive / vague", "Alarmist / defensive"
CONFIDENCE OPTIONS: "Strong — quantified guidance", "Moderate — qualitative objectives", "Weak — no visibility"
VISIBILITY OPTIONS: "Good — precise guidance", "Limited — wide range", "None — suspended guidance"

MD&A TEXT:
{mda_text[:3000]}

RISK FACTORS:
{risk_text[:2000] if risk_text else "Not available"}

Return ONLY the JSON object."""

    system = "You extract structured financial insights from SEC filings. Return ONLY valid JSON."
    response = _codex_chat(prompt, system=system, max_tokens=1500)

    if not response:
        return {
            "tone": "DATA NOT AVAILABLE — Codex unavailable",
            "confidence": "DATA NOT AVAILABLE",
            "visibility": "DATA NOT AVAILABLE",
            "concrete_promises": [],
            "defensive_signals": [],
            "risks": [],
        }

    try:
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            response = response.split("```")[1].split("```")[0]
        response = response.strip()
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            response = response[start:end]
        data = json.loads(response)
        return {
            "tone": data.get("tone", "N/A"),
            "confidence": data.get("confidence", "N/A"),
            "visibility": data.get("visibility", "N/A"),
            "concrete_promises": data.get("concrete_promises", []),
            "defensive_signals": data.get("defensive_signals", []),
            "risks": data.get("risks", []),
        }
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning(f"Codex JSON parse failed: {e} | raw: {response[:200]}")
        return {
            "tone": "PARSE ERROR",
            "confidence": "DATA NOT AVAILABLE",
            "visibility": "DATA NOT AVAILABLE",
            "concrete_promises": [],
            "defensive_signals": [],
            "risks": [],
        }


def codex_ai_insight(ticker: str, company_name: str, score: int, decision: str) -> str:
    """Generate a one-line AI insight using Codex."""
    prompt = f"""Generate a concise, insightful one-liner (max 120 chars) about {company_name} ({ticker}).
Score: {score}/40. Decision: {decision}.
Return ONLY the one-liner, no quotes, no explanation."""
    system = "Be concise. One sentence max."
    response = _codex_chat(prompt, system=system, max_tokens=80)
    return response.strip() if response else f"{decision} — score {score}/40"
