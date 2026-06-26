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


def test_default_provider_explicit(tmp_path):
    """Explicit default_provider in config."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
default_provider: xiaomi

providers:
  xiaomi:
    base_url: https://api.xiaomi.com/v1
    keys:
      - key: sk-a
        active: true
  xiaomi-anthropic:
    base_url: https://api.xiaomi.com/anthropic
    keys:
      - key: sk-b
        active: true
""")
    cfg = Config(config_file)
    # localhost should use default_provider
    provider = cfg.get_provider("127.0.0.1")
    assert provider is not None
    assert provider.name == "xiaomi"
    assert provider.base_url == "https://api.xiaomi.com/v1"


def test_default_provider_auto_single(tmp_path):
    """Auto-detect default when only one provider exists."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  xiaomi:
    base_url: https://api.xiaomi.com/v1
    keys:
      - key: sk-a
        active: true
""")
    cfg = Config(config_file)
    provider = cfg.get_provider("127.0.0.1")
    assert provider is not None
    assert provider.name == "xiaomi"


def test_default_provider_no_match_multiple(tmp_path):
    """No default when multiple providers and no explicit default."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  xiaomi:
    base_url: https://api.xiaomi.com/v1
    keys:
      - key: sk-a
        active: true
  anthropic:
    base_url: https://api.anthropic.com
    keys:
      - key: sk-b
        active: true
""")
    cfg = Config(config_file)
    # No explicit default, multiple providers -> no match for localhost
    provider = cfg.get_provider("127.0.0.1")
    assert provider is None


def test_localhost_matching(tmp_path):
    """localhost also matches default provider."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
default_provider: xiaomi

providers:
  xiaomi:
    base_url: https://api.xiaomi.com/v1
    keys:
      - key: sk-a
        active: true
""")
    cfg = Config(config_file)
    provider = cfg.get_provider("localhost")
    assert provider is not None
    assert provider.name == "xiaomi"


def test_host_matching_still_works(tmp_path):
    """Normal host matching still works with default_provider set."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
default_provider: xiaomi

providers:
  xiaomi:
    base_url: https://api.xiaomi.com/v1
    keys:
      - key: sk-a
        active: true
  anthropic:
    base_url: https://api.anthropic.com
    keys:
      - key: sk-b
        active: true
""")
    cfg = Config(config_file)
    # Direct host matching still works
    assert cfg.get_provider("api.anthropic.com").name == "anthropic"
    assert cfg.get_provider("api.xiaomi.com").name == "xiaomi"
    # localhost uses default
    assert cfg.get_provider("127.0.0.1").name == "xiaomi"
