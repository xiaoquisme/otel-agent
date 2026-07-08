"""Tests for model-name parsing and provider resolution."""

import pytest
from pathlib import Path
from otel_agent.config import Config
from otel_agent.router import parse_model, resolve_provider


def test_parse_model_simple():
    provider, model = parse_model("openai/gpt-5.4")
    assert provider == "openai"
    assert model == "gpt-5.4"


def test_parse_model_nested():
    provider, model = parse_model("openrouter/openai/gpt-5.4")
    assert provider == "openrouter"
    assert model == "openai/gpt-5.4"


def test_parse_model_three_levels():
    provider, model = parse_model("xiaomi/mimo-v-2.5")
    assert provider == "xiaomi"
    assert model == "mimo-v-2.5"


def test_parse_model_no_slash_raises():
    with pytest.raises(ValueError, match="must include provider prefix"):
        parse_model("gpt-4")


def test_parse_model_empty_prefix_raises():
    with pytest.raises(ValueError, match="must include provider prefix"):
        parse_model("/gpt-4")


def test_parse_model_empty_suffix_raises():
    with pytest.raises(ValueError, match="must include provider prefix"):
        parse_model("openai/")


def test_resolve_provider_found(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
    api_format: openai
""")
    cfg = Config(config_file)
    provider = resolve_provider("openai", cfg)
    assert provider.name == "openai"


def test_resolve_provider_not_found(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
    api_format: openai
""")
    cfg = Config(config_file)
    with pytest.raises(ValueError, match="Unknown provider 'nonexistent'"):
        resolve_provider("nonexistent", cfg)


def test_resolve_provider_lists_available(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
    api_format: openai
  - name: xiaomi
    base_url: https://api.xiaomi.com/v1
    api_key: sk-b
    api_format: openai
""")
    cfg = Config(config_file)
    with pytest.raises(ValueError, match="openai, xiaomi"):
        resolve_provider("unknown", cfg)
