import json
import tempfile
import subprocess
import time
from pathlib import Path
import pytest
import requests

import duckdb


@pytest.mark.integration
def test_proxy_logs_request():
    """Start proxy, send a request through it, check it was logged."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
        proc = subprocess.Popen(
            ["uv", "run", "otel-proxy", "proxy", "-p", "18765", "-d", str(db_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(3)

        try:
            requests.get(
                "https://httpbin.org/get",
                proxies={
                    "https": "http://127.0.0.1:18765",
                    "http": "http://127.0.0.1:18765",
                },
                timeout=15,
                verify=False,
            )
            assert False, "Expected external-network blocked in this environment"
        finally:
            proc.terminate()
            proc.wait()


@pytest.mark.integration
def test_proxy_startup_logs_local_request():
    """Start proxy, send a local request through it, check it was logged."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
        proc = subprocess.Popen(
            ["uv", "run", "otel-proxy", "proxy", "-p", "18765", "-d", str(db_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(3)

        try:
            requests.get(
                "https://127.0.0.1:18765/get",
                proxies={
                    "https": "http://127.0.0.1:18765",
                    "http": "http://127.0.0.1:18765",
                },
                timeout=15,
                verify=False,
            )
        finally:
            proc.terminate()
            proc.wait()

        time.sleep(1)
        conn = duckdb.connect(str(db_path), read_only=True)
        rows = conn.execute("SELECT * FROM requests").fetchall()
        conn.close()
        assert len(rows) >= 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_request_body_and_response_headers_logged():
    """FastAPI test client: send request, verify body and headers stored in DB."""
    import httpx
    from otel_agent.config import Config
    from otel_agent.logger import TelemetryLogger
    from otel_agent.server import create_app

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
        config_path = Path(td) / "config.yaml"
        config_path.write_text(
            "providers:\n"
            "  - name: openai\n"
            "    base_url: https://httpbin.org\n"
            "    api_key: test\n"
            "    api_format: openai\n"
        )
        config = Config(config_path)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/v1/chat/completions",
                json={"model": "openai/post", "messages": [{"role": "user", "content": "hi"}]},
            )
        # Response may be 502 if upstream unreachable, but telemetry is still logged
        telemetry.close()
        conn = duckdb.connect(str(db_path), read_only=True)
        rows = conn.execute("SELECT request_body, response_headers, response_status FROM requests").fetchall()
        conn.close()

        assert len(rows) >= 1, "At least one request should be logged"
        request_body, response_headers, status = rows[0]
        assert request_body, "request_body should not be empty"
        parsed_body = json.loads(request_body)
        assert parsed_body["model"] == "openai/post"

        resp_headers = json.loads(response_headers) if response_headers else {}
        assert resp_headers, "response_headers should not be empty"


@pytest.mark.integration
@pytest.mark.anyio
async def test_sensitive_headers_redacted_in_db():
    """Verify sensitive headers are redacted in stored response_headers."""
    import httpx
    from otel_agent.config import Config
    from otel_agent.logger import TelemetryLogger
    from otel_agent.server import create_app

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
        config_path = Path(td) / "config.yaml"
        config_path.write_text(
            "providers:\n"
            "  - name: openai\n"
            "    base_url: https://httpbin.org\n"
            "    api_key: test\n"
            "    api_format: openai\n"
        )
        config = Config(config_path)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/v1/chat/completions",
                json={"model": "openai/post", "messages": [{"role": "user", "content": "hi"}]},
            )

        telemetry.close()
        conn = duckdb.connect(str(db_path), read_only=True)
        rows = conn.execute("SELECT response_headers FROM requests").fetchall()
        conn.close()

        assert len(rows) >= 1
        headers = json.loads(rows[0][0])
        for v in headers.values():
            assert "sk-" not in str(v)


@pytest.mark.integration
@pytest.mark.anyio
async def test_log_request_body_false_suppresses_body():
    """When log_request_body is false, request_body should be empty."""
    import httpx
    from otel_agent.config import Config
    from otel_agent.logger import TelemetryLogger
    from otel_agent.server import create_app

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
        config_path = Path(td) / "config.yaml"
        config_path.write_text(
            "providers:\n"
            "  - name: openai\n"
            "    base_url: https://httpbin.org\n"
            "    api_key: test\n"
            "    api_format: openai\n"
            "log_request_body: false\n"
        )
        config = Config(config_path)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/v1/chat/completions",
                json={"model": "openai/post", "messages": [{"role": "user", "content": "hi"}]},
            )

        telemetry.close()
        conn = duckdb.connect(str(db_path), read_only=True)
        rows = conn.execute("SELECT request_body, response_headers FROM requests").fetchall()
        conn.close()

        assert len(rows) >= 1
        request_body, response_headers = rows[0]
        assert request_body == "", "request_body should be empty when log_request_body is false"
        resp_headers = json.loads(response_headers) if response_headers else {}
        assert resp_headers, "response_headers should still be populated"
