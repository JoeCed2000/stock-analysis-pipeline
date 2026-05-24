"""
TDD tests for /api/version endpoint.

The endpoint must return git version/commit metadata.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


class TestVersionEndpoint:
    """Tests for GET /api/version."""

    def test_version_returns_200_with_required_fields(self):
        """Happy path: endpoint returns 200 with version, commit, service, timestamp."""
        response = client.get("/api/version")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "service" in data
        assert data["service"] == "stock-analysis-pipeline"
        assert "version" in data
        assert "commit" in data
        assert "timestamp" in data

    def test_version_fields_are_non_empty_strings(self):
        """Happy path: version and commit should be non-empty strings."""
        response = client.get("/api/version")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data["version"], str), f"version is {type(data['version'])}"
        assert len(data["version"]) > 0, "version is empty"
        assert isinstance(data["commit"], str), f"commit is {type(data['commit'])}"
        assert len(data["commit"]) > 0, "commit is empty"

    def test_version_timestamp_is_iso8601(self):
        """Happy edge: timestamp should be ISO 8601 UTC."""
        response = client.get("/api/version")
        assert response.status_code == 200
        data = response.json()

        ts = data["timestamp"]
        # ISO 8601: ends with Z or +00:00
        assert ts.endswith("Z") or "+" in ts, f"Not ISO 8601: {ts}"
