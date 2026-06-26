from pathlib import Path
from otel_agent.config import Config
from otel_agent.rotator import KeyRotator


def test_rotator_cycles_keys(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
      - key: sk-b
        active: true
      - key: sk-c
        active: true
""")
    cfg = Config(config_file)
    rotator = KeyRotator(cfg)

    seen = [rotator.next("api.openai.com") for _ in range(6)]
    assert seen == ["sk-a", "sk-b", "sk-c", "sk-a", "sk-b", "sk-c"]


def test_rotator_skips_inactive(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
      - key: sk-b
        active: false
      - key: sk-c
        active: true
""")
    cfg = Config(config_file)
    rotator = KeyRotator(cfg)

    seen = [rotator.next("api.openai.com") for _ in range(4)]
    assert seen == ["sk-a", "sk-c", "sk-a", "sk-c"]


def test_rotator_picks_up_config_changes(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
""")
    cfg = Config(config_file)
    rotator = KeyRotator(cfg)

    assert rotator.next("api.openai.com") == "sk-a"

    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: false
      - key: sk-b
        active: true
""")
    assert rotator.next("api.openai.com") == "sk-b"


def test_rotator_no_keys_returns_none(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys: []
""")
    cfg = Config(config_file)
    rotator = KeyRotator(cfg)
    assert rotator.next("api.openai.com") is None
