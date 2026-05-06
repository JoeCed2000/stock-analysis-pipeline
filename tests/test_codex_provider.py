import inspect

from backend import codex_provider


def test_codex_provider_does_not_use_insecure_mktemp():
    source = inspect.getsource(codex_provider._codex_chat)

    assert "mktemp" not in source
