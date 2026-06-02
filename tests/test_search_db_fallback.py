import json

from backend import search_db


def test_read_recent_sqlite_falls_back_to_jsonl_when_sqlite_empty(tmp_path, monkeypatch):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    db_path = logs_dir / "searches.db"
    jsonl_path = logs_dir / "searches.jsonl"
    jsonl_path.write_text(
        json.dumps({
            "timestamp": "2026-06-02T07:46:39+00:00",
            "ticker": "AAPL",
            "status": "failed",
            "duration_ms": 0,
            "cache_hit": False,
            "user_agent": "curl",
            "client_ip": "1.2.3.4",
            "error": "Analysis timed out after 1200s",
        }) + "\n" +
        json.dumps({
            "timestamp": "2026-06-02T08:00:00+00:00",
            "ticker": "NVDA",
            "status": "completed",
            "duration_ms": 1234,
            "cache_hit": False,
            "user_agent": "browser",
            "client_ip": "1.2.3.4",
            "error": "",
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(search_db, "DB_PATH", db_path)

    rows = search_db.read_recent_sqlite(limit=10)

    assert [row["ticker"] for row in rows] == ["NVDA", "AAPL"]


def test_get_stats_falls_back_to_jsonl_when_sqlite_empty(tmp_path, monkeypatch):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    db_path = logs_dir / "searches.db"
    jsonl_path = logs_dir / "searches.jsonl"
    jsonl_path.write_text(
        json.dumps({
            "timestamp": "2026-06-02T07:46:39+00:00",
            "ticker": "AAPL",
            "status": "failed",
            "duration_ms": 0,
            "cache_hit": False,
            "user_agent": "curl",
            "client_ip": "1.2.3.4",
            "error": "Analysis timed out after 1200s",
        }) + "\n" +
        json.dumps({
            "timestamp": "2026-06-02T07:50:00+00:00",
            "ticker": "1 VALIDATION ERROR FOR ANALYSISRESULT\nPRICE_NATIVE\n  INPUT SHOULD BE A VALID NUMBER",
            "status": "failed",
            "duration_ms": 0,
            "cache_hit": False,
            "user_agent": "curl",
            "client_ip": "1.2.3.4",
            "error": "bad legacy row",
        }) + "\n" +
        json.dumps({
            "timestamp": "2026-06-02T08:00:00+00:00",
            "ticker": "NVDA",
            "status": "completed",
            "duration_ms": 1200,
            "cache_hit": False,
            "user_agent": "browser",
            "client_ip": "1.2.3.4",
            "error": "",
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(search_db, "DB_PATH", db_path)

    stats = search_db.get_stats()

    assert stats["total"] == 3
    assert stats["success_rate"] == 33.3
    assert stats["avg_duration_ms"] == 1200
    assert stats["top_tickers"] == [{"ticker": "NVDA", "count": 1}, {"ticker": "AAPL", "count": 1}]
    assert any(error["ticker"] == "AAPL" for error in stats["recent_errors"])
    assert all("VALIDATION ERROR" not in item["ticker"] for item in stats["top_tickers"])
