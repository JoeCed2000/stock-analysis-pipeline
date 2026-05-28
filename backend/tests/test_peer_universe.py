"""
Tests for V2.5 Peer Universe Configuration.

Covers all 6 acceptance criteria from SA-V25-T1:
  1. test_valid_peers        — NVDA → 5 AI semi peers, AAPL → mega_cap_consumer_tech
  2. test_unknown_ticker     — unknown ticker returns status "unavailable"
  3. test_duplicates_rejected — duplicate tickers in peers list rejected
  4. test_self_ref_rejected  — ticker referencing itself rejected
  5. test_empty_peers        — group with empty peers list rejected
  6. test_missing_group_id   — group without group_id rejected
"""

import pytest
from peer_universe import get_peers, reload, _validate_and_cache


# ═══════════════════════════════════════════════════════════════
#  1. Valid Peers
# ═══════════════════════════════════════════════════════════════


class TestValidPeers:
    def test_nvda_returns_5_ai_semiconductor_peers(self):
        """NVDA → status=available, group_id=ai_semiconductor, 5 peers."""
        result = get_peers("NVDA")

        assert result["status"] == "available"
        assert result["source"] == "curated"
        assert "timestamp" in result
        assert result["ticker"] == "NVDA"
        assert result["group_id"] == "ai_semiconductor"
        assert result["group_label"] == "AI Semiconductor"
        assert len(result["peers"]) == 5
        assert "AMD" in result["peers"]
        assert "AVGO" in result["peers"]
        assert "TSM" in result["peers"]
        assert "ASML" in result["peers"]
        assert "ARM" in result["peers"]

    def test_aapl_returns_mega_cap_consumer_tech(self):
        """AAPL → group_id=mega_cap_consumer_tech, 4 peers."""
        result = get_peers("AAPL")

        assert result["status"] == "available"
        assert result["ticker"] == "AAPL"
        assert result["group_id"] == "mega_cap_consumer_tech"
        assert result["group_label"] == "Mega-Cap Consumer Tech"
        assert len(result["peers"]) == 4
        assert "MSFT" in result["peers"]
        assert "GOOGL" in result["peers"]
        assert "AMZN" in result["peers"]
        assert "META" in result["peers"]

    def test_case_insensitive_lookup(self):
        """Lowercase input 'aapl' resolves correctly."""
        result = get_peers("aapl")
        assert result["status"] == "available"
        assert result["ticker"] == "AAPL"

    def test_tsla_returns_global_automotive_peers(self):
        """TSLA → group_id=global_automotive, 5 peers including TM, BYDDF."""
        result = get_peers("TSLA")

        assert result["status"] == "available"
        assert result["group_id"] == "global_automotive"
        assert len(result["peers"]) == 5
        assert "RIVN" in result["peers"]
        assert "GM" in result["peers"]
        assert "F" in result["peers"]
        assert "TM" in result["peers"]
        assert "BYDDF" in result["peers"]

    def test_goog_derives_from_mega_cap_group(self):
        """GOOG is a configured peer of AAPL and should derive an available group."""
        result = get_peers("GOOG")

        assert result["status"] == "available"
        assert result["ticker"] == "GOOG"
        assert result["group_id"] == "mega_cap_consumer_tech"
        assert result["group_label"] == "Mega-Cap Consumer Tech"
        assert result.get("derived_from_root") == "AAPL"

        # For derived members, peers include the root ticker + sibling peers.
        assert "AAPL" in result["peers"]
        assert "MSFT" in result["peers"]
        assert "AMZN" in result["peers"]
        assert "META" in result["peers"]
        assert "GOOG" not in result["peers"]
        assert len(result["peers"]) == 4


# ═══════════════════════════════════════════════════════════════
#  2. Unknown Ticker
# ═══════════════════════════════════════════════════════════════


def test_unknown_ticker():
    """Unknown ticker returns status='unavailable'."""
    result = get_peers("ZZZZZ")
    assert result["status"] == "unavailable"
    assert result["source"] == "curated"
    assert result["ticker"] == "ZZZZZ"
    assert "timestamp" in result
    # No group_id, group_label, or peers for unavailable tickers
    assert "group_id" not in result
    assert "peers" not in result


# ═══════════════════════════════════════════════════════════════
#  3. Duplicates Rejected
# ═══════════════════════════════════════════════════════════════


def test_duplicates_rejected():
    """Duplicate tickers in peers list → validation error."""
    bad_config = {
        "_meta": {"version": "1.0"},
        "test": {
            "ticker": "TEST",
            "group_id": "duplicate_group",
            "group_label": "Duplicate Group",
            "peers": ["AMD", "AMD", "INTC"],
        },
    }
    _validate_and_cache(bad_config)
    result = get_peers("TEST")
    assert result["status"] == "error"
    assert any("duplicate" in e.lower() for e in result.get("errors", []))

    # Clean up — reload real config
    reload()


# ═══════════════════════════════════════════════════════════════
#  4. Self-Reference Rejected
# ═══════════════════════════════════════════════════════════════


def test_self_ref_rejected():
    """Ticker referencing itself in peers → validation error."""
    bad_config = {
        "_meta": {"version": "1.0"},
        "self": {
            "ticker": "SELF",
            "group_id": "self_group",
            "group_label": "Self Group",
            "peers": ["SELF", "OTHER"],
        },
    }
    _validate_and_cache(bad_config)
    result = get_peers("SELF")
    assert result["status"] == "error"
    assert any(
        "references itself" in e for e in result.get("errors", [])
    )

    # Clean up
    reload()


# ═══════════════════════════════════════════════════════════════
#  5. Empty Peers
# ═══════════════════════════════════════════════════════════════


def test_empty_peers():
    """Group with empty peers list → validation error."""
    bad_config = {
        "_meta": {"version": "1.0"},
        "empty": {
            "ticker": "EMPTY",
            "group_id": "empty_group",
            "group_label": "Empty Group",
            "peers": [],
        },
    }
    _validate_and_cache(bad_config)
    result = get_peers("EMPTY")
    assert result["status"] == "error"
    assert any(
        "must be a non-empty list" in e for e in result.get("errors", [])
    )

    # Clean up
    reload()


# ═══════════════════════════════════════════════════════════════
#  6. Missing group_id
# ═══════════════════════════════════════════════════════════════


def test_missing_group_id():
    """Group without group_id → validation error."""
    bad_config = {
        "_meta": {"version": "1.0"},
        "no_group": {
            "ticker": "NOGROUP",
            "group_label": "No Group",
            "peers": ["AMD", "INTC"],
        },
    }
    _validate_and_cache(bad_config)
    result = get_peers("NOGROUP")
    assert result["status"] == "error"
    assert any(
        "missing group_id" in e for e in result.get("errors", [])
    )

    # Clean up
    reload()
