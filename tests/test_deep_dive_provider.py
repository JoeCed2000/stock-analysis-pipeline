"""Deep-dive LLM provider routing — SA_DEEP_DIVE_PROVIDER switch.

Codex Spark ran out of tokens; DeepSeek v4 Pro becomes the primary provider
when SA_DEEP_DIVE_PROVIDER=deepseek, with Codex kept as automatic fallback.
"""
import backend.earnings_deep_dive.generator as gen


def test_default_routing_is_codex_first(monkeypatch):
    monkeypatch.delenv("SA_DEEP_DIVE_PROVIDER", raising=False)
    calls = []
    monkeypatch.setattr(gen, "codex_chat", lambda *a, **k: calls.append("codex") or "codex-out")
    out = gen._llm_chat("prompt", system="sys")
    assert out == "codex-out"
    assert calls == ["codex"]


def test_deepseek_primary_when_env_set(monkeypatch):
    monkeypatch.setenv("SA_DEEP_DIVE_PROVIDER", "deepseek")
    monkeypatch.setattr(gen, "_deepseek_primary_disabled_until", 0.0)
    monkeypatch.setattr(gen, "codex_chat",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("codex must not be called")))
    import backend.kimi_provider as kimi
    monkeypatch.setattr(kimi, "_deepseek_chat", lambda prompt, system, max_tokens: "deepseek-out")
    assert gen._llm_chat("prompt", system="sys") == "deepseek-out"


def test_deepseek_failure_falls_back_to_codex(monkeypatch):
    monkeypatch.setenv("SA_DEEP_DIVE_PROVIDER", "deepseek")
    monkeypatch.setattr(gen, "_deepseek_primary_disabled_until", 0.0)
    import backend.kimi_provider as kimi
    monkeypatch.setattr(kimi, "_deepseek_chat", lambda prompt, system, max_tokens: None)
    monkeypatch.setattr(gen, "codex_chat", lambda *a, **k: "codex-out")
    assert gen._llm_chat("prompt", system="sys") == "codex-out"


def test_deepseek_failure_opens_short_circuit_for_following_sections(monkeypatch):
    monkeypatch.setenv("SA_DEEP_DIVE_PROVIDER", "deepseek")
    monkeypatch.setattr(gen, "_deepseek_primary_disabled_until", 0.0)
    import backend.kimi_provider as kimi
    calls = []
    monkeypatch.setattr(
        kimi,
        "_deepseek_chat",
        lambda prompt, system, max_tokens: calls.append("deepseek") or None,
    )
    monkeypatch.setattr(gen, "codex_chat", lambda *a, **k: "codex-out")

    assert gen._llm_chat("first", system="sys") == "codex-out"
    assert gen._llm_chat("second", system="sys") == "codex-out"
    assert calls == ["deepseek"]


def test_generation_provider_meta_labels(monkeypatch):
    monkeypatch.setenv("SA_DEEP_DIVE_PROVIDER", "deepseek")
    provider, model, effort = gen._generation_provider()
    assert provider == "deepseek"
    assert model == "deepseek-v4-pro"
    assert effort == "medium"

    monkeypatch.delenv("SA_DEEP_DIVE_PROVIDER", raising=False)
    provider, model, effort = gen._generation_provider()
    assert provider == "codex_cli"
    assert model == "gpt-5.3-codex-spark"
