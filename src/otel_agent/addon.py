from urllib.parse import urlparse
from mitmproxy import http
from otel_agent.config import Config
from otel_agent.logger import TelemetryLogger
from otel_agent.rotator import KeyRotator

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
        config: Config,
        rotator: KeyRotator,
        upstream_override: str = "",
    ):
        self.logger = logger
        self.config = config
        self.rotator = rotator
        self.upstream_override = upstream_override

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
        # Upstream override from CLI arg
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

        # Check if config has a provider with base_url for this host
        provider = self.config.get_provider(flow.request.host)
        if provider and provider.base_url and not self.upstream_override:
            parsed = urlparse(provider.base_url)
            flow.request.scheme = parsed.scheme
            flow.request.host = parsed.hostname
            if parsed.port:
                flow.request.port = parsed.port
            elif parsed.scheme == "https":
                flow.request.port = 443
            else:
                flow.request.port = 80

        # Inject API key via rotator
        key = self.rotator.next(flow.request.host)
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
