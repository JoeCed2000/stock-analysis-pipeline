"""Tests for the live chat widget backend."""

import pytest
from fastapi.testclient import TestClient
import backend.main as _bm
from backend.chat_store import initialize as init_chat_store


@pytest.fixture(autouse=True)
def isolate_state(monkeypatch):
    """Ensure clean state for each test."""
    monkeypatch.setattr(_bm, "_API_KEY", "test-key")
    # Initialize chat DB
    init_chat_store()
    yield


@pytest.fixture
def client():
    return TestClient(_bm.app)


def test_create_session(client):
    res = client.post("/api/chat/session", json={
        "visitor_name": "Nami",
        "language": "ja",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"].startswith("sess_")
    assert data["language"] == "ja"
    assert data["visitor_name"] == "Nami"


def test_get_history_empty(client):
    # Create session first
    sess = client.post("/api/chat/session", json={"language": "ja"}).json()
    res = client.get(f"/api/chat/history?session_id={sess['session_id']}")
    assert res.status_code == 200
    data = res.json()
    assert data["messages"] == []


def test_send_message_returns_processing(client):
    sess = client.post("/api/chat/session", json={"language": "ja"}).json()
    res = client.post("/api/chat/message", json={
        "session_id": sess["session_id"],
        "message": "テストメッセージ",
        "idempotency_key": "test-key-001",
        "context": {"client_language": "ja"},
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "processing"
    assert data["user_message_id"].startswith("msg_")
    assert data["assistant_message_id"].startswith("msg_")


def test_idempotency_prevents_duplicate(client):
    sess = client.post("/api/chat/session", json={"language": "ja"}).json()
    key = "dup-test-key-001"

    res1 = client.post("/api/chat/message", json={
        "session_id": sess["session_id"],
        "message": "重複テスト",
        "idempotency_key": key,
        "context": {"client_language": "ja"},
    })
    assert res1.status_code == 200
    data1 = res1.json()
    assert "duplicate" not in data1

    res2 = client.post("/api/chat/message", json={
        "session_id": sess["session_id"],
        "message": "重複テスト",
        "idempotency_key": key,
        "context": {"client_language": "ja"},
    })
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2.get("duplicate") is True
    assert data2["user_message_id"] == data1["user_message_id"]


def test_session_not_found(client):
    res = client.post("/api/chat/message", json={
        "session_id": "sess_nonexistent",
        "message": "test",
        "context": {"client_language": "ja"},
    })
    assert res.status_code == 404


def test_history_has_message_after_send(client):
    sess = client.post("/api/chat/session", json={"language": "ja"}).json()
    client.post("/api/chat/message", json={
        "session_id": sess["session_id"],
        "message": "履歴テスト",
        "context": {"client_language": "ja"},
    })
    res = client.get(f"/api/chat/history?session_id={sess['session_id']}")
    assert res.status_code == 200
    data = res.json()
    assert len(data["messages"]) >= 1  # at least user message
    assert data["messages"][0]["role"] == "user"
    assert "履歴" in data["messages"][0]["content"]


def test_debug_context(client):
    sess = client.post("/api/chat/session", json={"language": "ja"}).json()
    res = client.get(f"/api/chat/context?session_id={sess['session_id']}")
    assert res.status_code == 200
    data = res.json()
    assert "language" in data
    assert data["language"] == "ja"


def test_ai_response_is_japanese_by_default(client):
    """Integration test: verify AI responds in Japanese when no ticker."""
    sess = client.post("/api/chat/session", json={"language": "ja"}).json()
    res = client.post("/api/chat/message", json={
        "session_id": sess["session_id"],
        "message": "Hello, can you summarize this stock?",
        "context": {"client_language": "ja"},
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "processing"

    # Wait and check history for Japanese response
    import time
    time.sleep(8)

    hist = client.get(f"/api/chat/history?session_id={sess['session_id']}").json()
    assistant_msgs = [m for m in hist["messages"] if m["role"] == "assistant"]
    if assistant_msgs and assistant_msgs[0]["content"]:
        content = assistant_msgs[0]["content"]
        # Response should be in Japanese, not English
        # Check for Japanese characters or polite phrases
        has_japanese = any(
            marker in content
            for marker in ["です", "ます", "ください", "ありがとう", "申し訳", "ご質問"]
        )
        assert has_japanese, f"Expected Japanese response, got: {content[:200]}"


def test_message_context_stored(client):
    """Verify ticker and URL context are saved with messages."""
    sess = client.post("/api/chat/session", json={"language": "ja"}).json()
    client.post("/api/chat/message", json={
        "session_id": sess["session_id"],
        "message": "NVDAのリスクを教えて",
        "context": {
            "current_url": "https://sa.cedlabusa.net/stocks/NVDA",
            "ticker": "NVDA",
            "pdf_title": "NVDA Analysis",
            "client_language": "ja",
        },
    })
    hist = client.get(f"/api/chat/history?session_id={sess['session_id']}").json()
    user_msgs = [m for m in hist["messages"] if m["role"] == "user"]
    assert len(user_msgs) >= 1
    assert user_msgs[0]["ticker"] == "NVDA"
