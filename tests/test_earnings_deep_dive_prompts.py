from backend.earnings_deep_dive.prompts import eps_revenue_prompt


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
