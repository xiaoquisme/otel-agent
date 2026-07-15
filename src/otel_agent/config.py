"""otel-agent configuration — provider registry with hot-reload."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


DEFAULT_CONFIG = """\\
# otel-agent configuration
# Docs: https://github.com/xiaoquisme/otel-agent
#
# Providers are referenced by model name prefix:
#   openai/gpt-5.4           -> routes to the 'openai' provider
#   openrouter/openai/gpt-5.4 -> routes to the 'openrouter' provider
#   xiaomi/mimo-v-2.5         -> routes to the 'xiaomi' provider

providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: YOUR_API_KEY
    api_format: openai
    # Optional capability fields for auto-routing:
    # cost_per_1k_input: 0.0025
    # cost_per_1k_output: 0.01
    # max_context: 128000
    # rate_limit_rpm: 500
    # tiers: [simple, medium, complex, reasoning]

  # - name: openrouter
  #   base_url: https://openrouter.ai/api/v1
  #   api_key: YOUR_OPENROUTER_KEY
  #   api_format: openai

  # - name: xiaomi
  #   base_url: https://api.xiaomi.com/v1
  #   api_key: YOUR_XIAOMI_KEY
  #   api_format: openai

  # - name: anthropic
  #   base_url: https://api.anthropic.com
  #   api_key: YOUR_ANTHROPIC_KEY
  #   api_format: anthropic

# Auto-routing configuration (optional)
# auto_routing:
#   circuit_breaker_threshold: 5
#   circuit_breaker_cooldown: 60
#   session_ttl_minutes: 30
"""

VALID_API_FORMATS = ("openai", "anthropic")
VALID_TIERS = ("simple", "medium", "complex", "reasoning")


@dataclass
class Provider:
    """A single upstream LLM provider with optional routing capabilities."""

    name: str
    base_url: str
    api_key: str
    api_format: str = "openai"
    # Auto-routing capability fields
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    max_context: int = 0
    rate_limit_rpm: int = 0
    tiers: list[str] = field(default_factory=lambda: list(VALID_TIERS))
    default_model: str = ""

    @property
    def supports_auto_routing(self) -> bool:
        """Whether this provider has capability metadata for auto-routing."""
        return bool(self.tiers) and (self.cost_per_1k_input > 0 or self.cost_per_1k_output > 0)

    def cost_per_token(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost for a given token usage."""
        return (input_tokens * self.cost_per_1k_input + output_tokens * self.cost_per_1k_output) / 1000


class Config:
    """Loads and hot-reloads ~/.otel-agent/config.yaml.

    Providers are stored as a flat list. Routing is model-name-driven:
    the first segment of the model string is the provider name.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._mtime: float = 0
        self._providers: dict[str, Provider] = {}
        self._log_request_body: bool = True
        self._storage: str = "duckdb"
        self._auto_routing: dict = {}
        self._reload()

    def _reload(self) -> None:
        if not self.path.exists():
            self._providers = {}
            return

        stat = self.path.stat().st_mtime
        if stat == self._mtime:
            return
        self._mtime = stat

        with open(self.path) as f:
            data = yaml.safe_load(f) or {}

        providers: dict[str, Provider] = {}
        raw = data.get("providers") or []
        if not isinstance(raw, list):
            return

        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue

            # Parse tiers
            raw_tiers = item.get("tiers")
            if raw_tiers is None:
                tiers = list(VALID_TIERS)
            elif isinstance(raw_tiers, list):
                tiers = [str(t).lower().strip() for t in raw_tiers]
                for t in tiers:
                    if t not in VALID_TIERS:
                        raise ValueError(
                            f"Provider '{name}' has invalid tier '{t}'. "
                            f"Must be one of: {', '.join(VALID_TIERS)}"
                        )
            else:
                tiers = list(VALID_TIERS)

            providers[name] = Provider(
                name=name,
                base_url=str(item.get("base_url", "")),
                api_key=str(item.get("api_key", "")),
                api_format=str(item.get("api_format", "openai")),
                cost_per_1k_input=float(item.get("cost_per_1k_input", 0)),
                cost_per_1k_output=float(item.get("cost_per_1k_output", 0)),
                max_context=int(item.get("max_context", 0)),
                rate_limit_rpm=int(item.get("rate_limit_rpm", 0)),
                tiers=tiers,
                default_model=str(item.get("default_model", "")),
            )

        self._providers = providers
        self._log_request_body = bool(data.get("log_request_body", True))
        self._storage = str(data.get("storage", "duckdb")).strip()
        self._auto_routing = data.get("auto_routing") or {}
        self._validate()

    def _validate(self) -> None:
        for name, provider in self._providers.items():
            if not provider.base_url:
                raise ValueError(
                    f"Provider '{name}' must have a base_url. "
                    f"Add a valid URL to the provider config."
                )
            if not provider.api_key:
                raise ValueError(
                    f"Provider '{name}' must have an api_key. "
                    f"Add a valid API key to the provider config."
                )
            if provider.api_format not in VALID_API_FORMATS:
                raise ValueError(
                    f"Provider '{name}' has invalid api_format '{provider.api_format}'. "
                    f"Must be one of: {', '.join(VALID_API_FORMATS)}"
                )

    @property
    def providers(self) -> dict[str, Provider]:
        self._reload()
        return dict(self._providers)

    def get_provider(self, name: str) -> Provider | None:
        self._reload()
        return self._providers.get(name)

    def get_providers_for_tier(self, tier: str) -> list[Provider]:
        """Return providers that support the given complexity tier."""
        self._reload()
        return [p for p in self._providers.values() if tier in p.tiers]

    @property
    def auto_routing(self) -> dict:
        self._reload()
        return dict(self._auto_routing)

    @property
    def routes(self) -> list[dict[str, str]]:
        self._reload()
        result = []
        for name, provider in sorted(self._providers.items()):
            result.append({
                "provider": name,
                "base_url": provider.base_url,
                "api_format": provider.api_format,
            })
        return result

    @property
    def log_request_body(self) -> bool:
        self._reload()
        return self._log_request_body

    @property
    def storage(self) -> str:
        self._reload()
        return self._storage
