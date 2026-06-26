from mitmproxy import http
from otel_agent.logger import TelemetryLogger


class TelemetryAddon:
    def __init__(self, logger: TelemetryLogger, upstream_override: str = ""):
        self.logger = logger
        self.upstream_override = upstream_override

    def request(self, flow: http.HTTPFlow):
        """Optionally rewrite the upstream target."""
        if self.upstream_override:
            from urllib.parse import urlparse
            parsed = urlparse(self.upstream_override)
            flow.request.scheme = parsed.scheme
            flow.request.host = parsed.hostname
            if parsed.port:
                flow.request.port = parsed.port
            elif parsed.scheme == "https":
                flow.request.port = 443
            else:
                flow.request.port = 80

    def response(self, flow: http.HTTPFlow):
        """Log every completed request/response."""
        req_body = flow.request.get_content().decode("utf-8", errors="replace")
        resp_body = (
            flow.response.get_content().decode("utf-8", errors="replace")
            if flow.response
            else ""
        )

        latency = 0.0
        if flow.response and flow.response.timestamp_start and flow.response.timestamp_end:
            latency = (flow.response.timestamp_end - flow.response.timestamp_start) * 1000

        self.logger.log_request(
            method=flow.request.method,
            url=flow.request.url,
            request_headers=dict(flow.request.headers),
            request_body=req_body,
            response_status=flow.response.status_code if flow.response else 0,
            response_headers=dict(flow.response.headers) if flow.response else {},
            response_body=resp_body,
            latency_ms=latency,
            upstream=self.upstream_override or flow.request.url,
        )
