"""Focused regressions for the production security boundary.

Artifact content/allow-list behavior is covered in test_artifact_access_security.py.
This module keeps the authorization invariants small and explicit: spoofable
transport metadata never grants access, private object names are not enumerable,
and public curated routes are not accidentally placed behind the master key.
"""

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
import pytest

import backend.main as main


TEST_KEY = "security-regression-test-key"
PRIVATE_ARTIFACT_PATHS = (
    "/api/analyze/{ticker}/download",
    "/api/sources/{ticker}",
    "/api/traceability/{ticker}",
)
PUBLIC_CURATED_PATHS = (
    "/api/report/{ticker}",
    "/api/report/{ticker}/pdf",
    "/api/dossier/{ticker}/status",
    "/api/dossier/{ticker}/download",
)
SPOOFED_HEADER_SETS = (
    {},
    {"Origin": "https://sa.cedlabusa.net"},
    {"Referer": "https://sa.cedlabusa.net/"},
    {"Host": "sa.cedlabusa.net"},
    {
        "Origin": "https://sa.cedlabusa.net",
        "Referer": "https://sa.cedlabusa.net/",
        "Host": "sa.cedlabusa.net",
        "ngrok-skip-browser-warning": "true",
    },
)


def _route(path: str, method: str = "GET") -> APIRoute:
    return next(
        route
        for route in main.app.routes
        if isinstance(route, APIRoute)
        and route.path == path
        and method in route.methods
    )


def _direct_dependencies(route: APIRoute) -> set[object]:
    return {dependency.call for dependency in route.dependant.dependencies}


@pytest.fixture(autouse=True)
def fail_closed_security_state(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "_API_KEY", TEST_KEY)
    monkeypatch.setattr(main, "_rate_limits", {})
    monkeypatch.setattr(main, "_batch_jobs", {})
    monkeypatch.setattr(main, "BATCH_DIR", tmp_path / "batches")
    main.BATCH_DIR.mkdir()


class TestSecurityBoundaryRegression:
    @pytest.mark.parametrize("route_path", PRIVATE_ARTIFACT_PATHS)
    def test_private_routes_are_wired_to_master_key_dependency(self, route_path):
        assert main._require_auth in _direct_dependencies(_route(route_path))

    @pytest.mark.parametrize("route_path", PUBLIC_CURATED_PATHS)
    def test_public_curated_routes_are_not_wired_to_master_key(self, route_path):
        assert main._require_auth not in _direct_dependencies(_route(route_path))

    @pytest.mark.parametrize("headers", SPOOFED_HEADER_SETS)
    @pytest.mark.parametrize(
        "path",
        (
            "/api/analyze/AAPL/download",
            "/api/sources/AAPL",
            "/api/traceability/AAPL",
        ),
    )
    def test_loopback_and_spoofable_headers_never_authorize(self, headers, path):
        client = TestClient(main.app, client=("127.0.0.1", 51000))

        response = client.get(path, headers=headers)

        assert response.status_code == 403
        assert response.json() == {"detail": "Invalid API key"}

    @pytest.mark.parametrize(
        "path",
        (
            "/api/analyze/AAPL/download",
            "/api/analyze/ZZZZSECURITYMISS/download",
            "/api/sources/AAPL",
            "/api/sources/ZZZZSECURITYMISS",
            "/api/traceability/AAPL",
            "/api/traceability/ZZZZSECURITYMISS",
        ),
    )
    def test_private_object_existence_is_not_enumerable_without_key(self, path):
        client = TestClient(main.app, client=("203.0.113.42", 51000))

        response = client.get(path)

        assert response.status_code == 403
        assert response.json() == {"detail": "Invalid API key"}

    def test_internal_batch_id_is_indistinguishable_from_unknown_id(self):
        main._batch_jobs["internal-known-job"] = {
            "job_id": "internal-known-job",
            "status": "completed",
            "tickers": ["AAPL"],
            "completed": 1,
            "total": 1,
            "results": {},
            "errors": {},
        }
        client = TestClient(main.app, client=("203.0.113.42", 51000))

        known = client.get("/api/batch/internal-known-job/status")
        unknown = client.get("/api/batch/internal-unknown-job/status")

        assert known.status_code == unknown.status_code == 404
        assert known.json() == unknown.json() == {"detail": "Job not found"}
