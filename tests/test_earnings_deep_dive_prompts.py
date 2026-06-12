from backend.earnings_deep_dive.prompts import eps_revenue_prompt, verdict_prompt


def test_eps_revenue_prompt_forbids_transcript_actual_when_supplied_revenue_missing():
    prompt = eps_revenue_prompt(
        language="en",
        ticker="AVGO",
        company="Broadcom Inc",
        quarter="FY2026 Q2",
        metrics={
            "eps_actual": 2.44,
            "eps_estimate": 2.40,
            "revenue_actual": None,
            "revenue_quarterly": None,
            "revenue_yoy": 0.4787,
        },
        transcript_excerpt="Revenue of $22.19B (47.87% Y/Y) beats by $115.08M.",
    )

    assert "Revenue Actual is not present in supplied_metrics" in prompt
    assert "Actual cell MUST be —" in prompt
    assert "Do NOT copy a transcript revenue" in prompt
    assert "supplied_metrics.revenue_actual or supplied_metrics.revenue_quarterly" in prompt


def test_eps_revenue_prompt_uses_supplied_quarterly_revenue_when_present():
    prompt = eps_revenue_prompt(
        language="en",
        ticker="MSFT",
        company="Microsoft",
        quarter="FY2026 Q1",
        metrics={
            "revenue_actual": None,
            "revenue_quarterly": 82_900_000_000,
        },
        transcript_excerpt="",
    )

    assert "Revenue (quarterly) = $82.90B" in prompt
    assert "Revenue Actual is not present in supplied_metrics" not in prompt


def test_verdict_prompt_requires_one_explicit_recommendation_label_en():
    prompt = verdict_prompt(
        language="en",
        ticker="NVDA",
        company="NVIDIA Corp",
        quarter="FY2026 Q1",
        metrics={"eps_actual": 6.5, "eps_estimate": 6.2},
        transcript_excerpt="",
    )

    assert "Recommendation: BUY" in prompt
    assert "Recommendation: HOLD" in prompt
    assert "Recommendation: SELL" in prompt
    assert "without making buy/sell advice" not in prompt


def test_verdict_prompt_requires_one_explicit_recommendation_label_jp():
    prompt = verdict_prompt(
        language="jp",
        ticker="NVDA",
        company="NVIDIA Corp",
        quarter="FY2026 Q1",
        metrics={"eps_actual": 6.5, "eps_estimate": 6.2},
        transcript_excerpt="",
    )

    assert "Recommendation: BUY" in prompt
    assert "Recommendation: HOLD" in prompt
    assert "Recommendation: SELL" in prompt
    assert "without making buy/sell advice" not in prompt


def test_eps_revenue_prompt_carries_consensus_provider():
    """The EPS & Revenue prompt says 'name the consensus source' — the
    actual provider must therefore be IN the prompt, otherwise the LLM
    invents one (observed: 'FactSet consensus' in a client PDF whose table
    said 'Investing.com')."""
    from backend.earnings_deep_dive.generator import _section_metrics

    metrics = {
        "eps_estimate": 1.77, "eps_actual": 1.87,
        "revenue_estimate": 79.19e9, "revenue_actual": 81.6e9,
        "consensus_provider": "Investing.com (analyst consensus)",
    }
    section_metrics = _section_metrics("EPS & Revenue", metrics)
    assert section_metrics.get("consensus_provider") == "Investing.com (analyst consensus)"

    from backend.earnings_deep_dive.prompts import build_prompt
    prompt = build_prompt(
        "EPS & Revenue", "en", "ACME", "Acme Corp", "FY2027 Q1",
        section_metrics, "Revenue beat expectations.",
    )
    assert "Investing.com (analyst consensus)" in prompt
    assert "never invent" in prompt.lower() or "do not invent" in prompt.lower()
