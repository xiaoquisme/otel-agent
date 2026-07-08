"""Tests for the new flat-provider config schema."""

from pathlib import Path
from otel_agent.config import Config


def test_load_valid_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
    api_format: openai
""")
    cfg = Config(config_file)
    provider = cfg.get_provider("openai")
    assert provider is not None
    assert provider.base_url == "https://api.openai.com/v1"
    assert provider.api_format == "openai"


def test_multiple_providers(tmp_path):
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
  - name: anthropic
    base_url: https://api.anthropic.com
    api_key: sk-ant
    api_format: anthropic
""")
    cfg = Config(config_file)
    assert len(cfg.providers) == 3
    assert cfg.get_provider("openai").api_format == "openai"
    assert cfg.get_provider("anthropic").api_format == "anthropic"
    assert cfg.get_provider("xiaomi").base_url == "https://api.xiaomi.com/v1"


def test_missing_config_returns_empty():
    cfg = Config(Path("/nonexistent/config.yaml"))
    assert cfg.providers == {}
    assert cfg.get_provider("openai") is None
    assert cfg.routes == []


def test_reload_on_change(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
    api_format: openai
""")
    cfg = Config(config_file)
    assert cfg.get_provider("openai").base_url == "https://api.openai.com/v1"

    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.new.com/v1
    api_key: sk-b
    api_format: openai
""")
    assert cfg.get_provider("openai").base_url == "https://api.new.com/v1"


def test_routes_property(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
    api_format: openai
  - name: anthropic
    base_url: https://api.anthropic.com
    api_key: sk-b
    api_format: anthropic
""")
    cfg = Config(config_file)
    routes = cfg.routes
    assert len(routes) == 2
    names = [r["provider"] for r in routes]
    assert "anthropic" in names
    assert "openai" in names


def test_empty_base_url_rejected(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: ""
    api_key: sk-a
    api_format: openai
""")
    try:
        Config(config_file)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must have a base_url" in str(e)


def test_empty_api_key_rejected(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: ""
    api_format: openai
""")
    try:
        Config(config_file)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must have an api_key" in str(e)


def test_invalid_api_format_rejected(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
    api_format: cohere
""")
    try:
        Config(config_file)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "invalid api_format" in str(e)


def test_default_api_format_is_openai(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
""")
    cfg = Config(config_file)
    assert cfg.get_provider("openai").api_format == "openai"


def test_get_unknown_provider_returns_none(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
    api_format: openai
""")
    cfg = Config(config_file)
    assert cfg.get_provider("nonexistent") is None
