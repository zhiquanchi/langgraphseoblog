import pytest

from app.llm import model_catalog


def test_discover_models_retries_three_times_when_empty(monkeypatch) -> None:
    calls = 0

    def empty_response(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr(model_catalog, "_request_models", empty_response)
    monkeypatch.setattr(model_catalog.time, "sleep", lambda _seconds: None)

    with pytest.raises(model_catalog.ModelDiscoveryError, match="连续 3 次"):
        model_catalog.discover_models("openai", "sk-test")

    assert calls == 3


def test_discover_models_returns_normalized_model_options(monkeypatch) -> None:
    monkeypatch.setattr(
        model_catalog,
        "_request_models",
        lambda *_args, **_kwargs: [{"id": "gpt-test", "name": "GPT Test"}],
    )

    assert model_catalog.discover_models("openai", "sk-test") == [
        {"id": "gpt-test", "name": "GPT Test"}
    ]
