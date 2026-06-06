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
    model: Optional[str] = "gpt-5.5",
    reasoning_effort: str = "low",
) -> Optional[str]:
    """Send a prompt to Codex CLI and return the response text.

    Uses stdin + ``-o`` instead of passing the full prompt as an argv value. The
    previous PTY path could exit rc=0 with an empty output file on Spark medium
    prompts; stdin is the Codex CLI's documented non-interactive path and avoids
    the zero-byte output failure.

    Args:
        model: Optional model override (e.g. 'gpt-5.5' for highest quality).
               When None, uses the default Codex model.
        reasoning_effort: Codex reasoning effort (minimal|low|medium|high). Company Overview
               uses medium for the Spark model; legacy calls keep low.
    """
    if not os.path.exists(CODEX_BIN):
        logger.warning("Codex CLI not found at %s", CODEX_BIN)
        return None

    safe_effort = reasoning_effort if reasoning_effort in {"minimal", "low", "medium", "high"} else "low"
    full_prompt = f"{system}\n\n{prompt}\n\nReturn ONLY the requested output. No explanations."
    env = os.environ.copy()
    env["HOME"] = _REAL_HOME
    last_error = None

    for attempt in range(CODEX_MAX_RETRIES + 1):
        if attempt > 0:
            backoff = CODEX_RETRY_BACKOFF[min(attempt - 1, len(CODEX_RETRY_BACKOFF) - 1)]
            jitter = backoff * 0.5 * (__import__("random").random())
            wait = backoff + jitter
            logger.info("Codex retry %d/%d after %.1fs…", attempt, CODEX_MAX_RETRIES, wait)
            time.sleep(wait)

        fd, output_file = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            args = [
                CODEX_BIN,
                "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "--json",
            ]
            if model:
                args.extend(["-m", model])
            args.extend([
                "-c", f"model_reasoning_effort={safe_effort}",
                "-o", output_file,
                "-",
            ])

            timeout = CODEX_TIMEOUT_FIRST if attempt == 0 else CODEX_TIMEOUT
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

            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                with open(output_file) as f:
                    response = f.read().strip()
                if response:
                    if attempt > 0:
                        logger.info("Codex succeeded on retry %d", attempt)
                    return response

            stdout_tail = (proc.stdout or "")[-500:]
            stderr_tail = (proc.stderr or "")[-500:]
            logger.warning(
                "Codex: no output (rc=%d, attempt %d, stdout_tail=%r, stderr_tail=%r)",
                proc.returncode,
                attempt + 1,
                stdout_tail,
                stderr_tail,
            )
            last_error = f"no_output(rc={proc.returncode})"
        except subprocess.TimeoutExpired:
            logger.warning(
                "Codex CLI timeout after %ds (attempt %d/%d, model=%s, effort=%s)",
                timeout,
                attempt + 1,
                CODEX_MAX_RETRIES + 1,
                model,
                safe_effort,
            )
            last_error = "timeout"
        except FileNotFoundError:
            logger.warning("Codex binary not found at %s", CODEX_BIN)
            return None
        except Exception as e:
            logger.warning("Codex CLI exception (attempt %d): %s", attempt + 1, e)
            last_error = str(e)
        finally:
            try:
                os.unlink(output_file)
            except OSError:
                pass

    logger.error("Codex CLI: all %d attempts failed. Last error: %s", CODEX_MAX_RETRIES + 1, last_error)
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
