import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from otel_agent.addon import TelemetryAddon
from otel_agent.config import Config
from otel_agent.logger import TelemetryLogger
from otel_agent.rotator import KeyRotator


def _make_config(tmp_path, yaml_content):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml_content)
    return Config(config_file)


def _make_flow(method="POST", url="https://api.openai.com/v1/chat/completions",
               req_body='{"model":"gpt-4"}', resp_body='{"choices":[]}',
               resp_status=200, path="/v1/chat/completions"):
    flow = MagicMock()
    flow.request.method = method
    flow.request.url = url
    flow.request.host = "api.openai.com"
    flow.request.headers = {}
    flow.request.get_content.return_value = req_body.encode()
    flow.request.scheme = "https"
    flow.request.port = 443
    flow.request.path = path
    flow.response = MagicMock()
    flow.response.status_code = resp_status
    flow.response.headers = {"content-type": "application/json"}
    flow.response.get_content.return_value = resp_body.encode()
    flow.response.timestamp_start = 1000.0
    flow.response.timestamp_end = 1001.5
    return flow


def _make_addon(tmp_path, yaml_content, upstream_override=""):
    db_path = tmp_path / "test.db"
    logger = TelemetryLogger(db_path)
    config = _make_config(tmp_path, yaml_content)
    rotator = KeyRotator(config)
    return TelemetryAddon(logger, config, rotator, upstream_override=upstream_override)


def test_addon_routes_openai_path(tmp_path):
    addon = _make_addon(tmp_path, """
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-openai
      active: true
""")
    flow = _make_flow(path="/openai/v1/chat/completions")
    addon.request(flow)
    assert flow.request.host == "api.openai.com"
    assert flow.request.path == "/v1/chat/completions"
    assert flow.request.headers["Authorization"] == "Bearer sk-openai"


def test_addon_routes_anthropic_path(tmp_path):
    addon = _make_addon(tmp_path, """
providers:
  anthropic:
    - name: deesseek
      base_url: https://api.anthropic.com
      api_key: sk-ant
      active: true
""")
    flow = _make_flow(path="/anthropic/v1/messages")
    addon.request(flow)
    assert flow.request.host == "api.anthropic.com"
    assert flow.request.path == "/v1/messages"
    assert flow.request.headers["x-api-key"] == "sk-ant"


def test_addon_strips_openai_prefix(tmp_path):
    addon = _make_addon(tmp_path, """
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-a
      active: true
""")
    flow = _make_flow(path="/openai/v1/chat/completions")
    addon.request(flow)
    assert flow.request.path == "/v1/chat/completions"


def test_addon_strips_anthropic_prefix(tmp_path):
    addon = _make_addon(tmp_path, """
providers:
  anthropic:
    - name: deesseek
      base_url: https://api.anthropic.com
      api_key: sk-a
      active: true
""")
    flow = _make_flow(path="/anthropic/v1/messages")
    addon.request(flow)
    assert flow.request.path == "/v1/messages"


def test_addon_exact_path_match(tmp_path):
    addon = _make_addon(tmp_path, """
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-a
      active: true
""")
    flow = _make_flow(path="/openai")
    addon.request(flow)
    assert flow.request.path == "/"


def test_addon_unknown_path_ignored(tmp_path):
    addon = _make_addon(tmp_path, """
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-a
      active: true
""")
    flow = _make_flow(path="/unknown/v1/foo")
    flow.request.host = "api.cohere.com"
    flow.request.headers = {"Authorization": "Bearer original"}
    addon.request(flow)
    assert flow.request.headers["Authorization"] == "Bearer original"


def test_addon_injects_openai_key(tmp_path):
    addon = _make_addon(tmp_path, """
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-test123
      active: true
""")
    flow = _make_flow(path="/openai/v1/chat/completions")
    addon.request(flow)
    assert flow.request.headers["Authorization"] == "Bearer sk-test123"


def test_addon_injects_anthropic_key(tmp_path):
    addon = _make_addon(tmp_path, """
providers:
  anthropic:
    - name: deesseek
      base_url: https://api.anthropic.com
      api_key: sk-ant-xxx
      active: true
""")
    flow = _make_flow(path="/anthropic/v1/messages")
    addon.request(flow)
    assert flow.request.headers["x-api-key"] == "sk-ant-xxx"


def test_addon_raises_when_no_active_provider(tmp_path):
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
        _make_addon(tmp_path, """
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-a
      active: false
""")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "no active provider" in str(e)


def test_addon_logs_request(tmp_path):
    db_path = tmp_path / "test.db"
    addon = _make_addon(tmp_path, """
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-a
      active: true
""")
    flow = _make_flow(path="/openai/v1/chat/completions")
    addon.response(flow)
    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT method, request_body FROM requests").fetchone()
    conn.close()
    assert row[0] == "POST"
    assert "gpt-4" in row[1]


def test_addon_calculates_latency(tmp_path):
    db_path = tmp_path / "test.db"
    addon = _make_addon(tmp_path, """
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-a
      active: true
""")
    flow = _make_flow(path="/openai/v1/chat/completions")
    flow.response.timestamp_start = 1000.0
    flow.response.timestamp_end = 1001.5
    addon.response(flow)
    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT latency_ms FROM requests").fetchone()
    conn.close()
    assert row[0] == 1500.0


def test_addon_config_hot_reload(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-a
      active: true
""")
    db_path = tmp_path / "test.db"
    logger = TelemetryLogger(db_path)
    config = Config(config_file)
    rotator = KeyRotator(config)
    addon = TelemetryAddon(logger, config, rotator)

    flow = _make_flow(path="/openai/v1/chat/completions")
    addon.request(flow)
    assert flow.request.headers["Authorization"] == "Bearer sk-a"

    config_file.write_text("""
providers:
  openai:
    - name: deesseek
      base_url: https://api.deesseek.com/v1
      api_key: sk-b
      active: true
""")
    flow = _make_flow(path="/openai/v1/chat/completions")
    addon.request(flow)
    assert flow.request.headers["Authorization"] == "Bearer sk-b"


def test_strip_prefix():
    assert TelemetryAddon._strip_prefix("/openai/v1/chat", "/openai") == "/v1/chat"
    assert TelemetryAddon._strip_prefix("/anthropic/v1/messages", "/anthropic") == "/v1/messages"
    assert TelemetryAddon._strip_prefix("/openai", "/openai") == "/"
    assert TelemetryAddon._strip_prefix("/other/path", "/openai") == "/other/path"
