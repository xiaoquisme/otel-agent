"""Dashboard HTTP server with routing."""

from __future__ import annotations

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs

from otel_agent.dashboard.api import DashboardAPI


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the dashboard."""

    api: DashboardAPI
    html_content: str = ""

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default access logs."""
        pass

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/":
            self._serve_html()
        elif path == "/api/requests":
            self._serve_requests(params)
        elif path.startswith("/api/requests/"):
            self._serve_request_detail(path)
        elif path == "/api/events":
            self._serve_sse()
        elif path == "/api/export":
            self._serve_export(params)
        elif path == "/api/cache/clear":
            self._serve_cache_clear()
        else:
            self._serve_404()

    def _serve_html(self) -> None:
        content = self.html_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_requests(self, params: dict) -> None:
        search = params.get("search", [""])[0]
        method = params.get("method", [""])[0]
        status_str = params.get("status", ["0"])[0]
        cursor_str = params.get("cursor", ["0"])[0]
        limit_str = params.get("limit", ["50"])[0]

        try:
            status = int(status_str)
            cursor = int(cursor_str)
            limit = min(int(limit_str), 500)
        except ValueError:
            self._serve_json({"error": "Invalid parameter"}, 400)
            return

        result = self.api.get_requests(
            search=search, method=method, status=status,
            cursor=max(cursor, 0), limit=max(limit, 1),
        )
        self._serve_json(result)

    def _serve_request_detail(self, path: str) -> None:
        try:
            request_id = int(path.split("/")[-1])
        except ValueError:
            self._serve_json({"error": "Invalid request ID"}, 400)
            return

        result = self.api.get_request(request_id)
        if result is None:
            self._serve_json({"error": "Request not found"}, 404)
            return
        self._serve_json(result)

    def _serve_sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        last_id = self.api.get_max_id()
        try:
            while True:
                new_requests = self.api.get_requests_since(last_id)
                for req in new_requests:
                    data = json.dumps(req)
                    self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    last_id = req["id"]
                import time
                time.sleep(1)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _serve_export(self, params: dict) -> None:
        fmt = params.get("format", ["csv"])[0]
        search = params.get("search", [""])[0]
        method = params.get("method", [""])[0]
        status_str = params.get("status", ["0"])[0]

        try:
            status = int(status_str)
        except ValueError:
            status = 0

        rows = self.api.get_all_filtered(search=search, method=method, status=status)

        if fmt == "json":
            content = json.dumps(rows, indent=2).encode("utf-8")
            content_type = "application/json"
            filename = "requests.json"
        else:
            import csv
            import io
            output = io.StringIO()
            if rows:
                writer = csv.DictWriter(output, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            content = output.getvalue().encode("utf-8")
            content_type = "text/csv"
            filename = "requests.csv"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_json(self, data: Any, status: int = 200) -> None:
        content = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_404(self) -> None:
        self.send_response(404)
        self.end_headers()

    def _serve_cache_clear(self) -> None:
        self.api.clear_cache()
        self._serve_json({"status": "ok"})


class DashboardServer:
    """Lightweight HTTP server for the dashboard."""

    def __init__(self, db_path: Path, port: int = 9090):
        self.db_path = db_path
        self.port = port
        self.api = DashboardAPI(db_path)
        self.html_content = self._load_html()

    def _load_html(self) -> str:
        html_path = Path(__file__).parent / "index.html"
        if html_path.exists():
            return html_path.read_text()
        return "<h1>Dashboard</h1><p>index.html not found</p>"

    def serve(self) -> None:
        handler = type("Handler", (DashboardHandler,), {
            "api": self.api,
            "html_content": self.html_content,
        })
        server = HTTPServer(("0.0.0.0", self.port), handler)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
