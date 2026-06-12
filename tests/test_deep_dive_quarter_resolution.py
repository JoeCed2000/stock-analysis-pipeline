"""Fiscal-label resolution for the deep-dive quarter (NVDA FY2026-Q1-title defect).

Observed 2026-06-12 (dossier 18:53): the transcript label FY2027 Q1 was
rejected by _is_forward_quarter (fiscal 2027 > calendar 2026) and the
_period_from_filing fallback fabricated 'FY2026 Q1' from the calendar
filing year — the served PDF carried the wrong fiscal title 6 times.
"""
from datetime import datetime

import backend.pipeline as pl


TODAY = datetime(2026, 6, 12)


class TestIsForwardQuarter:
    def test_fiscal_label_one_year_ahead_is_not_forward(self):
        # NVDA fiscal year runs ~1 year ahead of calendar (FY ends late Jan).
        assert pl._is_forward_quarter("FY2027 Q1", today=TODAY) is False

    def test_fiscal_label_two_years_ahead_is_forward(self):
        assert pl._is_forward_quarter("FY2028 Q1", today=TODAY) is True

    def test_calendar_label_future_quarter_is_forward(self):
        assert pl._is_forward_quarter("2026Q4", today=TODAY) is True

    def test_calendar_label_current_quarter_is_not_forward(self):
        assert pl._is_forward_quarter("2026Q2", today=TODAY) is False


class TestResolveDeepDiveQuarter:
    def test_fiscal_period_label_is_authoritative(self, monkeypatch):
        monkeypatch.setattr(pl, "_latest_filing_period", lambda ticker: "FY2026 Q1")
        resolved = pl._resolve_deep_dive_quarter(
            ticker="NVDA",
            transcript_source={"quarter": "latest quarter"},
            yf_data={"financials": {"fiscal_period_label": "FY2027 Q1"}},
        )
        assert resolved == "FY2027 Q1"

    def test_transcript_fiscal_label_survives_forward_guard(self, monkeypatch):
        monkeypatch.setattr(pl, "_latest_filing_period", lambda ticker: None)
        resolved = pl._resolve_deep_dive_quarter(
            ticker="NVDA",
            transcript_source={"quarter": "FY2027 Q1"},
            yf_data={"financials": {}},
        )
        assert resolved == "FY2027 Q1"


class TestPeriodFromFiling:
    def test_10q_returns_honest_calendar_tag(self):
        # A calendar-derived period must stay a calendar tag: prefixing 'FY'
        # impersonates a fiscal label (mapper doctrine, _resolved_quarter_label).
        period = pl._period_from_filing({"date": "2026-05-28", "form": "10-Q"})
        assert period == "2026Q1"
        assert "FY" not in period
