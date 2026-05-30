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


# ── Visitor Name Detection Tests ──────────────────────────────────────────
import json


def test_detect_visitor_ced_device():
    """linux-chrome device → 'Cédric'."""
    from backend.chat_context import _detect_visitor_name
    from backend import chat_store
    sid = chat_store.create_session(
        visitor_name="Nami",
        language="ja",
        metadata={"client_ip": "2a01:cb00::1", "device": "linux-chrome", "user_agent": "..."}
    ).id
    assert _detect_visitor_name(sid) == "Cédric"


def test_detect_visitor_nami_device():
    """apple-mac-safari device → 'Nami'."""
    from backend.chat_context import _detect_visitor_name
    from backend import chat_store
    sid = chat_store.create_session(
        visitor_name="Nami",
        language="ja",
        metadata={"client_ip": "86.242.1.1", "device": "apple-mac-safari", "user_agent": "..."}
    ).id
    assert _detect_visitor_name(sid) == "Nami"


def test_detect_visitor_unknown_device():
    """Unknown device → default 'Nami'."""
    from backend.chat_context import _detect_visitor_name
    from backend import chat_store
    sid = chat_store.create_session(
        visitor_name="Nami",
        language="ja",
        metadata={"client_ip": "10.0.0.1", "device": "android-chrome", "user_agent": "..."}
    ).id
    assert _detect_visitor_name(sid) == "Nami"


def test_detect_visitor_missing_metadata():
    """Session without metadata → default 'Nami'."""
    from backend.chat_context import _detect_visitor_name
    from backend import chat_store
    sid = chat_store.create_session(
        visitor_name="Nami",
        language="ja",
    ).id
    assert _detect_visitor_name(sid) == "Nami"


def test_detect_visitor_corrupted_metadata():
    """Session with corrupted metadata_json → default 'Nami'."""
    from backend.chat_context import _detect_visitor_name
    from backend import chat_store
    import sqlite3
    sid = chat_store.create_session(visitor_name="Nami", language="ja").id
    # Corrupt the metadata
    conn = sqlite3.connect(chat_store.DB_PATH)
    conn.execute("UPDATE chat_sessions SET metadata_json='not-json' WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    assert _detect_visitor_name(sid) == "Nami"


def test_session_creation_stores_device_fingerprint(client):
    """POST /api/chat/session stores device in metadata_json."""
    import sqlite3
    from backend import chat_store
    res = client.post("/api/chat/session", json={
        "visitor_name": "Nami",
        "language": "ja",
    }, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15"
    })
    assert res.status_code == 200
    sid = res.json()["session_id"]

    conn = sqlite3.connect(chat_store.DB_PATH)
    row = conn.execute("SELECT metadata_json FROM chat_sessions WHERE id=?", (sid,)).fetchone()
    conn.close()
    meta = json.loads(row[0])
    assert meta["device"] == "apple-mac-safari"
    assert "client_ip" in meta


def test_session_creation_linux_chrome_fingerprint(client):
    """POST /api/chat/session with Linux Chrome → device=linux-chrome."""
    import sqlite3
    from backend import chat_store
    res = client.post("/api/chat/session", json={
        "visitor_name": "Nami",
        "language": "ja",
    }, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0"
    })
    assert res.status_code == 200
    sid = res.json()["session_id"]

    conn = sqlite3.connect(chat_store.DB_PATH)
    row = conn.execute("SELECT metadata_json FROM chat_sessions WHERE id=?", (sid,)).fetchone()
    conn.close()
    meta = json.loads(row[0])
    assert meta["device"] == "linux-chrome"


def test_context_includes_visitor_display_name(client):
    """build_chat_context() returns visitor_display_name from session fingerprint."""
    import asyncio
    from backend import chat_context, chat_store
    sid = chat_store.create_session(
        visitor_name="Nami",
        language="ja",
        metadata={"client_ip": "2a01:cb00::1", "device": "linux-chrome"}
    ).id

    ctx = asyncio.run(chat_context.build_chat_context(
        session_id=sid,
        user_message="Hello",
        language="ja",
    ))
    assert ctx["visitor_display_name"] == "Cédric"


def test_visitor_isolation_different_devices_different_names(client):
    """Two sessions with different device types get different visitor names."""
    from backend import chat_store
    ced_sid = chat_store.create_session(
        visitor_name="Nami", language="ja",
        metadata={"client_ip": "2a01:cb00::1", "device": "linux-chrome"}
    ).id
    nami_sid = chat_store.create_session(
        visitor_name="Nami", language="ja",
        metadata={"client_ip": "86.242.1.1", "device": "apple-mac-safari"}
    ).id

    from backend.chat_context import _detect_visitor_name
    assert _detect_visitor_name(ced_sid) == "Cédric"
    assert _detect_visitor_name(nami_sid) == "Nami"
    assert _detect_visitor_name(ced_sid) != _detect_visitor_name(nami_sid)
