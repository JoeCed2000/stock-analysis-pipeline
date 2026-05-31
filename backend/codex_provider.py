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


def _codex_chat(prompt: str, system: str = "", max_tokens: int = 1000, model: Optional[str] = "gpt-5.5") -> Optional[str]:
    """Send a prompt to Codex CLI via PTY and return the response text.
    
    Retries up to CODEX_MAX_RETRIES times with exponential backoff on timeout/failure.
    Serializes subprocess launches via a global lock to avoid Cloudflare rate-limiting
    when EN and JP deep-dive generations run in parallel.
    
    Args:
        model: Optional model override (e.g. 'gpt-5.3-spark' for cheap fallback).
               When None, uses the default Codex model.
    """
    if not os.path.exists(CODEX_BIN):
        logger.warning("Codex CLI not found at %s", CODEX_BIN)
        return None

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
        full_prompt = f"{system}\n\n{prompt}\n\nReturn ONLY the requested output. No explanations."

        master_fd = None
        try:
            # Serialize launches to avoid Cloudflare rate-limit on parallel EN+JP
            with _codex_launch_lock:
                master_fd, slave_fd = os.openpty()
                
                args = [CODEX_BIN, "exec",
                        "--ephemeral",
                        "--skip-git-repo-check",
                        "--json"]
                if model:
                    args.extend(["-m", model])
                args.extend(["-c", "model_reasoning_effort=low",
                             "-o", output_file,
                             full_prompt])
                
                # Build environment with real HOME so Codex finds auth.json
                env = os.environ.copy()
                env["HOME"] = _REAL_HOME

                proc = subprocess.Popen(
                    args,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    close_fds=True,
                    env=env,
                )
                
                os.close(slave_fd)
            
            # Wait with timeout — check output file for early progress signal
            timeout = CODEX_TIMEOUT_FIRST if attempt == 0 else CODEX_TIMEOUT
            start = time.time()
            while proc.poll() is None:
                elapsed = time.time() - start
                # If output file is still empty after 120s, Spark is truly hung (not slow)
                output_size = os.path.exists(output_file) and os.path.getsize(output_file) or 0
                if elapsed > CODEX_TIMEOUT_FIRST and output_size == 0:
                    proc.kill()
                    logger.warning("Codex CLI hung — no output after %ds (attempt %d/%d)",
                                   int(elapsed), attempt + 1, CODEX_MAX_RETRIES + 1)
                    os.close(master_fd)
                    last_error = "hung"
                    break
                if elapsed > timeout:
                    proc.kill()
                    logger.warning("Codex CLI timeout after %ds (attempt %d/%d, output=%d bytes)",
                                   int(elapsed), attempt + 1, CODEX_MAX_RETRIES + 1, output_size)
                    os.close(master_fd)
                    last_error = "timeout"
                    break  # will retry
                time.sleep(0.5)
            else:
                # Process exited normally
                os.close(master_fd)
                
                # Read output file
                if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                    with open(output_file) as f:
                        response = f.read().strip()
                    if response:
                        if attempt > 0:
                            logger.info("Codex succeeded on retry %d", attempt)
                        return response
                
                logger.warning("Codex: no output (rc=%d, attempt %d)", proc.returncode, attempt + 1)
                last_error = f"no_output(rc={proc.returncode})"

        except FileNotFoundError:
            if master_fd is not None:
                try: os.close(master_fd)
                except OSError: pass
            logger.warning("Codex binary not found at %s", CODEX_BIN)
            return None
        except Exception as e:
            if master_fd is not None:
                try: os.close(master_fd)
                except OSError: pass
            logger.warning("Codex CLI exception (attempt %d): %s", attempt + 1, e)
            last_error = str(e)
        finally:
            try:
                os.unlink(output_file)
            except OSError:
                pass

    logger.error("Codex CLI: all %d attempts failed. Last error: %s",
                 CODEX_MAX_RETRIES + 1, last_error)
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
