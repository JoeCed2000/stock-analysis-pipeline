"""Press release fetcher must be quarter-aware and ticker-generic.

Regression (2026-06-12): a hardcoded NVDA candidate list tried
fourth→first quarter URLs of the current calendar year and returned the
first HTTP 200 — the Q4 FY2026 press release shipped in a Q1 FY2027
client report (pages 1 + 20). The fix removes every ticker hardcode and
scores search candidates against the resolved fiscal label.
"""
import pytest

from backend import press_release_fetcher as prf


class TestFiscalHintParsing:
    def test_fy_label(self):
        assert prf._parse_fiscal_hint("FY2027 Q1") == (2027, 1)

    def test_calendar_tag(self):
        assert prf._parse_fiscal_hint("2026Q2") == (2026, 2)

    def test_garbage(self):
        assert prf._parse_fiscal_hint("latest") == (None, None)
        assert prf._parse_fiscal_hint(None) == (None, None)


class TestQuarterScoring:
    def test_matching_quarter_and_year_scores_highest(self):
        url = "https://news.example.com/acme-announces-financial-results-first-quarter-fiscal-2027"
        assert prf._url_quarter_score(url, 2027, 1) > 0

    def test_wrong_quarter_scores_negative(self):
        url = "https://news.example.com/acme-announces-financial-results-for-fourth-quarter-and-fiscal-2026"
        assert prf._url_quarter_score(url, 2027, 1) < 0

    def test_no_hint_is_neutral(self):
        url = "https://news.example.com/acme-q2-earnings"
        assert prf._url_quarter_score(url, None, None) == 0


class TestFindPressReleaseUrl:
    def test_prefers_hinted_quarter_among_candidates(self, monkeypatch):
        wrong = "https://ir.acme.example/news/acme-announces-financial-results-for-fourth-quarter-and-fiscal-2026"
        right = "https://ir.acme.example/news/acme-announces-financial-results-first-quarter-fiscal-2027"
        monkeypatch.setattr(prf, "_search_press_release_urls", lambda t, q: [wrong, right])

        url = prf.find_press_release_url("ACME", fiscal_label="FY2027 Q1")

        assert url == right

    def test_rejects_only_wrong_quarter_candidates(self, monkeypatch):
        """A wrong-period press release is worse than none: the report says
        'Unavailable from reviewed sources' instead of citing last quarter."""
        wrong = "https://ir.acme.example/news/acme-announces-financial-results-for-fourth-quarter-and-fiscal-2026"
        monkeypatch.setattr(prf, "_search_press_release_urls", lambda t, q: [wrong])

        assert prf.find_press_release_url("ACME", fiscal_label="FY2027 Q1") is None

    def test_without_hint_first_trusted_candidate_wins(self, monkeypatch):
        first = "https://ir.acme.example/news/acme-q3-fiscal-2026-earnings"
        monkeypatch.setattr(prf, "_search_press_release_urls", lambda t, q: [first])

        assert prf.find_press_release_url("ACME") == first

    def test_no_ticker_hardcode_left(self):
        """No per-ticker behavior branches. The trusted-host allowlist may
        legitimately contain official newsroom domains (incl. nvidianews) —
        that filters sources, it does not special-case behavior."""
        import inspect
        src = inspect.getsource(prf)
        assert "_nvidia_candidate_urls" not in src
        assert 'ticker_clean == "NVDA"' not in src


class TestMultiQuerySearch:
    def test_site_restricted_query_finds_hinted_release(self, monkeypatch):
        """The generic query can miss the official newsroom page; a second,
        site-restricted query must be tried before giving up (no-NA policy:
        the release exists, find it)."""
        right = "https://newsroom.acme.example/acme-announces-financial-results-first-quarter-fiscal-2027"
        calls = []

        def fake_search(ticker, query):
            calls.append(query)
            return [right] if query.startswith("site:") else []

        monkeypatch.setattr(prf, "_search_press_release_urls", fake_search)
        url = prf.find_press_release_url(
            "ACME", fiscal_label="FY2027 Q1", company_website="https://www.acme.example",
        )
        assert url == right
        assert any(q.startswith("site:acme.example") for q in calls)

    def test_stops_querying_once_positive_candidate_found(self, monkeypatch):
        right = "https://ir.acme.example/acme-first-quarter-fiscal-2027-results"
        calls = []

        def fake_search(ticker, query):
            calls.append(query)
            return [right]

        monkeypatch.setattr(prf, "_search_press_release_urls", fake_search)
        assert prf.find_press_release_url("ACME", fiscal_label="FY2027 Q1") == right
        assert len(calls) == 1
