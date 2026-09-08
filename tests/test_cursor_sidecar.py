"""Tests for Cursor CLI model listing."""

from otel_agent.config import Provider
from otel_agent.cursor_sidecar import parse_agent_list_models


SAMPLE_LIST = """Available models

auto - Auto (default)
gpt-5.3-codex-low - Codex 5.3 Low
composer-2.5 - Composer 2.5
cursor-grok-4.6-high-fast - Cursor Grok 4.6 Fast
claude-opus-5-thinking-high - Claude Opus 5 1M Thinking
"""


def test_parse_agent_list_models_extracts_cli_ids():
    ids = parse_agent_list_models(SAMPLE_LIST)
    assert ids == [
        "auto",
        "gpt-5.3-codex-low",
        "composer-2.5",
        "cursor-grok-4.6-high-fast",
        "claude-opus-5-thinking-high",
    ]
    assert "grok" not in ids
    assert "composer-1.5" not in ids


def test_fetch_loopback_cursor_models_uses_agent_cli(monkeypatch):
    import asyncio

    from otel_agent.models import fetch_provider_models

    provider = Provider(
        name="cursor",
        base_url="http://127.0.0.1:4646/v1",
        api_key="crsr_test",
        api_format="openai",
    )
    called = {"http": False}

    class FakeClient:
        async def get(self, *args, **kwargs):
            called["http"] = True
            raise AssertionError("sidecar /v1/models must not be used for loopback cursor")

    monkeypatch.setattr(
        "otel_agent.cursor_sidecar.list_cursor_cli_models",
        lambda api_key="": ["auto", "composer-2.5", "cursor-grok-4.6-high-fast"],
    )
    models = asyncio.run(fetch_provider_models(FakeClient(), provider))
    assert called["http"] is False
    assert [m["id"] for m in models] == ["auto", "composer-2.5", "cursor-grok-4.6-high-fast"]
    assert all(m["owned_by"] == "cursor" for m in models)


def test_cursor_cli_model_for_sidecar_always_passthrough_prefix():
    from otel_agent.cursor_sidecar import cursor_cli_model_for_sidecar

    assert cursor_cli_model_for_sidecar("auto") == "auto"
    assert cursor_cli_model_for_sidecar("gpt-5.3-codex") == "cursor-gpt-5.3-codex"
    assert cursor_cli_model_for_sidecar("composer-2.5") == "cursor-composer-2.5"
    assert cursor_cli_model_for_sidecar("cursor-grok-4.6-high-fast") == "cursor-grok-4.6-high-fast"
