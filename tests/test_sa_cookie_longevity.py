"""Tests for cookie longevity categorization, smart HAR merge, and freshness.

These tests cover the new behavior added in 2026-06-11 to make SA
cookies last longer:

  * ``_categorize_cookie_longevity`` — classifies each cookie name as
    LONG / MEDIUM / SHORT / UNKNOWN so the smart merge knows what to
    keep and what to overwrite.
  * ``_estimate_expires_at`` — converts a HAR ``expires`` value (or
    lack thereof) into a usable expiry epoch, defaulting to a
    category-appropriate TTL.
  * ``_compute_cookie_freshness`` — drives the admin freshness
    endpoint and decides whether to trigger a Firefox refresh.
  * ``import_har_cookies`` — must preserve long-lived auth cookies
    from the existing store when a fresh HAR is missing them.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from backend import seeking_alpha_access as sa


# ─────────────────────────────────────────────────────────────────────
# Cookie longevity classification
# ─────────────────────────────────────────────────────────────────────


class TestCookieLongevity:
    def test_long_lived_auth_cookies(self):
        for name in [
            "slireg",
            "sa-user-id-v3",
            "user_remember_token",
            "gk_user_access",
            "user_nick",
            "sapu",
            "sailthru_hid",
        ]:
            assert sa._categorize_cookie_longevity(name) == "LONG", name

    def test_medium_lived_cookies(self):
        for name in ["session_id", "pxcts", "_px3", "_pxvid", "machine_cookie", "ever_pro"]:
            assert sa._categorize_cookie_longevity(name) == "MEDIUM", name

    def test_short_lived_cookies_exact(self):
        for name in ["_ga", "_fbp", "_fbc", "_gcl_au", "_twpid", "hubspotutk", "g_state"]:
            assert sa._categorize_cookie_longevity(name) == "SHORT", name

    def test_short_lived_cookies_wildcard(self):
        for name in ["_ga_KGRFF2R2C5", "_hjSessionUser_65666", "_hjAbsoluteSessionIn",
                     "amplitude_id_abc", "mp_abc_mixpanel", "_ttp"]:
            assert sa._categorize_cookie_longevity(name) == "SHORT", name

    def test_unknown_cookie(self):
        assert sa._categorize_cookie_longevity("totally-unknown-thing-xyz") == "UNKNOWN"

    def test_empty_cookie(self):
        assert sa._categorize_cookie_longevity("") == "UNKNOWN"


# ─────────────────────────────────────────────────────────────────────
# _estimate_expires_at
# ─────────────────────────────────────────────────────────────────────


class TestEstimateExpiresAt:
    def test_session_cookie_longevity_default(self):
        now = time.time()
        exp = sa._estimate_expires_at("_ga", -1)
        # _ga is SHORT, default 24h
        assert exp is not None
        assert 23 * 3600 < (exp - now) < 25 * 3600

    def test_long_lived_session_default_is_30_days(self):
        now = time.time()
        exp = sa._estimate_expires_at("slireg", -1)
        assert exp is not None
        assert 29 * 24 * 3600 < (exp - now) < 31 * 24 * 3600

    def test_explicit_har_expires_is_preserved(self):
        far_future = time.time() + 365 * 24 * 3600
        exp = sa._estimate_expires_at("_ga", far_future)
        assert exp == far_future

    def test_expired_har_falls_back_to_category_default(self):
        ancient = time.time() - 30 * 24 * 3600  # 30 days ago
        now = time.time()
        exp = sa._estimate_expires_at("slireg", ancient)
        # 30 days old + LONG default = ~30 days from now
        assert exp is not None
        assert 29 * 24 * 3600 < (exp - now) < 31 * 24 * 3600

    def test_none_or_zero_uses_default(self):
        now = time.time()
        for har_exp in (None, 0, -1):
            exp = sa._estimate_expires_at("session_id", har_exp)
            # MEDIUM default = 7 days
            assert exp is not None
            assert 6 * 24 * 3600 < (exp - now) < 8 * 24 * 3600


# ─────────────────────────────────────────────────────────────────────
# _cookies_by_name
# ─────────────────────────────────────────────────────────────────────


class TestCookiesByName:
    def test_indexes_by_name(self):
        cookies = [
            {"name": "a", "value": "1", "domain": ".x.com"},
            {"name": "b", "value": "2", "domain": ".x.com"},
        ]
        out = sa._cookies_by_name(cookies)
        assert out == {"a": cookies[0], "b": cookies[1]}

    def test_handles_empty_list(self):
        assert sa._cookies_by_name([]) == {}

    def test_handles_none(self):
        assert sa._cookies_by_name(None) == {}

    def test_skips_empty_names(self):
        cookies = [{"name": "", "value": "1"}, {"name": "b", "value": "2"}]
        out = sa._cookies_by_name(cookies)
        assert "b" in out
        assert "" not in out


# ─────────────────────────────────────────────────────────────────────
# import_har_cookies smart merge
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    d = tmp_path / ".state"
    monkeypatch.setattr("backend.seeking_alpha_access.STATE_DIR", d)
    return d


def _make_har(cookies: list[dict], user_agent: str | None = None) -> Path:
    """Build a minimal valid HAR file with the given cookies.

    Each entry's cookies are structured (so expires is honored), and we
    add a Cookie header to cover both parse paths.
    """
    header = f"Mozilla/5.0 Test" if user_agent is None else user_agent
    entries = []
    for c in cookies:
        entries.append({
            "request": {
                "url": c.get("url", "https://seekingalpha.com/symbol/NVDA"),
                "cookies": [{
                    "name": c["name"],
                    "value": c["value"],
                    "expires": c.get("expires", -1),
                }],
                "headers": [
                    {"name": "Cookie", "value": "; ".join(
                        f"{x['name']}={x['value']}" for x in cookies
                    )},
                    {"name": "User-Agent", "value": header},
                ],
            },
        })
    har = {"log": {"version": "1.2", "entries": entries}}
    p = Path("/tmp/test_har.json")
    p.write_text(json.dumps(har), encoding="utf-8")
    return p


class TestHarSmartMerge:
    def test_fresh_har_creates_complete_store(self, state_dir):
        har = _make_har([
            {"name": "slireg", "value": "abc"},
            {"name": "sa-user-id-v3", "value": "xyz"},
            {"name": "_ga", "value": "GA1.1.123"},
        ])
        result = sa.import_har_cookies(har)
        assert result["configured"] is True
        # slireg + sa-user-id-v3 = 2 long, _ga = 1 short, total 3
        assert result["cookie_count"] == 3

    def test_har_preserves_long_lived_when_missing(self, state_dir):
        """When a fresh HAR omits slireg, the existing store's slireg is kept.

        With the downgrade-protection fix, even when the HAR DOES carry
        the same long-lived name (sa-user-id-v3), the store's still-valid
        copy wins over the HAR's value. To force replacement, the user
        must clear the store first.
        """
        # Step 1: upload a full HAR
        future = time.time() + 30 * 24 * 3600
        har_full = _make_har([
            {"name": "slireg", "value": "ORIGINAL_SLIREG", "expires": future},
            {"name": "sa-user-id-v3", "value": "ORIGINAL_SA_V3", "expires": future},
            {"name": "_ga", "value": "GA1.1.111", "expires": -1},
        ])
        sa.import_har_cookies(har_full)

        # Step 2: upload a partial HAR (missing slireg, has different
        # sa-user-id-v3 and _ga). The store wins for ALL long-lived
        # because it's still valid. Short-lived (_ga) is overwritten.
        har_partial = _make_har([
            {"name": "sa-user-id-v3", "value": "FRESH_SA_V3", "expires": -1},
            {"name": "_ga", "value": "GA1.1.222", "expires": -1},
        ])
        sa.import_har_cookies(har_partial)

        # The store should still have all 3 cookies
        names = {c["name"] for c in sa._read_store().get("cookies_parsed", [])}
        assert "slireg" in names, "slireg must be preserved (HAR missing it)"
        assert "sa-user-id-v3" in names
        assert "_ga" in names

        store_cookies = sa._read_store().get("cookies_parsed", [])

        # slireg value must be the ORIGINAL (not in HAR → kept)
        slireg = next(c for c in store_cookies if c["name"] == "slireg")
        assert slireg["value"] == "ORIGINAL_SLIREG"

        # sa-user-id-v3 must STILL be the ORIGINAL (downgrade protected)
        sa_v3 = next(c for c in store_cookies if c["name"] == "sa-user-id-v3")
        assert sa_v3["value"] == "ORIGINAL_SA_V3", (
            "sa-user-id-v3 should be downgrade-protected when the store's "
            "expiry is fresher than the HAR"
        )

        # _ga was free to update (SHORT-lived)
        ga = next(c for c in store_cookies if c["name"] == "_ga")
        assert ga["value"] == "GA1.1.222"

    def test_har_short_lived_overwrites_every_time(self, state_dir):
        har1 = _make_har([{"name": "_ga", "value": "v1"}])
        sa.import_har_cookies(har1)

        har2 = _make_har([{"name": "_ga", "value": "v2"}])
        sa.import_har_cookies(har2)

        store = sa._read_store()
        ga = next(c for c in store["cookies_parsed"] if c["name"] == "_ga")
        assert ga["value"] == "v2"

    def test_each_cookie_has_longevity_field(self, state_dir):
        har = _make_har([
            {"name": "slireg", "value": "x"},
            {"name": "_ga", "value": "y"},
            {"name": "session_id", "value": "z"},
        ])
        sa.import_har_cookies(har)
        store = sa._read_store()
        by_name = {c["name"]: c for c in store["cookies_parsed"]}
        assert by_name["slireg"]["longevity"] == "LONG"
        assert by_name["_ga"]["longevity"] == "SHORT"
        assert by_name["session_id"]["longevity"] == "MEDIUM"

    def test_each_cookie_has_expires_at(self, state_dir):
        har = _make_har([{"name": "slireg", "value": "x", "expires": -1}])
        sa.import_har_cookies(har)
        slireg = next(c for c in sa._read_store()["cookies_parsed"] if c["name"] == "slireg")
        assert "expires_at" in slireg
        assert slireg["expires_at"] > time.time()  # future-dated

    def test_har_with_no_sa_cookies_raises(self, state_dir):
        # HAR with only non-SA URLs
        p = Path("/tmp/empty_har.json")
        p.write_text(json.dumps({
            "log": {"version": "1.2", "entries": [
                {"request": {"url": "https://example.com", "cookies": [], "headers": []}}
            ]}
        }), encoding="utf-8")
        with pytest.raises(ValueError, match="No Seeking Alpha cookies"):
            sa.import_har_cookies(p)

    def test_har_cannot_downgrade_still_valid_long_lived(self, state_dir):
        """Uploading a HAR with a 'stale' slireg must NOT overwrite a fresher
        one in the store. The store's value wins for the whole 30-day window
        (or until the user explicitly clears the store).
        """
        # Step 1: full HAR with slireg valid for 30d
        future = time.time() + 30 * 24 * 3600
        har_full = _make_har([
            {"name": "slireg", "value": "FRESH_VALUE", "expires": future},
            {"name": "sa-user-id-v3", "value": "FRESH_SA_V3", "expires": future},
        ])
        sa.import_har_cookies(har_full)

        store = sa._read_store()
        slireg = next(c for c in store["cookies_parsed"] if c["name"] == "slireg")
        assert slireg["value"] == "FRESH_VALUE"

        # Step 2: upload a HAR from a DIFFERENT browser/account with a
        # different slireg. The store's still-valid slireg must win.
        har_other_account = _make_har([
            {"name": "slireg", "value": "OTHER_ACCOUNT_SLIREG", "expires": -1},
            {"name": "_ga", "value": "GA1.1.different"},
        ])
        result = sa.import_har_cookies(har_other_account)
        meta = result.get("merge_metadata", {})

        # slireg must still be the FRESH one, not the other-account one
        store = sa._read_store()
        slireg_after = next(c for c in store["cookies_parsed"] if c["name"] == "slireg")
        assert slireg_after["value"] == "FRESH_VALUE", (
            "Store slireg was overwritten by a HAR with worse/no expiry!"
        )

        # _ga was free to update (SHORT)
        ga = next(c for c in store["cookies_parsed"] if c["name"] == "_ga")
        assert ga["value"] == "GA1.1.different"

        # Meta should report the downgrade protection
        assert "slireg" in meta.get("downgrade_protected", []), (
            f"Expected slireg in downgrade_protected, got {meta}"
        )

    def test_har_cannot_replace_long_lived_with_backfilled_expiry(self, state_dir):
        """Even if the HAR shows an expired slireg, the store's backfilled
        30d default keeps it alive. To force replacement, the user must
        clear the store explicitly.
        """
        # Step 1: import a slireg whose expires is in the past
        #         (simulating an old session — the smart merge backfills
        #         expires_at to now+30d because slireg is LONG-lived)
        ancient = time.time() - 24 * 3600
        har_old = _make_har([
            {"name": "slireg", "value": "OLD_SLIREG", "expires": ancient},
        ])
        sa.import_har_cookies(har_old)

        store = sa._read_store()
        slireg = next(c for c in store["cookies_parsed"] if c["name"] == "slireg")
        # expires_at was backfilled with the LONG default = now + 30d
        assert slireg["expires_at"] > time.time() + 29 * 24 * 3600

        # Step 2: upload a HAR with a different slireg. Store's
        # backfilled 30d expiry still wins — the HAR is rejected
        # to avoid clobbering a still-valid store value.
        har_new = _make_har([
            {"name": "slireg", "value": "NEW_SLIREG", "expires": ancient},
        ])
        sa.import_har_cookies(har_new)
        store = sa._read_store()
        slireg_after = next(c for c in store["cookies_parsed"] if c["name"] == "slireg")
        # Store wins
        assert slireg_after["value"] == "OLD_SLIREG"


# ─────────────────────────────────────────────────────────────────────
# _compute_cookie_freshness
# ─────────────────────────────────────────────────────────────────────


class TestCookieFreshness:
    def test_not_configured_when_empty(self, state_dir):
        freshness = sa._compute_cookie_freshness({})
        assert freshness["status"] == "not_configured"
        assert freshness["long_lived_present"] == []
        # 16 LONG_LIVED_AUTH_COOKIES = slireg + 5 sa-user-id* + 2 remember + 2 gk + 3 user + sailthru
        assert len(freshness["long_lived_missing"]) > 0

    def test_fresh_when_all_long_lived_present(self, state_dir):
        # Build a payload with all long-lived cookies + a recent updated_at
        cookies = [{"name": n, "value": "x", "domain": ".sa.com", "path": "/",
                    "expires_at": time.time() + 30 * 24 * 3600, "longevity": "LONG"}
                   for n in sa.LONG_LIVED_AUTH_COOKIES]
        cookies.append({"name": "_ga", "value": "v", "domain": ".sa.com", "path": "/",
                        "expires_at": time.time() + 24 * 3600, "longevity": "SHORT"})
        payload = {
            "cookies_parsed": cookies,
            "cookie_expires": {c["name"]: c["expires_at"] for c in cookies},
            "updated_at": "2026-06-11T18:00:00+00:00",
        }
        freshness = sa._compute_cookie_freshness(payload)
        assert freshness["status"] == "fresh"
        assert freshness["long_lived_missing"] == []

    def test_missing_long_lived_auth_triggers_warning(self, state_dir):
        # Only 1 of 16 long-lived cookies present
        cookies = [{"name": "slireg", "value": "x", "domain": ".sa.com", "path": "/",
                    "expires_at": time.time() + 30 * 24 * 3600, "longevity": "LONG"}]
        payload = {
            "cookies_parsed": cookies,
            "cookie_expires": {"slireg": time.time() + 30 * 24 * 3600},
            "updated_at": "2026-06-11T18:00:00+00:00",
        }
        freshness = sa._compute_cookie_freshness(payload)
        assert freshness["status"] == "missing_long_lived_auth"
        assert "slireg" in freshness["long_lived_present"]
        assert len(freshness["long_lived_missing"]) >= 3

    def test_expiring_soon_when_within_24h(self, state_dir):
        # All long-lived present, but one expires in 6h
        soon = time.time() + 6 * 3600
        cookies = [{"name": n, "value": "x", "domain": ".sa.com", "path": "/",
                    "expires_at": soon, "longevity": "LONG"}
                   for n in sa.LONG_LIVED_AUTH_COOKIES]
        payload = {
            "cookies_parsed": cookies,
            "cookie_expires": {n: soon for n in sa.LONG_LIVED_AUTH_COOKIES},
            "updated_at": "2026-06-11T18:00:00+00:00",
        }
        freshness = sa._compute_cookie_freshness(payload)
        assert freshness["status"] == "expiring_soon"
        assert freshness["earliest_long_lived_expiry"] == soon

    def test_stale_over_72h(self, state_dir):
        # All long-lived present with long expiry, but updated > 72h ago
        cookies = [{"name": n, "value": "x", "domain": ".sa.com", "path": "/",
                    "expires_at": time.time() + 30 * 24 * 3600, "longevity": "LONG"}
                   for n in sa.LONG_LIVED_AUTH_COOKIES]
        payload = {
            "cookies_parsed": cookies,
            "cookie_expires": {n: time.time() + 30 * 24 * 3600
                               for n in sa.LONG_LIVED_AUTH_COOKIES},
            "updated_at": "2026-06-08T10:00:00+00:00",  # 4 days ago
        }
        freshness = sa._compute_cookie_freshness(payload)
        assert freshness["status"] == "stale_over_72h"
        assert freshness["store_age_hours"] > 72


# ─────────────────────────────────────────────────────────────────────
# get_access_status exposes freshness
# ─────────────────────────────────────────────────────────────────────


class TestAccessStatusIncludesFreshness:
    def test_status_returns_freshness_dict(self, state_dir):
        result = sa.get_access_status()
        assert "freshness" in result
        assert result["freshness"]["status"] == "not_configured"
        assert "merge_metadata" in result
        assert result["merge_metadata"] == {}
