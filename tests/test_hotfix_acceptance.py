"""Hotfix acceptance tests (post-f2d0f5c): override priority, surprise values,
fiscal-label prose repair, net cash filing override, highlights conciseness."""
import backend.pipeline as pl
from backend.earnings_deep_dive.mapper import (
    _rows_for_section,
    _ensure_section_commentary,
    _cap_section_length,
    build_earnings_deep_dive_report,
)
from backend.earnings_deep_dive.schemas import FinancialMetrics


def _nvda_metrics(monkeypatch, comparison):
    """Build metrics through the real pipeline path with a hostile
    quarterly_comparison that previously clobbered the consensus override."""
    monkeypatch.setattr(pl, "_extract_quarterly_comparison", lambda t: comparison)
    result = type("R", (), {"ticker": "NVDA", "financials": None, "valuation": None})()
    fin_data = {
        "fiscal_period_label": "FY2027 Q1",
        "period_tag": "2026Q2",
        "eps_actual": 1.87,
        "revenue_quarterly": 81.6e9,
    }
    return pl._deep_dive_metrics(result, {"ticker": "NVDA", "financials": fin_data})


HOSTILE_COMPARISON = {
    "eps_actual": 1.87,
    "eps_estimate": 1.77191,        # unrounded yfinance value
    "revenue_actual": 81.6e9,
    "revenue_estimate": 81.602824e9,  # ~= actual (the original client defect)
    "net_debt": -68.224e9,          # yfinance-only, missing LT marketable equity
    "cash_and_marketable_securities": 76.7e9,
}


class TestOverrideFinalPriority:
    def test_consensus_override_beats_quarterly_comparison(self, monkeypatch):
        m = _nvda_metrics(monkeypatch, dict(HOSTILE_COMPARISON))
        assert m.eps_estimate == 1.77
        assert m.revenue_estimate == 79.19e9
        assert m.eps_actual == 1.87          # actuals NOT overridden
        assert "investing" in (m.consensus_provider or "").lower()

    def test_net_cash_filing_override_beats_yfinance(self, monkeypatch):
        m = _nvda_metrics(monkeypatch, dict(HOSTILE_COMPARISON))
        assert m.net_debt == -72.102e9
        assert m.cash_and_marketable_securities == 80.572e9

    def test_surprise_rows_match_acceptance(self, monkeypatch):
        m = _nvda_metrics(monkeypatch, dict(HOSTILE_COMPARISON))
        rows = _rows_for_section("EPS & Revenue", ("EPS", "Revenue"), m)
        assert rows[0][3] == "+5.65%"   # (1.87-1.77)/1.77
        assert rows[1][3] == "+3.04%"   # (81.6-79.19)/79.19
        assert "Investing.com" in rows[0][5] and "Investing.com" in rows[1][5]

    def test_net_cash_row_displays_72_1B(self, monkeypatch):
        m = _nvda_metrics(monkeypatch, dict(HOSTILE_COMPARISON))
        rows = _rows_for_section(
            "Cash Flow", ("Operating cash flow", "CapEx", "Free cash flow", "Net debt"), m)
        net_row = next(r for r in rows if "Net Cash" in r[0])
        assert "$72.1B" in net_row[1]

    def test_no_override_ticker_keeps_comparison_values(self, monkeypatch):
        monkeypatch.setattr(pl, "_extract_quarterly_comparison",
                            lambda t: dict(HOSTILE_COMPARISON))
        result = type("R", (), {"ticker": "ZZZZ", "financials": None, "valuation": None})()
        m = pl._deep_dive_metrics(result, {"ticker": "ZZZZ", "financials": {}})
        assert m.eps_estimate == 1.77191  # unchanged path for non-override tickers


class TestFiscalLabelProse:
    def test_calendar_tag_repaired_in_prose(self):
        metrics = FinancialMetrics(fiscal_period_label="FY2027 Q1")
        report = build_earnings_deep_dive_report(
            ticker="NVDA", company="NVIDIA Corporation", quarter="2026Q2",
            language="en", metrics=metrics, transcript_url="",
            section_analysis={
                "EPS & Revenue": "The 2026Q2 quarter shows momentum; 2026Q2 execution matters."
            },
        )
        dump = report.model_dump_json()
        assert "2026Q2" not in dump, "calendar tag must not leak into the report model"
        assert report.quarter == "FY2027 Q1"


class TestHighlightsConciseness:
    VERBOSE = (
        "| Type | Number | Point | Evidence | Investor implication | Severity |\n"
        "|---|---|---|---|---|---|\n"
        "| Highlight | 1 | Operational | " + ("EPS beat with long evidence text. " * 40) + " | High | Low |\n\n"
        + ("This is a very long analytical paragraph repeating itself with dense prose. " * 60)
    )

    def test_verbose_llm_output_replaced_by_concise_fallback(self):
        metrics = FinancialMetrics(
            revenue_actual=81.6e9, revenue_estimate=79.19e9, eps_actual=1.87,
            eps_estimate=1.77, free_cash_flow=48.6e9, pe_forward=42.0)
        out = _ensure_section_commentary("en", "NVDA", "Highlights", metrics, [self.VERBOSE])
        combined = "\n".join(out)
        assert len(combined) <= 2600
        assert combined.count("Lowlight") >= 1
        assert combined.count("•") >= 6
        assert "Required table" not in combined
        assert not any(len(l) > 600 for l in combined.split("\n"))

    def test_conforming_concise_output_kept(self):
        concise = (
            "Highlights\n1. Growth\n   • Revenue up.\n   • EPS beat.\n"
            "2. Margins\n   • GM strong.\n3. Cash\n   • FCF solid.\n\n"
            "Lowlights\n1. Expectations\n   • High P/E.\n2. China\n   • Constrained.\n"
            "3. Capex cycle\n   • Watch spending."
        )
        out = _ensure_section_commentary("en", "NVDA", "Highlights", FinancialMetrics(), [concise])
        assert out == [concise]

    def test_eps_revenue_prose_capped(self):
        long_prose = "\n\n".join(f"Paragraph {i}. " + "x" * 400 for i in range(10))
        out = _ensure_section_commentary("en", "NVDA", "EPS & Revenue", FinancialMetrics(eps_actual=1.0), [long_prose])
        assert sum(len(p) for p in out) <= 1600 + 450  # cap + final paragraph tolerance

    def test_cap_keeps_first_paragraph(self):
        items = ["A" * 3000]
        assert _cap_section_length(items, max_chars=100) == ["A" * 3000]


class TestFinalPdfDefects:
    """Defects found while verifying the real final generation (post-hotfix)."""

    def test_verdict_eps_beat_without_explicit_surprise(self):
        from backend.earnings_deep_dive.mapper import _verdict_rows
        m = FinancialMetrics(eps_actual=1.87, eps_estimate=1.77,
                             revenue_actual=81.6e9, operating_cash_flow=27.7e9)
        rows = _verdict_rows(m, ("Earnings quality", "Growth durability",
                                 "Cash & balance sheet", "Valuation", "Overall"))
        flat = " | ".join(" ".join(r) for r in rows)
        assert "did not beat" not in flat
        assert "beat" in flat

    def test_highlights_rows_eps_beat_without_explicit_surprise(self):
        from backend.earnings_deep_dive.mapper import _highlights_rows
        m = FinancialMetrics(eps_actual=1.87, eps_estimate=1.77)
        flat = " | ".join(" ".join(r) for r in _highlights_rows(m, ("a", "b", "c")))
        assert "did not beat" not in flat

    def test_highlights_summary_has_no_bare_q_label(self):
        from backend.earnings_deep_dive.mapper import _summary
        text = _summary("en", "NVDA", "Highlights", FinancialMetrics(
            revenue_actual=81.6e9, revenue_yoy=0.852, eps_actual=1.87))
        assert " Q: " not in text

    def test_source_parenthetical_cleanup_never_spans_lines(self):
        from backend.earnings_deep_dive.markdown import post_process_markdown
        md = (
            "power (source: company metrics; earnings call transcript\n\n"
            "## Verdict\n\n**Recommendation: BUY**\n\n"
            "| Dimension | Source |\n|---|---|\n| Strengths (note) | SEC |\n"
        )
        out = post_process_markdown(md)
        assert "\n## Verdict\n" in out
        assert "\n**Recommendation: BUY**\n" in out
