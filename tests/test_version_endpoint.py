"""
TDD tests for /api/version endpoint.

Spec: Endpoint must return a 200 OK response containing
`version`, `commit`, `build_time`, and `python_version`.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


class TestVersionEndpoint:
    """Tests for GET /api/version."""

    def test_version_endpoint_returns_200_with_required_fields(self):
        """
        RED phase — endpoint does not exist yet, so this MUST fail with 404.

        Spec: GET /api/version → 200 OK with JSON:
          - version (str): git tag or describe output
          - commit (str): short git commit hash
          - build_time (str): ISO 8601 UTC timestamp of build
          - python_version (str): Python interpreter version
        """
        response = client.get("/api/version")
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()

        # All four required fields must be present
        required_fields = ["version", "commit", "build_time", "python_version"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_version_fields_are_non_empty_strings(self):
        """Happy path: all required fields must be non-empty strings."""
        response = client.get("/api/version")
        assert response.status_code == 200
        data = response.json()

        for field in ["version", "commit", "build_time", "python_version"]:
            value = data[field]
            assert isinstance(value, str), (
                f"{field} expected str, got {type(value).__name__}"
            )
            assert len(value) > 0, f"{field} is empty"

    def test_version_build_time_is_iso8601(self):
        """Edge case: build_time must be ISO 8601 UTC."""
        response = client.get("/api/version")
        assert response.status_code == 200
        data = response.json()

        ts = data["build_time"]
        # ISO 8601: ends with Z or contains +/-
        assert ts.endswith("Z") or "+" in ts, (
            f"build_time is not ISO 8601: {ts}"
        )
