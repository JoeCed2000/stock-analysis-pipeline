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
        "visitor_id": "visitor-test-123",
        "language": "ja",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"].startswith("sess_")
    assert data["language"] == "ja"
    assert data["visitor_id"] == "visitor-test-123"
    assert "visitor_name" not in data


def test_create_session_generates_visitor_id_when_missing(client):
    res = client.post("/api/chat/session", json={"language": "ja"})
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"].startswith("sess_")
    assert data["visitor_id"]
    assert "visitor_name" not in data


def test_create_session_ignores_spoofed_visitor_name(client):
    """Legacy/spoofed visitor_name payload must not reintroduce identity."""
    import sqlite3
    from backend import chat_store

    res = client.post("/api/chat/session", json={
        "visitor_id": "visitor-spoof-123",
        "visitor_name": "Nami",
        "language": "ja",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["visitor_id"] == "visitor-spoof-123"
    assert "visitor_name" not in data

    conn = sqlite3.connect(chat_store.DB_PATH)
    row = conn.execute("SELECT visitor_name FROM chat_sessions WHERE id=?", (data["session_id"],)).fetchone()
    conn.close()
    assert row[0] == "訪問者"


def test_get_history_empty(client):
    # Create session first
    sess = client.post("/api/chat/session", json={"language": "ja"}).json()
    res = client.get(f"/api/chat/history?session_id={sess['session_id']}")
    assert res.status_code == 200
    data = res.json()
    assert data["messages"] == []


def test_send_message_returns_processing(client):
    import uuid
    sess = client.post("/api/chat/session", json={"language": "ja"}).json()
    res = client.post("/api/chat/message", json={
        "session_id": sess["session_id"],
        "message": "テストメッセージ",
        "idempotency_key": f"test-key-{uuid.uuid4().hex[:8]}",
        "context": {"client_language": "ja"},
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("processing", "completed")
    assert data["user_message_id"].startswith("msg_")
    # assistant_message_id may be empty for duplicate, but should start with msg_ otherwise
    if data["assistant_message_id"]:
        assert data["assistant_message_id"].startswith("msg_")


def test_idempotency_prevents_duplicate(client):
    import uuid
    sess = client.post("/api/chat/session", json={"language": "ja"}).json()
    key = f"dup-{uuid.uuid4().hex[:8]}"

    res1 = client.post("/api/chat/message", json={
        "session_id": sess["session_id"],
        "message": "重複テスト",
        "idempotency_key": key,
        "context": {"client_language": "ja"},
    })
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1.get("duplicate") is not True  # First submission should not be duplicate

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


def test_english_switch_after_explicit_request(client):
    """Verify AI switches to English when explicitly requested."""
    sess = client.post("/api/chat/session", json={"language": "ja"}).json()
    # First, explicitly request English
    client.post("/api/chat/message", json={
        "session_id": sess["session_id"],
        "message": "Please answer in English from now on.",
        "context": {"client_language": "ja"},
    })
    import time; time.sleep(8)
    hist = client.get(f"/api/chat/history?session_id={sess['session_id']}").json()
    assistant_msgs = [m for m in hist["messages"] if m["role"] == "assistant"]
    if assistant_msgs and assistant_msgs[0]["content"]:
        content = assistant_msgs[0]["content"]
        # Response should NOT have Japanese markers (it should be English now)
        has_japanese = any(
            marker in content
            for marker in ["です", "ます", "ください"]
        )
        # It might still contain some Japanese if the AI is acknowledging the switch
        # The key test: it should contain English words confirming the switch
        has_english = any(
            word in content.lower()
            for word in ["english", "sure", "of course", "switch"]
        )
        assert has_english or not has_japanese, \
            f"Expected English after explicit request, got: {content[:200]}"


def test_ticker_absent_prompts_question(client):
    """Verify AI asks for ticker when none is provided."""
    sess = client.post("/api/chat/session", json={"language": "ja"}).json()
    client.post("/api/chat/message", json={
        "session_id": sess["session_id"],
        "message": "この会社のリスクを教えて",
        "context": {"client_language": "ja"},  # no ticker
    })
    import time; time.sleep(8)
    hist = client.get(f"/api/chat/history?session_id={sess['session_id']}").json()
    assistant_msgs = [m for m in hist["messages"] if m["role"] == "assistant"]
    if assistant_msgs and assistant_msgs[0]["content"]:
        content = assistant_msgs[0]["content"]
        # Should ask which ticker or mention that no ticker is provided
        has_question = any(
            marker in content
            for marker in ["銘柄", "ティッカー", "どの", "教えて", "指定"]
        )
        assert has_question, \
            f"Expected AI to ask for ticker when none provided, got: {content[:200]}"


def test_bug_report_asks_details(client):
    """Verify AI asks for URL/browser/steps when bug reported."""
    sess = client.post("/api/chat/session", json={"language": "ja"}).json()
    client.post("/api/chat/message", json={
        "session_id": sess["session_id"],
        "message": "ボタンが動かない",
        "context": {"client_language": "ja", "current_url": "https://sa.cedlabusa.net/stock-analysis/"},
    })
    import time; time.sleep(8)
    hist = client.get(f"/api/chat/history?session_id={sess['session_id']}").json()
    assistant_msgs = [m for m in hist["messages"] if m["role"] == "assistant"]
    if assistant_msgs and assistant_msgs[0]["content"]:
        content = assistant_msgs[0]["content"]
        # Should ask for details: URL, browser, steps, screenshot
        has_bug_prompts = any(
            marker in content
            for marker in ["URL", "ブラウザ", "スクリーンショット", "手順", "ページ", "どの"]
        )
        assert has_bug_prompts, \
            f"Expected AI to ask bug report details, got: {content[:200]}"


def test_max_message_size_rejected(client):
    """Verify messages over 4000 chars are rejected."""
    sess = client.post("/api/chat/session", json={"language": "ja"}).json()
    long_msg = "あ" * 5000
    res = client.post("/api/chat/message", json={
        "session_id": sess["session_id"],
        "message": long_msg,
        "context": {"client_language": "ja"},
    })
    assert res.status_code == 413
    assert "too long" in res.json()["detail"].lower()


# ── Visitor Display Name Hardening Tests ──────────────────────────────────
import json


def test_detect_visitor_label_for_known_linux_device():
    """Known Linux Chrome fingerprint resolves to a neutral visitor label."""
    from backend.chat_context import _detect_visitor_name
    from backend import chat_store
    sid = chat_store.create_session(
        visitor_name="Visitor",
        language="ja",
        metadata={"client_ip": "2a01:cb00::1", "device": "linux-chrome", "user_agent": "..."}
    ).id
    assert _detect_visitor_name(sid) == "訪問者"


def test_detect_visitor_label_for_known_apple_device():
    """Known Apple/Safari fingerprint resolves to a neutral visitor label."""
    from backend.chat_context import _detect_visitor_name
    from backend import chat_store
    sid = chat_store.create_session(
        visitor_name="Visitor",
        language="ja",
        metadata={"client_ip": "86.242.1.1", "device": "apple-mac-safari", "user_agent": "..."}
    ).id
    assert _detect_visitor_name(sid) == "訪問者"


def test_detect_visitor_explicit_display_name_only():
    """Only an explicit display_name metadata field may customize the display label."""
    from backend.chat_context import _detect_visitor_name
    from backend import chat_store
    sid = chat_store.create_session(
        visitor_name="Visitor",
        language="ja",
        metadata={"display_name": "Client A", "device": "android-chrome"}
    ).id
    assert _detect_visitor_name(sid) == "Client A"


def test_detect_visitor_missing_metadata():
    """Session without metadata → neutral default."""
    from backend.chat_context import _detect_visitor_name
    from backend import chat_store
    sid = chat_store.create_session(
        visitor_name="Visitor",
        language="ja",
    ).id
    assert _detect_visitor_name(sid) == "訪問者"


def test_detect_visitor_corrupted_metadata():
    """Session with corrupted metadata_json → neutral default."""
    from backend.chat_context import _detect_visitor_name
    from backend import chat_store
    import sqlite3
    sid = chat_store.create_session(visitor_name="Visitor", language="ja").id
    conn = sqlite3.connect(chat_store.DB_PATH)
    conn.execute("UPDATE chat_sessions SET metadata_json='not-json' WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    assert _detect_visitor_name(sid) == "訪問者"


def test_session_creation_stores_neutral_apple_display_label_without_exposing_it(client):
    """POST /api/chat/session stores a neutral label and keeps fingerprint as audit metadata."""
    import sqlite3
    from backend import chat_store
    res = client.post("/api/chat/session", json={
        "visitor_id": "visitor-apple-123",
        "language": "ja",
    }, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15"
    })
    assert res.status_code == 200
    sid = res.json()["session_id"]
    assert res.json()["visitor_id"] == "visitor-apple-123"
    assert "visitor_name" not in res.json()

    conn = sqlite3.connect(chat_store.DB_PATH)
    row = conn.execute("SELECT visitor_name, metadata_json FROM chat_sessions WHERE id=?", (sid,)).fetchone()
    conn.close()
    assert row[0] == "訪問者"
    meta = json.loads(row[1])
    assert meta["device"] == "apple-mac-safari"
    assert meta["visitor_id"] == "visitor-apple-123"
    assert "client_ip" in meta


def test_session_creation_linux_chrome_fingerprint_display_label(client):
    """POST /api/chat/session with Linux Chrome stores a neutral display label."""
    import sqlite3
    from backend import chat_store
    res = client.post("/api/chat/session", json={
        "visitor_id": "visitor-linux-123",
        "language": "ja",
    }, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0"
    })
    assert res.status_code == 200
    sid = res.json()["session_id"]

    conn = sqlite3.connect(chat_store.DB_PATH)
    row = conn.execute("SELECT visitor_name, metadata_json FROM chat_sessions WHERE id=?", (sid,)).fetchone()
    conn.close()
    assert row[0] == "訪問者"
    meta = json.loads(row[1])
    assert meta["device"] == "linux-chrome"
    assert meta["visitor_id"] == "visitor-linux-123"


def test_context_includes_neutral_visitor_display_name(client):
    """build_chat_context() returns the neutral display label for fingerprints."""
    import asyncio
    from backend import chat_context, chat_store
    sid = chat_store.create_session(
        visitor_name="Visitor",
        language="ja",
        metadata={"client_ip": "2a01:cb00::1", "device": "linux-chrome"}
    ).id

    ctx = asyncio.run(chat_context.build_chat_context(
        session_id=sid,
        user_message="Hello",
        language="ja",
    ))
    assert ctx["visitor_display_name"] == "訪問者"


def test_known_device_labels_are_neutral_and_server_controlled(client):
    """Different fingerprints stay isolated but resolve to neutral display labels."""
    from backend import chat_store
    linux_sid = chat_store.create_session(
        visitor_name="Visitor", language="ja",
        metadata={"client_ip": "2a01:cb00::1", "device": "linux-chrome"}
    ).id
    apple_sid = chat_store.create_session(
        visitor_name="Visitor", language="ja",
        metadata={"client_ip": "86.242.1.1", "device": "apple-mac-safari"}
    ).id

    from backend.chat_context import _detect_visitor_name
    assert _detect_visitor_name(linux_sid) == "訪問者"
    assert _detect_visitor_name(apple_sid) == "訪問者"
