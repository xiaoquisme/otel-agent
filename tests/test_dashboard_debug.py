"""Debug discovers protocols but executes the actual gateway (mock upstream only)."""
import json
import sqlite3
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from otel_agent import server
from otel_agent.config import Config
from otel_agent.logger import TelemetryLogger


@contextmanager
def debug_gateway(tmp_path, monkeypatch, handler, *, log_body=True, extra=""):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"""
log_request_body: {str(log_body).lower()}
providers:
  - name: chat
    base_url: https://chat.test/v1
    api_key: private-chat-key
    models: [claude-misleading]
  - name: anthropic
    base_url: https://anthropic.test
    api_format: anthropic
    api_key: private-anthropic-key
    models: [gpt-misleading]
  - name: responses
    base_url: https://responses.test/codex
    auth: codex-oauth
    models: [claude-also-misleading]
{extra}
""")
    real_client = httpx.AsyncClient
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: real_client(
        **kw, transport=httpx.MockTransport(handler),
    ))

    async def bearer(provider):
        return provider.api_key or "private-codex-token"

    monkeypatch.setattr("otel_agent.provider_utils.resolve_bearer_async", bearer)
    db = tmp_path / "telemetry.sqlite"
    telemetry = TelemetryLogger(db)
    app = server.create_app(Config(config_file), telemetry)
    with TestClient(app) as client:
        yield client, db


def unreachable(request):
    pytest.fail(f"Unexpected upstream request: {request.url}")


def test_debug_discovery_selects_config_not_model_names(tmp_path, monkeypatch):
    with debug_gateway(tmp_path, monkeypatch, unreachable, log_body=False) as (client, _):
        response = client.get("/api/debug/models")
        assert response.status_code == 200
        body = response.json()
        assert body["log_request_body"] is False
        assert {m["id"]: m["endpoint"] for m in body["data"]} == {
            "chat/claude-misleading": "/v1/chat/completions",
            "anthropic/gpt-misleading": "/v1/messages",
            "responses/claude-also-misleading": "/v1/responses",
        }
        assert "private-" not in response.text
        assert "base_url" not in response.text
        assert "Authorization" not in response.text


@pytest.mark.parametrize("failure", ["http", "connection", "json", "shape", "entry"])
def test_debug_discovery_partial_failures_are_visible_and_retried(tmp_path, monkeypatch, failure):
    calls = []

    def handler(request):
        calls.append(request)
        if failure == "connection":
            raise httpx.ConnectError("private-chat-key", request=request)
        if failure == "http":
            return httpx.Response(403, json={"error": "private-chat-key"})
        if failure == "json":
            return httpx.Response(200, text="private-chat-key")
        if failure == "entry":
            return httpx.Response(200, json={"data": [None]})
        return httpx.Response(200, json={"data": {"not": "a list"}})

    extra = """  - name: broken
    base_url: https://broken.test/v1
    api_key: private-broken-key
"""
    with debug_gateway(tmp_path, monkeypatch, handler, extra=extra) as (client, _):
        for _ in range(2):
            response = client.get("/api/debug/models")
            assert response.status_code == 200
            body = response.json()
            assert len(body["data"]) == 3
            assert body["errors"][0]["provider"] == "broken"
            assert body["errors"][0]["type"] == "model_discovery_error"
            assert "private-" not in response.text
        assert len(calls) == 2  # failed catalogs are never cached as empty success


def test_provider_specific_catalog_error_is_not_a_credential_error(tmp_path, monkeypatch):
    extra = """  - name: broken
    base_url: https://broken.test/v1
    api_key: private-broken-key
"""
    with debug_gateway(tmp_path, monkeypatch, lambda request: httpx.Response(429), extra=extra) as (client, _):
        response = client.get("/v1/models?provider=broken")
        assert response.status_code == 502
        assert response.json()["error"]["type"] == "model_discovery_error"
        assert "429" in response.json()["error"]["message"]


def test_debug_discovery_handles_provider_removed_during_fetch(tmp_path, monkeypatch):
    extra = """  - name: transient
    base_url: https://transient.test/v1
    api_key: private-transient-key
"""
    def handler(request):
        path = tmp_path / "config.yaml"
        path.write_text(path.read_text().replace(extra, ""))
        return httpx.Response(200, json={"data": [{"id": "text-model"}]})

    with debug_gateway(tmp_path, monkeypatch, handler, extra=extra) as (client, _):
        response = client.get("/api/debug/models")
        assert response.status_code == 200
        assert len(response.json()["data"]) == 3


def test_debug_discovery_filters_only_known_non_text_models(tmp_path, monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"data": [
            {"id": "text", "output_modalities": ["text", "image"]},
            {"id": "image", "output_modalities": ["image"]},
            {"id": "unknown"},
        ]})

    extra = """  - name: catalog
    base_url: https://catalog.test/v1
    api_key: private-catalog-key
"""
    with debug_gateway(tmp_path, monkeypatch, handler, extra=extra) as (client, _):
        ids = {m["id"] for m in client.get("/api/debug/models").json()["data"]}
        assert "catalog/text" in ids and "catalog/unknown" in ids
        assert "catalog/image" not in ids
        assert len(client.get("/v1/models").json()["data"]) == 6  # public list unchanged


MODELS = [
    ("chat/claude-misleading", "/v1/chat/completions", "/v1/chat/completions", "openai"),
    ("anthropic/gpt-misleading", "/v1/messages", "/v1/messages", "anthropic"),
    ("responses/claude-also-misleading", "/v1/responses", "/codex/responses", "responses"),
]


def text_request(model, endpoint):
    if endpoint == "/v1/responses":
        return {"model": model, "stream": False, "instructions": "", "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "hello debug"}]},
        ]}
    body = {"model": model, "stream": False,
            "messages": [{"role": "user", "content": "hello debug"}]}
    if endpoint == "/v1/messages":
        body["max_tokens"] = 1024
    return body


@pytest.mark.parametrize("model,endpoint,upstream_path,fmt", MODELS)
@pytest.mark.parametrize("log_body", [True, False])
def test_debug_executes_native_gateway_and_telemetry(tmp_path, monkeypatch, model, endpoint, upstream_path, fmt, log_body):
    seen = []
    if fmt == "responses":
        payload = {"id": "resp_1", "object": "response", "status": "completed", "model": model.split("/", 1)[1],
                   "output": [{"type": "message", "content": [{"type": "output_text", "text": "answer"}]}],
                   "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}}
    elif fmt == "anthropic":
        payload = {"id": "msg_1", "type": "message", "role": "assistant", "model": "gpt-misleading",
                   "content": [{"type": "text", "text": "answer"}], "stop_reason": "end_turn",
                   "usage": {"input_tokens": 3, "output_tokens": 2}}
    else:
        payload = {"id": "chat_1", "model": "claude-misleading", "choices": [{"message": {"content": "answer"}}],
                   "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}

    def handler(request):
        seen.append(request)
        assert request.url.path == upstream_path
        sent = json.loads(request.content)
        assert sent["model"] == model.split("/", 1)[1]
        assert "hello debug" in request.content.decode()
        if fmt == "anthropic":
            assert request.headers["x-api-key"] == "private-anthropic-key"
        else:
            assert request.headers["authorization"].startswith("Bearer private-")
        if fmt == "responses":
            assert sent["stream"] is True and sent["store"] is False
            frame = f'event: response.completed\ndata: {json.dumps({"type": "response.completed", "response": payload})}\n\n'
            return httpx.Response(200, text=frame, headers={"content-type": "text/event-stream"})
        assert sent["stream"] is False
        return httpx.Response(200, json=payload)

    with debug_gateway(tmp_path, monkeypatch, handler, log_body=log_body) as (client, db):
        selected = next(m for m in client.get("/api/debug/models").json()["data"] if m["id"] == model)
        assert selected["endpoint"] == endpoint
        response = client.post(endpoint, json=text_request(model, endpoint))
        assert response.status_code == 200
        assert response.json() == payload  # no debug wrapper or native error/usage conversion
        assert "private-" not in response.text
        assert "authorization" not in response.headers
        assert len(seen) == 1
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT url, request_body, format, input_tokens, output_tokens, response_status FROM requests").fetchone()
    assert row[0].endswith(endpoint)
    assert ("hello debug" in row[1]) is log_body
    assert row[2:] == (fmt, 3, 2, 200)


@pytest.mark.parametrize("model,endpoint,upstream_path,fmt", MODELS)
@pytest.mark.parametrize("status", [401, 404, 429, 500])
def test_debug_preserves_gateway_errors_including_unknown_model(tmp_path, monkeypatch, model, endpoint, upstream_path, fmt, status):
    def handler(request):
        assert request.url.path == upstream_path
        return httpx.Response(status, json={"error": {"message": "unknown model" if status == 404 else "rejected", "type": "upstream_error"}})

    with debug_gateway(tmp_path, monkeypatch, handler) as (client, _):
        response = client.post(endpoint, json=text_request(model.split("/")[0] + "/unknown", endpoint))
        assert response.status_code == status
        assert "error" in response.json()
        assert "choices" not in response.json()
        assert "private-" not in response.text


def test_debug_credential_discovery_failure_keeps_other_models(tmp_path, monkeypatch):
    from otel_agent.auth_vault import AuthError

    extra = """  - name: expired
    base_url: https://expired.test/v1
    auth: codex-oauth
"""
    with debug_gateway(tmp_path, monkeypatch, unreachable, extra=extra) as (client, _):
        async def bearer(provider):
            raise AuthError("Credential unavailable", provider=provider.name)

        monkeypatch.setattr("otel_agent.provider_utils.resolve_bearer_async", bearer)
        body = client.get("/api/debug/models").json()
        assert len(body["data"]) == 3
        assert body["errors"] == [{"provider": "expired", "message": "Credential unavailable", "type": "credential_error"}]


def test_debug_discovers_anthropic_with_native_auth_and_url(tmp_path, monkeypatch):
    def handler(request):
        assert str(request.url) == "https://native.test/v1/models"
        assert request.headers["x-api-key"] == "private-native-key"
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"data": [{"id": "text-model"}]})

    extra = """  - name: native
    base_url: https://native.test
    api_format: anthropic
    api_key: private-native-key
"""
    with debug_gateway(tmp_path, monkeypatch, handler, extra=extra) as (client, _):
        body = client.get("/api/debug/models").json()
        assert not body["errors"]
        assert {"id": "native/text-model", "owned_by": "native", "endpoint": "/v1/messages"} in body["data"]


@pytest.mark.parametrize("event", [
    {"type": "error", "message": "quota exhausted"},
    {"type": "response.failed", "response": {"error": {"message": "generation failed"}}},
])
def test_debug_responses_stream_failure_is_not_success(tmp_path, monkeypatch, event):
    def handler(request):
        return httpx.Response(200, text=f"data: {json.dumps(event)}\n\n", headers={"content-type": "text/event-stream"})

    with debug_gateway(tmp_path, monkeypatch, handler) as (client, _):
        response = client.post("/v1/responses", json=text_request("responses/text-model", "/v1/responses"))
        assert response.status_code == 502
        assert response.json()["error"]


def test_debug_unknown_provider_does_not_call_upstream(tmp_path, monkeypatch):
    with debug_gateway(tmp_path, monkeypatch, unreachable) as (client, _):
        for endpoint in ("/v1/messages", "/v1/chat/completions", "/v1/responses"):
            response = client.post(endpoint, json=text_request("missing/model", endpoint))
            assert response.status_code == 400
            assert response.json()["error"]["type"] == "invalid_request_error"
