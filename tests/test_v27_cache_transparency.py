"""Tests for overview_cache_info and overview_cache_flush (T8 — cache transparency).

Verifies: cache info metadata, flush deletes files, non-existent ticker handling.
"""

import json
import time
import pytest
from pathlib import Path
from datetime import datetime, timezone

from backend.company_overview import (
    overview_cache_info,
    overview_cache_flush,
    _overview_cache_set,
    _overview_cache_path,
    OVERVIEW_CACHE_TTL,
    OVERVIEW_CACHE_VERSION,
    CACHE_DIR,
)


class TestCacheInfo:
    """GET /api/cache/overview/{ticker} — cache metadata."""

    def test_no_cache_returns_not_cached(self):
        """Tickticker with no cache file returns cached=False."""
        result = overview_cache_info("ZZZXX", "en")
        assert result["cached"] is False
        assert result["ticker"] == "ZZZXX"
        assert result["language"] == "en"
        assert result["ttl_days"] == 7

    def test_cached_overview_returns_metadata(self):
        """Cached overview returns full metadata with age and timestamp."""
        _overview_cache_set("TESTCACHE", "en", {"test": True, "name": "TestCo"})
        result = overview_cache_info("TESTCACHE", "en")

        assert result["cached"] is True
        assert result["ticker"] == "TESTCACHE"
        assert result["language"] == "en"
        assert result["cache_version"] == OVERVIEW_CACHE_VERSION
        assert "cached_at" in result
        assert result["age_seconds"] >= 0
        assert result["age_days"] >= 0
        assert result["ttl_days"] == 7
        assert result["expired"] is False  # just set

        # clean up
        overview_cache_flush("TESTCACHE", "en")

    def test_expired_cache_shows_expired_true(self):
        """Cache older than TTL reports expired=True."""
        path = _overview_cache_path("TESTEXP", "en")
        old_ts = datetime.now(timezone.utc).timestamp() - OVERVIEW_CACHE_TTL - 3600
        entry = {"version": OVERVIEW_CACHE_VERSION, "timestamp": old_ts, "data": {}}
        CACHE_DIR.mkdir(exist_ok=True)
        with open(path, "w") as f:
            json.dump(entry, f)

        result = overview_cache_info("TESTEXP", "en")
        assert result["cached"] is True
        assert result["expired"] is True
        assert result["age_days"] >= 7

        # clean up
        path.unlink(missing_ok=True)


class TestCacheFlush:
    """POST /api/cache/overview/{ticker}/flush — delete cached overview."""

    def setup_method(self):
        """Ensure clean state."""
        overview_cache_flush("TFLUSH", None)

    def test_flush_single_language(self):
        """Flush en only — deletes en, leaves jp."""
        _overview_cache_set("TFLUSH", "en", {"test": "en"})
        _overview_cache_set("TFLUSH", "jp", {"test": "jp"})

        result = overview_cache_flush("TFLUSH", "en")
        assert result["deleted"] == ["en"]
        assert result["not_found"] == []
        assert result["ticker"] == "TFLUSH"

        # en should be gone, jp should remain
        info_en = overview_cache_info("TFLUSH", "en")
        assert info_en["cached"] is False
        info_jp = overview_cache_info("TFLUSH", "jp")
        assert info_jp["cached"] is True

        # clean up jp
        overview_cache_flush("TFLUSH", "jp")

    def test_flush_all_languages(self):
        """Flush without specifying language removes all."""
        _overview_cache_set("TFLUSH", "en", {"test": "en"})
        _overview_cache_set("TFLUSH", "jp", {"test": "jp"})

        result = overview_cache_flush("TFLUSH", None)
        assert "en" in result["deleted"]
        assert "jp" in result["deleted"]

        info_en = overview_cache_info("TFLUSH", "en")
        assert info_en["cached"] is False
        info_jp = overview_cache_info("TFLUSH", "jp")
        assert info_jp["cached"] is False

    def test_flush_nonexistent_ticker(self):
        """Flush non-existent ticker returns empty deleted list."""
        result = overview_cache_flush("NOEXIST", "en")
        assert result["deleted"] == []
        assert result["ticker"] == "NOEXIST"

    def test_flush_nonexistent_language(self):
        """Flush language that doesn't exist for an existing ticker."""
        _overview_cache_set("TFLUSH", "en", {"test": True})
        result = overview_cache_flush("TFLUSH", "jp")  # jp doesn't exist
        assert result["deleted"] == []
        assert "jp" in result["not_found"] or result["not_found"] == []

        # clean up
        overview_cache_flush("TFLUSH", "en")


class TestCacheInfoEdgeCases:
    """Edge cases for cache_info."""

    def test_corrupted_cache_file(self):
        """Corrupted JSON returns cached=False gracefully."""
        path = _overview_cache_path("CORRUPT", "en")
        CACHE_DIR.mkdir(exist_ok=True)
        path.write_text("{invalid json")

        result = overview_cache_info("CORRUPT", "en")
        # Should not raise — returns cached=False or error field
        assert "error" in result or result.get("cached") is False

        path.unlink(missing_ok=True)

    def test_lowercase_ticker(self):
        """Lowercase ticker is uppercased."""
        _overview_cache_set("LOWTEST", "en", {"x": 1})
        result = overview_cache_info("lowtest", "en")
        assert result["ticker"] == "LOWTEST"

        overview_cache_flush("LOWTEST", "en")
