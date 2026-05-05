from backend import rapidapi_sa


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


def test_search_sa_transcripts_uses_rapidapi_headers_and_normalizes(monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return FakeResponse(
            {
                "data": [
                    {
                        "id": 12345,
                        "title": "NVIDIA Corporation Q1 2026 Earnings Call Transcript",
                        "publishOn": "2026-02-20T21:30:00Z",
                        "quarter": "2026Q1",
                    }
                ]
            }
        )

    monkeypatch.setenv("RAPIDAPI_KEY", "test-key")
    monkeypatch.setenv("RAPIDAPI_SEEKING_ALPHA_HOST", "example-seeking-alpha.p.rapidapi.com")
    monkeypatch.setattr(rapidapi_sa.http, "get", fake_get)

    results = rapidapi_sa.search_sa_transcripts("nvda")

    assert results == [
        {
            "id": "12345",
            "title": "NVIDIA Corporation Q1 2026 Earnings Call Transcript",
            "date": "2026-02-20",
            "quarter": "2026Q1",
            "url": "https://seekingalpha.com/article/12345",
        }
    ]
    assert calls[0]["url"] == "https://example-seeking-alpha.p.rapidapi.com/gettranscripts/v2/list"
    assert calls[0]["params"]["symbol"] == "NVDA"
    assert calls[0]["headers"]["X-RapidAPI-Key"] == "test-key"
    assert calls[0]["headers"]["X-RapidAPI-Host"] == "example-seeking-alpha.p.rapidapi.com"


def test_fetch_sa_transcript_normalizes_segmented_content(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse(
            {
                "data": {
                    "id": "abc",
                    "attributes": {
                        "title": "NVIDIA Corporation Q1 2026 Earnings Call Transcript",
                        "publishOn": "2026-02-20T21:30:00Z",
                        "quarter": "2026Q1",
                        "transcript": [
                            {"speaker": "Operator", "content": "Welcome to the call."},
                            {"speakerName": "CEO", "text": "Revenue accelerated."},
                        ],
                    },
                }
            }
        )

    monkeypatch.setenv("RAPIDAPI_KEY", "test-key")
    monkeypatch.setattr(rapidapi_sa.http, "get", fake_get)

    result = rapidapi_sa.fetch_sa_transcript("abc")

    assert result["id"] == "abc"
    assert result["title"] == "NVIDIA Corporation Q1 2026 Earnings Call Transcript"
    assert result["date"] == "2026-02-20"
    assert result["quarter"] == "2026Q1"
    assert "Operator: Welcome to the call." in result["content"]
    assert "CEO: Revenue accelerated." in result["content"]


def test_search_sa_transcripts_skips_when_key_missing(monkeypatch):
    def fail_get(*args, **kwargs):
        raise AssertionError("HTTP should not be called without RAPIDAPI_KEY")

    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    monkeypatch.setattr(rapidapi_sa.http, "get", fail_get)

    assert rapidapi_sa.search_sa_transcripts("MSFT") == []
