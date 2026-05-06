def test_translate_text_uses_local_codex_provider(monkeypatch):
    from backend import codex_provider
    from backend import translator

    calls = []

    def fake_codex_chat(prompt: str, system: str = "", max_tokens: int = 1000):
        calls.append({"prompt": prompt, "system": system, "max_tokens": max_tokens})
        return "売上高は改善しました。"

    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setattr(codex_provider, "_codex_chat", fake_codex_chat)

    translated = translator.translate_text("Revenue improved.", "ja")

    assert translated == "売上高は改善しました。"
    assert len(calls) == 1
    assert "Revenue improved." in calls[0]["prompt"]
    assert "Japanese" in calls[0]["system"]


def test_translate_text_returns_original_when_codex_unavailable(monkeypatch):
    from backend import codex_provider
    from backend import translator

    monkeypatch.setenv("NVIDIA_API_KEY", "must-not-be-used")
    monkeypatch.setattr(codex_provider, "_codex_chat", lambda *args, **kwargs: None)

    assert translator.translate_text("Revenue improved.", "ja") == "Revenue improved."


def test_translate_text_strict_mode_fails_when_codex_unavailable(monkeypatch):
    import pytest

    from backend import codex_provider
    from backend import translator

    monkeypatch.setattr(codex_provider, "_codex_chat", lambda *args, **kwargs: None)

    with pytest.raises(translator.TranslationUnavailableError):
        translator.translate_text("Revenue improved.", "ja", strict=True)
