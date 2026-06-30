from pathlib import Path
from otel_agent.config import Config
from otel_agent.rotator import KeyRotator


def test_rotator_returns_active_provider_key(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-a
      active: true
  anthropic:
    - name: deesseek
      base_url: https://api.anthropic.com
      api_key: sk-ant
      active: true
""")
    cfg = Config(config_file)
    rotator = KeyRotator(cfg)

    assert rotator.next_by_api_key("openai") == "sk-a"
    assert rotator.next_by_api_key("anthropic") == "sk-ant"


def test_rotator_reloads_config_changes(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-a
      active: true
""")
    cfg = Config(config_file)
    rotator = KeyRotator(cfg)

    assert rotator.next_by_api_key("openai") == "sk-a"

    config_file.write_text("""
providers:
  openai:
    - name: deesseek
      base_url: https://api.deesseek.com/v1
      api_key: sk-b
      active: true
""")
    assert rotator.next_by_api_key("openai") == "sk-b"


def test_rotator_no_active_provider_returns_none(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-a
      active: true
""")
    cfg = Config(config_file)
    rotator = KeyRotator(cfg)

    assert rotator.next_by_api_key("nonexistent") is None
