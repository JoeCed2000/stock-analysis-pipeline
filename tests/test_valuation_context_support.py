from backend.services.valuation_context import (
    calculate_valuation_context_summary,
    calculate_valuation_support,
)


def _sig(level: str) -> dict[str, object]:
    return {"level": level}


def test_valuation_support_dead_heat_with_neutral_is_mixed():
    """Regression: 1 support / 1 neutral / 1 concern must be mixed, not supportive."""
    support = calculate_valuation_support(
        peg_signal=_sig("below_1"),      # support
        ps_vs_growth=_sig("moderate"),   # neutral
        ev_ebitda_vs_growth=_sig("weak"),  # concern
    )

    assert support["support"] == 1
    assert support["neutral"] == 1
    assert support["concern"] == 1
    assert support["dominant"] == "mixed"

    summary = calculate_valuation_context_summary(
        peg_signal=_sig("below_1"),
        ps_vs_growth=_sig("moderate"),
        ev_ebitda_vs_growth=_sig("weak"),
    )
    assert summary["valuation_level"] == "mixed_signals"


def test_valuation_support_dead_heat_without_neutral_is_mixed():
    support = calculate_valuation_support(
        peg_signal=_sig("below_1"),
        ps_vs_growth=_sig("weak"),
    )

    assert support["support"] == 1
    assert support["neutral"] == 0
    assert support["concern"] == 1
    assert support["dominant"] == "mixed"


def test_valuation_support_stays_supportive_when_support_leads():
    support = calculate_valuation_support(
        peg_signal=_sig("below_1"),
        ps_vs_growth=_sig("strong"),
        ev_ebitda_vs_growth=_sig("weak"),
    )

    assert support["support"] == 2
    assert support["concern"] == 1
    assert support["dominant"] == "supportive"
