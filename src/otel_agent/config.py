"""otel-agent configuration — provider registry with hot-reload."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


DEFAULT_CONFIG = """\
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
"""

VALID_API_FORMATS = ("openai", "anthropic")


@dataclass
class Provider:
    """A single upstream LLM provider."""

    name: str
    base_url: str
    api_key: str
    api_format: str = "openai"


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
            providers[name] = Provider(
                name=name,
                base_url=str(item.get("base_url", "")),
                api_key=str(item.get("api_key", "")),
                api_format=str(item.get("api_format", "openai")),
            )

        self._providers = providers
        self._log_request_body = bool(data.get("log_request_body", True))
        self._storage = str(data.get("storage", "duckdb")).strip()
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
