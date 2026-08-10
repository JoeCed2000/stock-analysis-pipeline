from datetime import date

from backend.company_overview import (
    _apply_verified_leadership_transition,
    _backfill_company_profile,
)


APPLE_TRANSITION = {
    "title": "Tim Cook to become Apple Executive Chairman John Ternus to become Apple CEO",
    "url": (
        "https://www.apple.com/newsroom/2026/04/"
        "tim-cook-to-become-apple-executive-chairman-john-ternus-to-become-apple-ceo/"
    ),
    "content": (
        "Apple announced that Tim Cook will become executive chairman and John Ternus, "
        "senior vice president of Hardware Engineering, will become Apple's next chief "
        "executive officer effective on September 1, 2026."
    ),
    "date": "2026-04-20",
}


def test_official_future_ceo_transition_keeps_current_ceo_and_names_designate():
    overview = {
        "company_profile": {
            "ceo": "Tim Cook",
            "website": "https://www.apple.com",
        },
        "ceo_leadership_style": (
            "CEO information not available from current structured data sources. "
            "Investors should consult proxy statements."
        ),
    }

    _apply_verified_leadership_transition(
        overview,
        [APPLE_TRANSITION],
        as_of=date(2026, 7, 12),
    )

    profile = overview["company_profile"]
    assert profile["ceo"] == "Tim Cook"
    assert profile["ceo_designate"] == "John Ternus"
    assert profile["ceo_effective_date"] == "2026-09-01"
    assert profile["ceo_transition_source_url"] == APPLE_TRANSITION["url"]
    assert "Tim Cook remains CEO through August 31, 2026" in overview["ceo_leadership_style"]
    assert "John Ternus is CEO-designate" in overview["ceo_leadership_style"]
    assert "CEO information not available" not in overview["ceo_leadership_style"]


def test_official_effective_transition_promotes_designate_to_current_ceo():
    overview = {
        "company_profile": {
            "ceo": "Tim Cook",
            "website": "https://www.apple.com",
        }
    }

    _apply_verified_leadership_transition(
        overview,
        [APPLE_TRANSITION],
        as_of=date(2026, 9, 1),
    )

    profile = overview["company_profile"]
    assert profile["ceo"] == "John Ternus"
    assert profile["former_ceo"] == "Tim Cook"
    assert "ceo_designate" not in profile


def test_unofficial_transition_claim_is_ignored():
    overview = {
        "company_profile": {
            "ceo": "Tim Cook",
            "website": "https://www.apple.com",
        }
    }
    claim = {**APPLE_TRANSITION, "url": "https://rumors.example/apple-ceo"}

    _apply_verified_leadership_transition(
        overview,
        [claim],
        as_of=date(2026, 7, 12),
    )

    assert overview["company_profile"] == {
        "ceo": "Tim Cook",
        "website": "https://www.apple.com",
    }


def test_profile_backfill_uses_raw_yahoo_identity_fields():
    overview = {"company_profile": {"website": None, "country": None}}
    snapshot = {
        "_raw_info": {
            "longName": "Apple Inc.",
            "website": "https://www.apple.com",
            "country": "United States",
            "city": "Cupertino",
            "state": "CA",
            "fullTimeEmployees": 166000,
            "companyOfficers": [
                {"name": "Tim Cook", "title": "Chief Executive Officer"}
            ],
        }
    }

    _backfill_company_profile(overview, snapshot)

    assert overview["company_profile"]["name"] == "Apple Inc."
    assert overview["company_profile"]["website"] == "https://www.apple.com"
    assert overview["company_profile"]["country"] == "United States"
    assert overview["company_profile"]["headquarters"] == "Cupertino, CA, United States"
    assert overview["company_profile"]["employees"] == 166000
    assert overview["company_profile"]["ceo"] == "Tim Cook"


def test_verified_registry_covers_announced_apple_transition_without_search_results():
    overview = {
        "company_profile": {
            "ceo": "Tim Cook",
            "website": "https://www.apple.com",
        }
    }

    _apply_verified_leadership_transition(
        overview,
        [],
        ticker="AAPL",
        as_of=date(2026, 7, 12),
    )

    profile = overview["company_profile"]
    assert profile["ceo"] == "Tim Cook"
    assert profile["ceo_designate"] == "John Ternus"
    assert profile["ceo_effective_date"] == "2026-09-01"
    assert profile["ceo_transition_source_url"].startswith(
        "https://www.apple.com/newsroom/2026/04/"
    )
