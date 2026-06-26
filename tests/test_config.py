import tempfile
from pathlib import Path
from otel_agent.config import Config


def test_load_valid_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    type: openai
    prefix: /openai
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
    provider = cfg.get_provider("127.0.0.1")
    assert provider is not None
    assert provider.name == "xiaomi"


def test_default_provider_auto_single(tmp_path):
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
    provider = cfg.get_provider("127.0.0.1")
    assert provider is None


def test_localhost_matching(tmp_path):
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
    assert cfg.get_provider("api.anthropic.com").name == "anthropic"
    assert cfg.get_provider("api.xiaomi.com").name == "xiaomi"
    assert cfg.get_provider("127.0.0.1").name == "xiaomi"


# --- New tests for type/prefix routing ---


def test_type_inference_from_name(tmp_path):
    """Provider name containing 'anthropic' infers type=anthropic."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  xiaomi-anthropic:
    base_url: https://api.xiaomi.com/anthropic
    keys:
      - key: sk-a
        active: true
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-b
        active: true
""")
    cfg = Config(config_file)
    assert cfg.get_provider("xiaomi-anthropic").type == "anthropic"
    assert cfg.get_provider("openai").type == "openai"


def test_prefix_defaults_to_name(tmp_path):
    """Provider without explicit prefix gets /<name>."""
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
    assert cfg.get_provider("openai").prefix == "/openai"


def test_prefix_explicit(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  my-openai:
    type: openai
    prefix: /openai
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
""")
    cfg = Config(config_file)
    assert cfg.get_provider("my-openai").prefix == "/openai"


def test_get_provider_by_prefix(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    type: openai
    prefix: /openai
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
  anthropic:
    type: anthropic
    prefix: /anthropic
    base_url: https://api.anthropic.com
    keys:
      - key: sk-b
        active: true
""")
    cfg = Config(config_file)
    p = cfg.get_provider_by_prefix("/openai/v1/chat/completions")
    assert p is not None
    assert p.name == "openai"

    p = cfg.get_provider_by_prefix("/anthropic/v1/messages")
    assert p is not None
    assert p.name == "anthropic"

    assert cfg.get_provider_by_prefix("/unknown/v1/foo") is None


def test_get_provider_by_prefix_longest_match(tmp_path):
    """Longer prefix wins when both match."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  short:
    type: openai
    prefix: /open
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
  long:
    type: openai
    prefix: /openai
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-b
        active: true
""")
    cfg = Config(config_file)
    p = cfg.get_provider_by_prefix("/openai/v1/chat/completions")
    assert p.name == "long"

    p = cfg.get_provider_by_prefix("/open/other")
    assert p.name == "short"


def test_duplicate_prefix_rejected(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  a:
    type: openai
    prefix: /openai
    base_url: https://api.a.com/v1
    keys:
      - key: sk-a
        active: true
  b:
    type: openai
    prefix: /openai
    base_url: https://api.b.com/v1
    keys:
      - key: sk-b
        active: true
""")
    try:
        Config(config_file)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Duplicate prefix" in str(e)


def test_invalid_prefix_no_slash(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    type: openai
    prefix: openai
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
""")
    try:
        Config(config_file)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must start with" in str(e)


def test_invalid_type(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    type: unknown
    prefix: /openai
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
""")
    try:
        Config(config_file)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "type must be one of" in str(e)


def test_empty_base_url_rejected(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    type: openai
    prefix: /openai
    base_url: ""
    keys:
      - key: sk-a
        active: true
""")
    try:
        Config(config_file)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must have a base_url" in str(e)


def test_routes_property(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    type: openai
    prefix: /openai
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
  anthropic:
    type: anthropic
    prefix: /anthropic
    base_url: https://api.anthropic.com
    keys:
      - key: sk-b
        active: true
""")
    cfg = Config(config_file)
    routes = cfg.routes
    assert len(routes) == 2
    assert routes[0]["prefix"] == "/anthropic"
    assert routes[1]["prefix"] == "/openai"


def test_backward_compat_no_type_prefix(tmp_path):
    """Existing configs without type/prefix still work."""
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
    p = cfg.get_provider("openai")
    assert p.type == "openai"
    assert p.prefix == "/openai"
    assert cfg.get_provider_by_prefix("/openai/v1/chat/completions") is not None
