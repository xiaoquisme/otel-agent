import tempfile
from pathlib import Path
from otel_agent.config import Config


def test_load_valid_config(tmp_path):
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
""")
    cfg = Config(config_file)
    provider = cfg.get_provider("openai.com")
    assert provider is not None
    assert provider.base_url == "https://api.openai.com/v1"


def test_active_keys_only(tmp_path):
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
    keys = cfg.get_active_keys("openai.com")
    assert keys == ["sk-a", "sk-c"]


def test_host_matching(tmp_path):
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
    assert cfg.get_provider("api.openai.com") is not None
    assert cfg.get_provider("api.anthropic.com") is None


def test_all_keys_inactive(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: false
""")
    cfg = Config(config_file)
    keys = cfg.get_active_keys("openai.com")
    assert keys == []


def test_missing_config_returns_empty():
    cfg = Config(Path("/nonexistent/config.yaml"))
    assert cfg.get_provider("openai.com") is None
    assert cfg.get_active_keys("openai.com") == []


def test_reload_on_change(tmp_path):
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
    assert cfg.get_active_keys("openai.com") == ["sk-a"]

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
    assert cfg.get_active_keys("openai.com") == ["sk-b"]
