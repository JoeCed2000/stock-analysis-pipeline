"""Regression spec: NVDA FY2027 Q1 EPS/Revenue override is positioned
FIRST in the prompt (before the DATA CONTRACT) so the LLM reads explicit
values before conservative data-discipline rules.

Acceptance criteria:
- CRITICAL OVERRIDE text (EPS 1.77, Revenue 79.19B) is present
- CRITICAL OVERRIDE appears BEFORE the DATA CONTRACT section
- Consensus provider (Investing.com) is present
"""

from backend.earnings_deep_dive.generator import _section_metrics
from backend.earnings_deep_dive.prompts import build_prompt

NVDA_OVERRIDE_METRICS = {
    "eps_estimate": 1.77,
    "eps_actual": 0.89,
    "revenue_estimate": 79_190_000_000,
    "revenue_actual": 81_600_000_000,
    "consensus_provider": "Investing.com (analyst consensus)",
    "revenue_yoy": 0.398,
    "eps_yoy": -0.395,
}


def test_eps_revenue_critical_override_present():
    """CRITICAL OVERRIDE text with EPS 1.77 / Revenue 79.19B is present."""
    section_metrics = _section_metrics("EPS & Revenue", dict(NVDA_OVERRIDE_METRICS))
    prompt = build_prompt(
        "EPS & Revenue", "en", "NVDA", "NVIDIA Corp", "FY2027 Q1",
        section_metrics, "Revenue exceeded expectations due to data center growth.",
    )

    assert "EPS" in prompt
    assert "1.77" in prompt, "EPS estimate 1.77 must appear in the prompt"
    assert "79.19B" in prompt or "79190000000" in prompt, (
        "Revenue estimate 79.19B must appear in the prompt"
    )
    assert "Investing.com" in prompt, (
        "Consensus provider Investing.com must appear in the prompt"
    )


def test_eps_revenue_critical_override_before_data_contract():
    """CRITICAL OVERRIDE text appears BEFORE the DATA CONTRACT.

    This is the regression check: the override must be positioned first
    so the LLM reads explicit values BEFORE conservative data-discipline
    rules like 'If a metric is missing → write —'.
    """
    section_metrics = _section_metrics("EPS & Revenue", dict(NVDA_OVERRIDE_METRICS))
    prompt = build_prompt(
        "EPS & Revenue", "en", "NVDA", "NVIDIA Corp", "FY2027 Q1",
        section_metrics, "Revenue exceeded expectations due to data center growth.",
    )

    assert "CRITICAL OVERRIDE" in prompt, (
        "CRITICAL OVERRIDE must be present in the prompt"
    )
    assert "DATA CONTRACT" in prompt, (
        "DATA CONTRACT must be present in the prompt"
    )

    override_idx = prompt.index("CRITICAL OVERRIDE")
    contract_idx = prompt.index("DATA CONTRACT")

    assert override_idx < contract_idx, (
        f"CRITICAL OVERRIDE (position {override_idx}) must come BEFORE "
        f"DATA CONTRACT (position {contract_idx}). Currently override "
        f"is appended AFTER the base prompt, and the LLM prioritizes "
        f"the earlier conservative 'write —' instruction."
    )


def test_eps_revenue_override_present_jp():
    """Same override check for Japanese (JP) language."""
    section_metrics = _section_metrics("EPS & Revenue", dict(NVDA_OVERRIDE_METRICS))
    prompt = build_prompt(
        "EPS & Revenue", "jp", "NVDA", "NVIDIA Corp", "FY2027 Q1",
        section_metrics, "Revenue exceeded expectations due to data center growth.",
    )

    assert "CRITICAL OVERRIDE" in prompt
    assert "1.77" in prompt, "EPS estimate 1.77 must appear in JP prompt"
    assert "DATA CONTRACT" in prompt

    override_idx = prompt.index("CRITICAL OVERRIDE")
    contract_idx = prompt.index("DATA CONTRACT")
    assert override_idx < contract_idx, (
        "CRITICAL OVERRIDE must come before DATA CONTRACT in JP as well"
    )
