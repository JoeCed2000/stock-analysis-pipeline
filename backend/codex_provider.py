"""Codex CLI LLM provider — replaces Kimi K2.6 for pipeline NLP tasks.
Uses os.openpty() for PTY (required by Codex CLI).
"""
import os
import json
import logging
import subprocess
import tempfile
import time
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

CODEX_BIN = os.path.expanduser("~/.hermes/node/bin/codex")
CODEX_TIMEOUT = 300  # seconds (was 120 — JP deep-dive needs more)


def _codex_chat(prompt: str, system: str = "", max_tokens: int = 1000) -> Optional[str]:
    """Send a prompt to Codex CLI via PTY and return the response text."""
    if not os.path.exists(CODEX_BIN):
        logger.warning("Codex CLI not found at %s", CODEX_BIN)
        return None

    fd, output_file = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    full_prompt = f"{system}\n\n{prompt}\n\nReturn ONLY the requested output. No explanations."

    try:
        # Open PTY pair
        master_fd, slave_fd = os.openpty()
        
        proc = subprocess.Popen(
            [CODEX_BIN, "exec",
             "--ephemeral",
             "--skip-git-repo-check",
             "--json",
             "-c", "model_reasoning_effort=low",
             "-o", output_file,
             full_prompt],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )
        
        # Close slave fd in parent (child uses it)
        os.close(slave_fd)
        
        # Wait with timeout
        start = time.time()
        while proc.poll() is None:
            if time.time() - start > CODEX_TIMEOUT:
                proc.kill()
                logger.warning("Codex CLI timeout after %ds", CODEX_TIMEOUT)
                os.close(master_fd)
                return None
            time.sleep(0.5)
        
        os.close(master_fd)
        
        # Read output file
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            with open(output_file) as f:
                response = f.read().strip()
            if response:
                return response
        
        logger.warning("Codex: no output (rc=%d)", proc.returncode)
        return None
        
    except FileNotFoundError:
        logger.warning("Codex binary not found at %s", CODEX_BIN)
        return None
    except Exception as e:
        logger.warning("Codex CLI exception: %s", e)
        return None
    finally:
        try:
            os.unlink(output_file)
        except OSError:
            pass


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
