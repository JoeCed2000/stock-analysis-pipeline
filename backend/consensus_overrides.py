"""Consensus estimate overrides — client-supplied reference figures.

Estimates (EPS / revenue consensus) sourced from a reference provider such as
Investing.com are stored per ticker and fiscal period in
``backend/config/consensus_overrides.json``. Overrides only replace *estimate*
fields, never company-reported actuals, and they carry an explicit provider
label so the PDF never attributes a consensus figure to SEC filings.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_OVERRIDES_PATH = Path(__file__).parent / "config" / "consensus_overrides.json"


def _load() -> Dict[str, Any]:
    try:
        with open(_OVERRIDES_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.warning("consensus_overrides.json unreadable: %s", exc)
        return {}


def get_consensus_override(ticker: str, *period_keys: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return the override entry matching the first known period key, if any."""
    entries = _load().get((ticker or "").upper())
    if not entries:
        return None
    for key in period_keys:
        if key and key in entries:
            return entries[key]
    return None


def apply_consensus_overrides(ticker: str, financials: Dict[str, Any]) -> None:
    """Apply estimate overrides in place. Estimates only — never actuals."""
    override = get_consensus_override(
        ticker,
        financials.get("fiscal_period_label"),
        financials.get("estimate_period_tag") or financials.get("period_tag"),
        "latest",
    )
    if not override:
        return
    for field in ("eps_estimate", "revenue_estimate"):
        if override.get(field) is not None:
            financials[field] = override[field]
    financials["consensus_provider"] = override.get("source", "Consensus override")
    if override.get("as_of"):
        financials["consensus_as_of"] = override["as_of"]
    logger.info("Consensus override applied for %s (%s)", ticker, override.get("source"))
