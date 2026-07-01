from urllib.parse import urlparse
import logging
from mitmproxy import http
from otel_agent.config import Config
from otel_agent.logger import TelemetryLogger
from otel_agent.rotator import KeyRotator

logger = logging.getLogger(__name__)

# Auth header by API type
AUTH_HEADERS = {
    "openai": ("Authorization", "Bearer "),
    "anthropic": ("x-api-key", ""),
}


def _format_connection_error(provider_name: str, base_url: str, error: Exception) -> str:
    """Format a connection error with actionable diagnostics."""
    error_type = type(error).__name__
    error_msg = str(error)

    # Determine specific failure reason
    if "Connection refused" in error_msg or isinstance(error, ConnectionRefusedError):
        reason = "Connection refused — server is not accepting connections"
        troubleshooting = [
            f"Is the server running at {base_url}?",
            "Is the port correct?",
            "Check firewall settings",
        ]
    elif "Name or service not known" in error_msg or "getaddrinfo failed" in error_msg:
        reason = "DNS resolution failed — hostname could not be resolved"
        troubleshooting = [
            "Check if the hostname in the URL is correct",
            "Verify DNS settings",
            "Try using an IP address instead of hostname",
        ]
    elif "timed out" in error_msg.lower() or isinstance(error, TimeoutError):
        reason = "Connection timed out — server did not respond in time"
        troubleshooting = [
            f"Is the server running at {base_url}?",
            "Check network connectivity",
            "Increase timeout settings if needed",
        ]
    elif "Network is unreachable" in error_msg:
        reason = "Network unreachable — no route to host"
        troubleshooting = [
            "Check network connectivity",
            "Verify VPN/proxy settings",
            "Check if the host is accessible from this machine",
        ]
    else:
        reason = f"{error_type}: {error_msg}"
        troubleshooting = [
            f"Verify the server is running at {base_url}",
            "Check network connectivity",
            "Verify the URL in your config: ~/.otel-agent/config.yaml",
        ]

    lines = [
        f"❌ Connection failed to provider '{provider_name}'",
        f"   🌐 Endpoint: {base_url}",
        f"   🔍 Error: {reason}",
        "",
        "   Troubleshooting:",
    ]
    for step in troubleshooting:
        lines.append(f"   • {step}")

    return "\n".join(lines)


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
        """Route request by provider path and inject API key."""
        path = flow.request.path

        if path.startswith("/openai"):
            provider_type = "openai"
            prefix = "/openai"
        elif path.startswith("/anthropic"):
            provider_type = "anthropic"
            prefix = "/anthropic"
        else:
            provider_type = None

        if provider_type:
            provider = self.config.get_active_provider(provider_type)
            if not provider:
                available_types = list(self.config.provider_types.keys())
                raise ValueError(
                    f"No active provider configured for type '{provider_type}'. "
                    f"Configured types: {', '.join(available_types) or 'none'}. "
                    f"Check your config at ~/.otel-agent/config.yaml"
                )

            flow.request.path = self._strip_prefix(path, prefix)
            try:
                self._rewrite_upstream(flow, provider.base_url)
            except Exception as e:
                error_msg = _format_connection_error(provider.name, provider.base_url, e)
                logger.error(error_msg)
                raise ValueError(error_msg) from e

            key = self.rotator.next_by_api_key(provider_type)
            if key:
                self._inject_auth(flow, key, provider_type)
            return

        # Upstream override from CLI arg takes priority for non-standard paths
        if self.upstream_override:
            self._rewrite_upstream(flow, self.upstream_override)
            key = self.rotator.next_by_api_key("")
            if key:
                self._inject_auth(flow, key, "openai")

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
