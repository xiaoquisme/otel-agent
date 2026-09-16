"""Tests for model discovery and caching."""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest

from otel_agent.config import Config, Provider
from otel_agent.models import ModelCache, aggregate_models, fetch_provider_models


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
    ids = [m["id"] for m in result["data"]]
    assert len(result["data"]) == 2
    assert "openai/gpt-4o" in ids
    assert "openai/gpt-4o-mini" in ids
    assert "auto" not in ids
    assert result["data"][0]["owned_by"] == "openai"


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
    ids = [m["id"] for m in result["data"]]
    assert len(result["data"]) == 1
    assert "xiaomi/mimo" in ids
    assert "auto" not in ids


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


# --- Declared models ---
#
# Some upstreams publish no catalog: the Codex subscription endpoint answers
# {"models":[]} even with a valid credential, so it contributes nothing and
# says nothing. An operator can declare the models on the provider row instead.


def _declared_config(tmp_path: Path, models_block: str) -> Config:
    """A subscription provider row plus whatever ``models`` block is given."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "providers:\n"
        "  - name: codex\n"
        "    base_url: https://chatgpt.com/backend-api/codex\n"
        "    auth: codex-oauth\n"
        "    api_format: openai\n"
        f"{models_block}"
    )
    return Config(config_file)


def _codex(models: tuple[str, ...]) -> Provider:
    return Provider(
        name="codex",
        base_url="https://chatgpt.com/backend-api/codex",
        api_key="",
        api_format="openai",
        auth="codex-oauth",
        models=models,
    )


class _UnreachableClient:
    """A client that fails the test if a provider is asked upstream."""

    async def get(self, *args, **kwargs):
        raise AssertionError(f"a declared provider must not be queried upstream: {args}")


def test_config_keeps_declared_models(tmp_path):
    cfg = _declared_config(tmp_path, "    models:\n      - gpt-5.6-sol\n      - gpt-5.6-sol-mini\n")
    assert cfg.get_provider("codex").models == ("gpt-5.6-sol", "gpt-5.6-sol-mini")


def test_config_without_declared_models_is_empty(tmp_path):
    cfg = _declared_config(tmp_path, "")
    assert cfg.get_provider("codex").models == ()


def test_declared_models_accept_a_bare_string(tmp_path):
    """``models: gpt-5.6-sol`` is a one-entry declaration, not a typo to drop."""
    cfg = _declared_config(tmp_path, "    models: gpt-5.6-sol\n")
    assert cfg.get_provider("codex").models == ("gpt-5.6-sol",)


def test_declared_models_drop_entries_that_are_not_usable_ids(tmp_path):
    """A malformed entry degrades to "not declared" for that entry alone —
    the row keeps listing, and config load never raises on it."""
    cfg = _declared_config(
        tmp_path,
        "    models:\n"
        "      - gpt-5.6-sol\n"
        "      - 42\n"
        "      - null\n"
        "      - ''\n"
        "      - '  gpt-5.6-sol  '\n"
        "      - gpt-5.6-sol\n",
    )
    assert cfg.get_provider("codex").models == ("gpt-5.6-sol",)


def test_declared_models_ignore_a_value_that_is_not_a_list_of_ids(tmp_path):
    cfg = _declared_config(tmp_path, "    models:\n      gpt-5.6-sol: true\n")
    assert cfg.get_provider("codex").models == ()


def test_declared_models_are_returned_without_an_upstream_call():
    provider = _codex(("gpt-5.6-sol",))
    models = asyncio.run(fetch_provider_models(_UnreachableClient(), provider))
    assert [m["id"] for m in models] == ["gpt-5.6-sol"]
    assert all(m["object"] == "model" for m in models)
    assert all(m["owned_by"] == "codex" for m in models)


def test_declared_models_need_no_credential(tmp_path, monkeypatch):
    """Listing a provider that declares its models does not resolve a bearer,
    so it still answers when the credential is broken (and reports no failure)."""
    monkeypatch.setenv("OTEL_AGENT_AUTH_PATH", str(tmp_path / "absent.json"))
    failures: dict[str, str] = {}
    models = asyncio.run(
        fetch_provider_models(_UnreachableClient(), _codex(("gpt-5.6-sol",)), failures=failures)
    )
    assert failures == {}
    assert [m["id"] for m in models] == ["gpt-5.6-sol"]


def test_undeclared_provider_still_queries_upstream():
    provider = Provider(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-a",
        api_format="openai",
    )
    seen: dict = {}

    class _Response:
        status_code = 200

        def json(self):
            return {"data": [{"id": "gpt-4o", "object": "model", "created": 7}]}

    class _Client:
        async def get(self, url, **kwargs):
            seen["url"] = str(url)
            return _Response()

    models = asyncio.run(fetch_provider_models(_Client(), provider))
    assert seen["url"] == "https://api.openai.com/v1/models"
    assert models == [{"id": "gpt-4o", "object": "model", "created": 7}]


def test_declared_models_end_up_prefixed_in_the_listing():
    """The declared id is what a client calls, so it carries the same
    ``provider/model`` prefix an upstream-discovered id would."""
    models = asyncio.run(fetch_provider_models(_UnreachableClient(), _codex(("gpt-5.6-sol",))))
    body = aggregate_models({"codex": models})
    assert [m["id"] for m in body["data"]] == ["codex/gpt-5.6-sol"]
    assert body["data"][0]["owned_by"] == "codex"
    assert "errors" not in body


# --- CLI-sourced models ---
#
# The installed vendor CLI publishes the catalog the subscription endpoint
# does not: `codex debug models` renders it as JSON, the same fix
# cursor_sidecar.list_cursor_cli_models applies for Cursor. Unlike that one,
# the source is declared on the provider row (`models_from`), so no vendor
# name appears in a conditional.
#
# Every test here stubs the subprocess: none of them may run the real binary,
# and none of them may reach the network.

_CODEX_CATALOG = json.dumps({
    "models": [
        {"slug": "gpt-6-astra", "display_name": "GPT-6-Astra", "visibility": "list"},
        {"slug": "gpt-5.6-sol", "display_name": "GPT-5.6-Sol", "visibility": "list"},
        {"slug": "codex-auto-review", "display_name": "Auto", "visibility": "hide"},
    ]
})


class _CliResult:
    """What subprocess.run hands back, without a subprocess."""

    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = ""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


class _EmptyCatalogResponse:
    status_code = 200

    def json(self):
        return {"data": []}


class _UpstreamClient:
    """Answers an empty catalog and records that upstream was asked."""

    def __init__(self):
        self.urls: list[str] = []

    async def get(self, url, **kwargs):
        self.urls.append(str(url))
        return _EmptyCatalogResponse()


def _stub_codex_cli(monkeypatch, result: _CliResult | None = None, binary: str | None = "/usr/local/bin/codex"):
    """Replace the CLI with a stub; returns the argv list it records."""
    calls: list[list[str]] = []

    def _which(name):
        assert name == "codex", f"unexpected binary lookup: {name}"
        return binary

    def _run(argv, **kwargs):
        calls.append(list(argv))
        return result if result is not None else _CliResult(_CODEX_CATALOG)

    monkeypatch.setattr("otel_agent.cli_models.shutil.which", _which)
    monkeypatch.setattr("otel_agent.cli_models.subprocess.run", _run)
    return calls


def _codex_provider(models_from: str = "codex-cli") -> Provider:
    return Provider(
        name="codex",
        base_url="https://chatgpt.com/backend-api/codex",
        api_key="sk-a",
        api_format="openai",
        models_from=models_from,
    )


def _codex_cli_config(tmp_path: Path, models_from_block: str) -> Config:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "providers:\n"
        "  - name: codex\n"
        "    base_url: https://chatgpt.com/backend-api/codex\n"
        "    auth: codex-oauth\n"
        "    api_format: openai\n"
        f"{models_from_block}"
    )
    return Config(config_file)


def test_config_keeps_a_declared_model_source(tmp_path):
    cfg = _codex_cli_config(tmp_path, "    models_from: codex-cli\n")
    assert cfg.get_provider("codex").models_from == "codex-cli"


def test_config_without_a_model_source_queries_upstream(tmp_path):
    """No declaration — the catalog is discovered from the upstream, as before."""
    cfg = _codex_cli_config(tmp_path, "")
    provider = cfg.get_provider("codex")
    assert provider.models_from == ""

    client = _UpstreamClient()
    models = asyncio.run(fetch_provider_models(client, provider))
    assert client.urls == ["https://chatgpt.com/backend-api/codex/models"]
    assert models == []


def test_an_unknown_model_source_degrades_to_the_upstream_default(tmp_path):
    """A typo costs the declaration, not the gateway: config load survives it
    and the provider keeps the behaviour it had before the field existed."""
    cfg = _codex_cli_config(tmp_path, "    models_from: codex_cli\n")
    assert cfg.get_provider("codex").models_from == ""


def test_a_malformed_model_source_degrades_to_the_upstream_default(tmp_path):
    cfg = _codex_cli_config(tmp_path, "    models_from:\n      - codex-cli\n")
    assert cfg.get_provider("codex").models_from == ""


def test_cli_source_lists_the_slugs_the_cli_reports(monkeypatch):
    calls = _stub_codex_cli(monkeypatch)
    models = asyncio.run(fetch_provider_models(_UnreachableClient(), _codex_provider()))
    assert [m["id"] for m in models] == ["gpt-6-astra", "gpt-5.6-sol", "codex-auto-review"]
    assert all(m["object"] == "model" for m in models)
    assert all(m["owned_by"] == "codex" for m in models)
    assert all(m["created"] == 0 for m in models)
    assert calls == [["/usr/local/bin/codex", "debug", "models"]]


def test_cli_source_needs_no_credential(tmp_path, monkeypatch):
    """Listing from the CLI resolves no bearer, so a broken grant is not an
    error here — nothing was needed to answer."""
    monkeypatch.setenv("OTEL_AGENT_AUTH_PATH", str(tmp_path / "absent.json"))
    _stub_codex_cli(monkeypatch)
    failures: dict[str, str] = {}
    models = asyncio.run(
        fetch_provider_models(_UnreachableClient(), _codex_provider(), failures=failures)
    )
    assert failures == {}
    assert [m["id"] for m in models] == ["gpt-6-astra", "gpt-5.6-sol", "codex-auto-review"]


def test_a_cli_that_lists_no_models_is_an_answer_not_a_failure(monkeypatch):
    _stub_codex_cli(monkeypatch, _CliResult(json.dumps({"models": []})))
    models = asyncio.run(fetch_provider_models(_UnreachableClient(), _codex_provider()))
    assert models == []


def test_missing_cli_binary_degrades_without_raising(monkeypatch):
    _stub_codex_cli(monkeypatch, binary=None)
    client = _UpstreamClient()
    models = asyncio.run(fetch_provider_models(client, _codex_provider()))
    assert models == []
    assert client.urls == ["https://chatgpt.com/backend-api/codex/models"]


def test_cli_non_zero_exit_degrades_without_raising(monkeypatch):
    _stub_codex_cli(monkeypatch, _CliResult(stdout="", returncode=2, stderr="unrecognized"))
    client = _UpstreamClient()
    models = asyncio.run(fetch_provider_models(client, _codex_provider()))
    assert models == []
    assert client.urls == ["https://chatgpt.com/backend-api/codex/models"]


def test_unparsable_cli_output_degrades_without_raising(monkeypatch):
    _stub_codex_cli(monkeypatch, _CliResult(stdout="error: no catalog for you\n"))
    client = _UpstreamClient()
    models = asyncio.run(fetch_provider_models(client, _codex_provider()))
    assert models == []
    assert client.urls == ["https://chatgpt.com/backend-api/codex/models"]


def test_cli_entries_without_a_usable_slug_are_dropped(monkeypatch):
    _stub_codex_cli(
        monkeypatch,
        _CliResult(json.dumps({"models": [
            {"slug": "gpt-6-astra"},
            {"display_name": "no slug"},
            {"slug": ""},
            {"slug": 7},
            "gpt-5.5",
            {"slug": "gpt-6-astra"},
        ]})),
    )
    models = asyncio.run(fetch_provider_models(_UnreachableClient(), _codex_provider()))
    assert [m["id"] for m in models] == ["gpt-6-astra"]


def test_cli_sourced_ids_end_up_prefixed_in_the_listing(monkeypatch):
    """A CLI id is called the same way any discovered id is, so it carries the
    same ``provider/model`` prefix."""
    _stub_codex_cli(monkeypatch)
    models = asyncio.run(fetch_provider_models(_UnreachableClient(), _codex_provider()))
    body = aggregate_models({"codex": models})
    assert [m["id"] for m in body["data"]] == [
        "codex/gpt-6-astra", "codex/gpt-5.6-sol", "codex/codex-auto-review",
    ]
    assert body["data"][0]["owned_by"] == "codex"
    assert "errors" not in body
