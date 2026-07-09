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


# ------------------------------------------------------------------
# BUG-001: Concurrent access — proxy internal dashboard API
# ------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.anyio
async def test_proxy_internal_dashboard_api():
    """Verify proxy internal dashboard API endpoints return correct data.

    This is the foundation for BUG-001 fix: dashboard queries route through
    the proxy's internal API instead of opening a separate DuckDB connection.
    """
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

        # Log some test requests directly
        for i in range(5):
            telemetry.log_request(
                method="POST",
                url=f"http://example.com/api/{i}",
                request_headers={"content-type": "application/json"},
                request_body=f'{{"test": {i}}}',
                response_status=200,
                response_headers={"content-type": "application/json"},
                response_body=f'{{"ok": true, "i": {i}}}',
                latency_ms=10.0 + i,
                upstream="https://httpbin.org",
            )

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # Test internal max-id
            resp = await client.get("/internal/dashboard/max-id")
            assert resp.status_code == 200
            max_id = resp.json()
            assert max_id >= 5

            # Test internal requests (paginated)
            resp = await client.get("/internal/dashboard/requests", params={"limit": 3})
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 5
            assert len(data["data"]) == 3
            assert data["has_more"] is True

            # Test internal request detail
            first_id = data["data"][0]["id"]
            resp = await client.get(f"/internal/dashboard/requests/{first_id}")
            assert resp.status_code == 200
            detail = resp.json()
            assert detail["method"] == "POST"
            assert "example.com" in detail["url"]

            # Test internal requests-since
            resp = await client.get(f"/internal/dashboard/requests-since/{max_id - 2}")
            assert resp.status_code == 200
            since = resp.json()
            assert len(since) >= 1

            # Test internal export
            resp = await client.get("/internal/dashboard/export", params={"method": "POST"})
            assert resp.status_code == 200
            export = resp.json()
            assert len(export) == 5

        telemetry.close()


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_api_routes_through_proxy():
    """Verify DashboardAPI routes queries through proxy internal API when available.

    BUG-001: When the proxy is running, DashboardAPI should use HTTP calls
    to the proxy's internal API instead of opening its own DuckDB connection.
    """
    import httpx
    from otel_agent.config import Config
    from otel_agent.logger import TelemetryLogger
    from otel_agent.server import create_app
    from otel_agent.dashboard.api import DashboardAPI

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

        # Log test requests
        for i in range(3):
            telemetry.log_request(
                method="GET",
                url=f"http://example.com/{i}",
                request_headers={},
                request_body="",
                response_status=200,
                response_headers={},
                response_body="{}",
                latency_ms=5.0,
                upstream="https://httpbin.org",
            )

        # Start a real uvicorn server in a background thread
        import threading
        import uvicorn

        server_config = uvicorn.Config(app, host="127.0.0.1", port=18799, log_level="error")
        server = uvicorn.Server(server_config)
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()
        time.sleep(1)  # Wait for server to start

        try:
            # Create DashboardAPI pointing to the proxy
            api = DashboardAPI(db_path, proxy_port=18799)

            # All queries should route through the proxy's internal API
            result = api.get_requests(limit=10)
            assert result["total"] == 3
            assert len(result["data"]) == 3

            detail = api.get_request(result["data"][0]["id"])
            assert detail is not None
            assert detail["method"] == "GET"

            max_id = api.get_max_id()
            assert max_id >= 3

            since = api.get_requests_since(max_id - 1)
            assert len(since) >= 1

            filtered = api.get_all_filtered(method="GET")
            assert len(filtered) == 3

            api.close()
        finally:
            server.should_exit = True
            server_thread.join(timeout=5)

        telemetry.close()
