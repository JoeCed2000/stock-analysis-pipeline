import inspect

from backend import codex_provider


def test_codex_provider_does_not_use_insecure_mktemp():
    source = inspect.getsource(codex_provider._codex_chat)

    assert "mktemp" not in source


def test_codex_provider_defaults_to_spark_medium(monkeypatch, tmp_path):
    calls = []

    def fake_exists(path):
        return True

    def fake_run(args, **kwargs):
        calls.append(args)
        output_path = args[args.index("-o") + 1]
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("ok")

        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return Proc()

    monkeypatch.delenv("SA_CODEX_MODEL", raising=False)
    monkeypatch.delenv("SA_CODEX_DEFAULT_EFFORT", raising=False)
    monkeypatch.setattr(codex_provider.os.path, "exists", fake_exists)
    monkeypatch.setattr(codex_provider.subprocess, "run", fake_run)
    monkeypatch.setattr(codex_provider, "_codex_unavailable_until", 0.0, raising=False)

    result = codex_provider._codex_chat("prompt", system="system")

    assert result == "ok"
    args = calls[0]
    assert args[args.index("-m") + 1] == "gpt-5.3-codex-spark"
    # Default effort is deliberately medium (SA_CODEX_DEFAULT_EFFORT fallback)
    assert "model_reasoning_effort=medium" in args


def test_codex_quota_failure_opens_circuit_without_retries(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)

        class Proc:
            returncode = 1
            stdout = (
                '{"type":"error","message":"You have hit your usage limit for '
                'GPT-5.3-Codex-Spark. Try again later."}'
            )
            stderr = ""

        return Proc()

    monkeypatch.setattr(codex_provider.os.path, "exists", lambda path: True)
    monkeypatch.setattr(codex_provider.subprocess, "run", fake_run)
    monkeypatch.setattr(codex_provider.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(codex_provider, "_codex_unavailable_until", 0.0, raising=False)

    assert codex_provider._codex_chat("prompt") is None
    assert len(calls) == 1

    assert codex_provider._codex_chat("second prompt") is None
    assert len(calls) == 1
