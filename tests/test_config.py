import tempfile
from pathlib import Path
from otel_agent.config import Config


def test_load_valid_config(tmp_path):
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
    provider = cfg.get_active_provider("openai")
    assert provider is not None
    assert provider.base_url == "https://api.openai.com/v1"


def test_active_provider_only(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-a
      active: true
    - name: deesseek
      base_url: https://api.deesseek.com/v1
      api_key: sk-b
      active: false
""")
    cfg = Config(config_file)
    provider = cfg.get_active_provider("openai")
    assert provider is not None
    assert provider.name == "xiaomi"


def test_zero_active_providers_rejected(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-a
      active: false
""")
    try:
        Config(config_file)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "no active provider" in str(e)
        assert "Available providers: xiaomi" in str(e)
        assert "Set 'active: true'" in str(e)


def test_multiple_active_providers_rejected(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-a
      active: true
    - name: deesseek
      base_url: https://api.deesseek.com/v1
      api_key: sk-b
      active: true
""")
    try:
        Config(config_file)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "multiple active providers" in str(e)
        assert "Only one provider can be active" in str(e)


def test_missing_config_returns_empty():
    cfg = Config(Path("/nonexistent/config.yaml"))
    assert cfg.get_active_provider("openai") is None
    assert cfg.routes == []


def test_reload_on_change(tmp_path):
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
    assert cfg.get_active_provider("openai").name == "xiaomi"

    config_file.write_text("""
providers:
  openai:
    - name: deesseek
      base_url: https://api.deesseek.com/v1
      api_key: sk-b
      active: true
""")
    assert cfg.get_active_provider("openai").name == "deesseek"


def test_default_provider_explicit(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: xiaomi
      base_url: https://api.xiaomi.com/v1
      api_key: sk-a
      active: true
  anthropic:
    - name: xiaomi-anthropic
      base_url: https://api.xiaomi.com/anthropic
      api_key: sk-b
      active: true
""")
    cfg = Config(config_file)
    provider = cfg.get_active_provider("openai")
    assert provider is not None
    assert provider.name == "xiaomi"


def test_default_provider_auto_single(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: xiaomi
      base_url: https://api.xiaomi.com/v1
      api_key: sk-a
      active: true
""")
    cfg = Config(config_file)
    provider = cfg.get_active_provider("openai")
    assert provider is not None
    assert provider.name == "xiaomi"


def test_default_provider_no_match_multiple(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: xiaomi
      base_url: https://api.xiaomi.com/v1
      api_key: sk-a
      active: true
  anthropic:
    - name: anthropic
      base_url: https://api.anthropic.com
      api_key: sk-b
      active: true
""")
    cfg = Config(config_file)
    assert cfg.get_active_provider("unknown") is None


def test_localhost_matching(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: xiaomi
      base_url: https://api.xiaomi.com/v1
      api_key: sk-a
      active: true
""")
    cfg = Config(config_file)
    provider = cfg.get_active_provider("openai")
    assert provider is not None
    assert provider.name == "xiaomi"


def test_host_matching_still_works(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: xiaomi
      base_url: https://api.xiaomi.com/v1
      api_key: sk-a
      active: true
  anthropic:
    - name: anthropic
      base_url: https://api.anthropic.com
      api_key: sk-b
      active: true
""")
    cfg = Config(config_file)
    assert cfg.get_active_provider("anthropic").name == "anthropic"
    assert cfg.get_active_provider("openai").name == "xiaomi"


# --- New tests for provider-type active routing ---


def test_active_provider_lookup_by_type(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-openai
      active: true
    - name: deesseek
      base_url: https://api.deesseek.com/v1
      api_key: sk-ds
      active: false
  anthropic:
    - name: xiaomi
      base_url: https://api.xiaomi.com/anthropic
      api_key: sk-ant-a
      active: false
    - name: deesseek
      base_url: https://api.anthropic.com
      api_key: sk-ant-b
      active: true
""")
    cfg = Config(config_file)
    assert cfg.get_active_provider("openai").name == "xiaomi"
    assert cfg.get_active_provider("anthropic").name == "deesseek"


def test_routes_property(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-openai
      active: true
  anthropic:
    - name: deesseek
      base_url: https://api.anthropic.com
      api_key: sk-ant-b
      active: true
""")
    cfg = Config(config_file)
    routes = cfg.routes
    assert len(routes) == 2
    assert routes[0]["prefix"] == "/anthropic"
    assert routes[0]["provider"] == "deesseek"
    assert routes[1]["prefix"] == "/openai"
    assert routes[1]["provider"] == "xiaomi"


def test_duplicate_type_rejected(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: a
      base_url: https://api.a.com/v1
      api_key: sk-a
      active: true
    - name: b
      base_url: https://api.b.com/v1
      api_key: sk-b
      active: true
""")
    try:
        Config(config_file)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "multiple active providers" in str(e)


def test_invalid_type(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  unknown:
    - name: a
      base_url: https://api.a.com/v1
      api_key: sk-a
      active: true
""")
    try:
        Config(config_file)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "is not valid" in str(e)
        assert "Must be one of:" in str(e)


def test_empty_base_url_rejected(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: a
      base_url: ""
      api_key: sk-a
      active: true
""")
    try:
        Config(config_file)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must have a base_url" in str(e)
        assert "Add a valid URL" in str(e)


def test_empty_api_key_rejected(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: a
      base_url: https://api.a.com/v1
      api_key: ""
      active: true
""")
    try:
        Config(config_file)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must have an api_key" in str(e)
        assert "Add a valid API key" in str(e)
