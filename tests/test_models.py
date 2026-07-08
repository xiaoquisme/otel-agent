"""Tests for model discovery and caching."""

import time
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest

from otel_agent.config import Config
from otel_agent.models import ModelCache, aggregate_models


# --- ModelCache tests ---


def test_cache_returns_none_when_empty(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
""")
    config = Config(config_file)
    cache = ModelCache(config)
    assert cache.get("openai") is None


def test_cache_stores_and_retrieves(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
""")
    config = Config(config_file)
    cache = ModelCache(config)
    models = [{"id": "gpt-4o", "object": "model", "created": 0}]
    cache.put("openai", models)
    assert cache.get("openai") == models


def test_cache_expires_after_ttl(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
""")
    config = Config(config_file)
    cache = ModelCache(config, ttl=0.01)
    cache.put("openai", [{"id": "gpt-4o"}])
    assert cache.get("openai") is not None

    time.sleep(0.02)
    assert cache.get("openai") is None


def test_cache_invalidates_on_config_change(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
""")
    config = Config(config_file)
    cache = ModelCache(config, ttl=300)
    cache.put("openai", [{"id": "gpt-4o"}])
    assert cache.get("openai") is not None

    # Change config file (triggers mtime change)
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-b
""")
    # Force config reload
    config._reload()
    assert cache.get("openai") is None


def test_cache_invalidate_clears_all(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
""")
    config = Config(config_file)
    cache = ModelCache(config)
    cache.put("openai", [{"id": "gpt-4o"}])
    cache.invalidate()
    assert cache.get("openai") is None


# --- aggregate_models tests ---


def test_aggregate_basic():
    raw = {
        "openai": [
            {"id": "gpt-4o", "object": "model", "created": 100},
            {"id": "gpt-4o-mini", "object": "model", "created": 200},
        ],
    }
    result = aggregate_models(raw)
    assert result["object"] == "list"
    assert len(result["data"]) == 2
    assert result["data"][0]["id"] == "openai/gpt-4o"
    assert result["data"][0]["owned_by"] == "openai"
    assert result["data"][1]["id"] == "openai/gpt-4o-mini"


def test_aggregate_multiple_providers():
    raw = {
        "openai": [{"id": "gpt-4o"}],
        "xiaomi": [{"id": "mimo-v-2.5"}],
    }
    result = aggregate_models(raw)
    ids = [m["id"] for m in result["data"]]
    assert "openai/gpt-4o" in ids
    assert "xiaomi/mimo-v-2.5" in ids


def test_aggregate_empty():
    result = aggregate_models({})
    assert result == {"object": "list", "data": []}


def test_aggregate_provider_with_empty_models():
    raw = {"openai": [], "xiaomi": [{"id": "mimo"}]}
    result = aggregate_models(raw)
    assert len(result["data"]) == 1
    assert result["data"][0]["id"] == "xiaomi/mimo"


def test_aggregate_preserves_created_field():
    raw = {"openai": [{"id": "gpt-4o", "created": 12345}]}
    result = aggregate_models(raw)
    assert result["data"][0]["created"] == 12345


def test_aggregate_missing_created_defaults_zero():
    raw = {"openai": [{"id": "gpt-4o"}]}
    result = aggregate_models(raw)
    assert result["data"][0]["created"] == 0


def test_aggregate_sorted_by_provider():
    raw = {
        "xiaomi": [{"id": "mimo"}],
        "anthropic": [{"id": "claude"}],
        "openai": [{"id": "gpt"}],
    }
    result = aggregate_models(raw)
    providers = [m["owned_by"] for m in result["data"]]
    assert providers == ["anthropic", "openai", "xiaomi"]
