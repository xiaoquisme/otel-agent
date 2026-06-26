from urllib.parse import urlparse
from mitmproxy import http
from otel_agent.logger import TelemetryLogger

# Provider auth header mapping
PROVIDER_AUTH = {
    "anthropic.com": "x-api-key",
}
DEFAULT_AUTH_HEADER = "Authorization"
DEFAULT_AUTH_PREFIX = "Bearer "


class TelemetryAddon:
    def __init__(
        self,
        logger: TelemetryLogger,
        upstream_override: str = "",
        api_keys: dict | None = None,
    ):
        self.logger = logger
        self.upstream_override = upstream_override
        # {host_pattern: api_key}  e.g. {"openai.com": "sk-xxx", "anthropic.com": "sk-ant-xxx"}
        self.api_keys = api_keys or {}

    def _match_key(self, host: str) -> str | None:
        """Return the API key whose pattern matches the given host."""
        for pattern, key in self.api_keys.items():
            if pattern in host:
                return key
        return None

    def _inject_auth(self, flow: http.HTTPFlow, key: str):
        """Inject the appropriate auth header based on the target host."""
        host = flow.request.host
        header = DEFAULT_AUTH_HEADER
        for provider, hdr in PROVIDER_AUTH.items():
            if provider in host:
                header = hdr
                break

        if header == DEFAULT_AUTH_HEADER:
            flow.request.headers[header] = DEFAULT_AUTH_PREFIX + key
        else:
            flow.request.headers[header] = key

    def request(self, flow: http.HTTPFlow):
        """Rewrite upstream target and inject API key."""
        if self.upstream_override:
            parsed = urlparse(self.upstream_override)
            flow.request.scheme = parsed.scheme
            flow.request.host = parsed.hostname
            if parsed.port:
                flow.request.port = parsed.port
            elif parsed.scheme == "https":
                flow.request.port = 443
            else:
                flow.request.port = 80

        # Inject API key (matches against the final host after rewrite)
        key = self._match_key(flow.request.host)
        if key:
            self._inject_auth(flow, key)

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
