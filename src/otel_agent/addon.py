from urllib.parse import urlparse
from mitmproxy import http
from otel_agent.config import Config
from otel_agent.logger import TelemetryLogger
from otel_agent.rotator import KeyRotator

# Auth header by API type
AUTH_HEADERS = {
    "openai": ("Authorization", "Bearer "),
    "anthropic": ("x-api-key", ""),
}


class TelemetryAddon:
    def __init__(
        self,
        logger: TelemetryLogger,
        config: Config,
        rotator: KeyRotator,
        upstream_override: str = "",
    ):
        self.logger = logger
        self.config = config
        self.rotator = rotator
        self.upstream_override = upstream_override

    def _inject_auth(self, flow: http.HTTPFlow, key: str, api_type: str = "openai"):
        """Inject auth header based on API type."""
        header, prefix = AUTH_HEADERS.get(api_type, AUTH_HEADERS["openai"])
        flow.request.headers[header] = prefix + key

    @staticmethod
    def _strip_prefix(path: str, prefix: str) -> str:
        """Strip prefix from request path. /openai/v1/chat -> /v1/chat."""
        if path == prefix:
            return "/"
        if path.startswith(prefix + "/"):
            return path[len(prefix):]
        return path

    def _rewrite_upstream(self, flow: http.HTTPFlow, base_url: str):
        """Rewrite request host/scheme/port to upstream base_url."""
        parsed = urlparse(base_url)
        flow.request.scheme = parsed.scheme
        flow.request.host = parsed.hostname
        if parsed.port:
            flow.request.port = parsed.port
        elif parsed.scheme == "https":
            flow.request.port = 443
        else:
            flow.request.port = 80

    def request(self, flow: http.HTTPFlow):
        """Route request by path prefix and inject API key."""
        # Upstream override from CLI arg takes priority
        if self.upstream_override:
            self._rewrite_upstream(flow, self.upstream_override)
            key = self.rotator.next(flow.request.host)
            if key:
                self._inject_auth(flow, key, "openai")
            return

        # Path-based routing: extract first path segment
        path = flow.request.path
        provider = self.config.get_provider_by_prefix(path)

        if provider:
            # Strip prefix and rewrite upstream
            flow.request.path = self._strip_prefix(path, provider.prefix)
            self._rewrite_upstream(flow, provider.base_url)

            # Inject auth by API type
            key = self.rotator.next(provider.name)
            if key:
                self._inject_auth(flow, key, provider.type)
            return

        # Fallback: host-based matching (existing behavior)
        provider = self.config.get_provider(flow.request.host)
        if provider and provider.base_url:
            self._rewrite_upstream(flow, provider.base_url)
            key = self.rotator.next(provider.name)
            if key:
                self._inject_auth(flow, key, provider.type)

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
