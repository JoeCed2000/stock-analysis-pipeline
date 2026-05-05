"""
Coverage gap tests — TDD for 90%+ backend coverage.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


class TestHealthEndpoint:
    """Health check structure."""

    def test_health_returns_correct_structure(self):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "stock-analysis-pipeline"
        assert "commit" in data


class TestAnalysesList:
    """GET /api/analyses — list completed dossiers."""

    def test_analyses_list_returns_array(self):
        response = client.get("/api/analyses")
        assert response.status_code == 200
        data = response.json()
        assert "analyses" in data
        assert isinstance(data["analyses"], list)


class TestBatchUpload:
    """Batch upload endpoint."""

    def test_batch_upload_no_file_400(self):
        response = client.post("/api/batch/upload")
        assert response.status_code == 400  # FastAPI returns 400 for missing file field (not 422)


class TestSourcesEndpoint:
    """Sources manifest endpoint."""

    def test_sources_404_for_unknown_ticker(self):
        response = client.get("/api/sources/ZZZZUNKNOWN")
        assert response.status_code == 404


class TestTraceabilityEndpoint:
    """Traceability CSV endpoint."""

    def test_traceability_404_for_unknown_ticker(self):
        response = client.get("/api/traceability/ZZZZUNKNOWN")
        assert response.status_code == 404


class TestReportEndpoint:
    """Report endpoints."""

    def test_report_404_for_unknown_ticker(self):
        response = client.get("/api/report/ZZZZUNKNOWN")
        assert response.status_code == 404

    def test_report_pdf_404_for_unknown_ticker(self):
        response = client.get("/api/report/ZZZZUNKNOWN/pdf")
        assert response.status_code == 404


class TestBatchJobNotFound:
    """Batch job 404."""

    def test_batch_status_404(self):
        response = client.get("/api/batch/nonexistent/status")
        assert response.status_code == 404

    def test_batch_download_404(self):
        response = client.get("/api/batch/nonexistent/download")
        assert response.status_code == 404


class TestEURConversion:
    """EUR conversion logic."""

    def test_convert_to_eur_basic(self):
        from backend.sources_collector import convert_to_eur
        with patch("backend.sources_collector._load_yfinance") as mock_yf:
            mock_ticker = MagicMock()
            mock_ticker.info = {"regularMarketPrice": 1.10}
            mock_yf.return_value.Ticker.return_value = mock_ticker
            
            result = convert_to_eur(100.0)
            # 100 USD / 1.10 = 90.91 EUR
            assert result is not None
            assert 90 < result < 92


class TestScoringEdgeCases:
    """Scoring edge cases."""

    def test_score_management_realtime_with_multilingual_tone(self):
        from backend.scorer import _score_management_realtime
        
        # English tone
        result_en = _score_management_realtime({
            "tone": "optimistic",
            "confidence": "high",
            "visibility": "good",
            "concrete_promises": ["p1", "p2", "p3"],
            "defensive_signals": [],
        })
        assert 3 <= result_en <= 5
        
        # French tone (backward compat)
        result_fr = _score_management_realtime({
            "tone": "optimiste",
            "confidence": "élevée",
            "visibility": "bonne",
            "concrete_promises": [],
            "defensive_signals": [],
        })
        assert 3 <= result_fr <= 5

    def test_score_geopolitical_all_sectors(self):
        from backend.scorer import _score_geopolitical
        
        assert _score_geopolitical("Technology", "Semiconductors") == 2
        assert _score_geopolitical("Software", "Services") == 4
        assert _score_geopolitical("Unknown", "Unknown") == 3

    def test_scoring_total_property(self):
        from backend.models import Scoring
        s = Scoring(growth=4, profitability=3, financial_strength=5,
                     moat=2, management=4, valuation_risk=3,
                     geopolitical_risk=4, business_momentum=5)
        assert s.total == 30
        assert "BUY" in s.decision() or "HOLD" in s.decision()
