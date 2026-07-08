"""Tests for KeyRotator with new config schema."""

from otel_agent.config import Config
from otel_agent.rotator import KeyRotator


def test_rotator_returns_provider_key(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
    api_format: openai
  - name: anthropic
    base_url: https://api.anthropic.com
    api_key: sk-ant
    api_format: anthropic
""")
    cfg = Config(config_file)
    rotator = KeyRotator(cfg)

    assert rotator.get_key("openai") == "sk-a"
    assert rotator.get_key("anthropic") == "sk-ant"


def test_rotator_reloads_config_changes(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
    api_format: openai
""")
    cfg = Config(config_file)
    rotator = KeyRotator(cfg)
    assert rotator.get_key("openai") == "sk-a"

    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.new.com/v1
    api_key: sk-b
    api_format: openai
""")
    assert rotator.get_key("openai") == "sk-b"


def test_rotator_unknown_provider_returns_none(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
    api_format: openai
""")
    cfg = Config(config_file)
    rotator = KeyRotator(cfg)
    assert rotator.get_key("nonexistent") is None
