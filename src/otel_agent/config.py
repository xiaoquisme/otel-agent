"""otel-agent configuration — provider registry with hot-reload."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from otel_agent.cli_models import MODEL_SOURCES

logger = logging.getLogger(__name__)


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

  # SuperGrok / xAI OAuth — no api_key. Sign in first:
  #   otel-agent auth login
  # Or copy an existing Hermes/Grok grant:
  #   otel-agent auth import-xai
  # Then call model xai/grok-4.6. Tokens live in ~/.otel-agent/auth.json.
  # - name: xai
  #   base_url: https://api.x.ai/v1
  #   auth: xai-oauth
  #   api_format: openai
"""

VALID_API_FORMATS = ("openai", "anthropic")
AUTH_XAI_OAUTH = "xai-oauth"
AUTH_CODEX_OAUTH = "codex-oauth"


@dataclass(frozen=True)
class AuthSource:
    """How a provider's credential is sourced, declared per auth mode.

    Code that would otherwise branch on a specific auth mode (or on a provider
    name) reads these flags instead, so adding a second subscription is a new
    table row rather than a new special case.
    """

    keyless: bool = False
    """api_key may be left empty — the credential comes from elsewhere."""

    vault_backed: bool = False
    """The bearer is resolved from the sidecar vault, not from api_key."""

    entitlement_hint: bool = False
    """Upstream entitlement 403 bodies get the vendor hint appended."""

    responses_only: bool = False
    """The upstream serves only the Responses API surface, so the chat-shaped
    routes must refuse this provider rather than forward and pass on its 404."""


#: Auth mode -> declaration. This table is the only place a subscription mode
#: is named; everything else looks the mode up.
AUTH_SOURCES: dict[str, AuthSource] = {
    "": AuthSource(),
    AUTH_XAI_OAUTH: AuthSource(keyless=True, vault_backed=True, entitlement_hint=True),
    AUTH_CODEX_OAUTH: AuthSource(keyless=True, vault_backed=True, responses_only=True),
}

VALID_AUTH_MODES = tuple(AUTH_SOURCES)


def auth_source(mode: str) -> AuthSource | None:
    """Return the declaration for *mode*, or None when it is not declared."""
    return AUTH_SOURCES.get(mode)


@dataclass
class Provider:
    """A single upstream LLM provider."""

    name: str
    base_url: str
    api_key: str
    api_format: str = "openai"
    auth: str = ""

    models: tuple[str, ...] = ()
    """Model ids this provider offers, declared by the operator.

    Empty — the default — means "not declared", and the provider's catalog is
    discovered from its upstream as before. A non-empty tuple *is* the
    catalog: it is listed without calling upstream, which is what an upstream
    that publishes none (the Codex subscription endpoint) needs. It is never
    guessed or defaulted to a built-in set — an undeclared provider stays
    undeclared rather than acquiring a list this code invented.
    """

    models_from: str = ""
    """Name of a declared source to read this provider's catalog from.

    Empty — the default — discovers the catalog from the upstream's
    ``GET /models``, as before. A declared source reads it from a vendor CLI
    instead, for an upstream that publishes no catalog of its own: the Codex
    subscription endpoint answers ``{"models": []}`` even with a valid
    credential, while the installed CLI knows the real list. The name is
    looked up in ``cli_models.MODEL_SOURCES`` — a vendor is named there and
    nowhere else, so this stays a declaration rather than a special case.

    An unknown or unusable name is dropped at load (see
    ``declared_model_source``) and the provider keeps the upstream behaviour.
    """


def declared_model_source(value: Any) -> str:
    """Normalize a provider row's ``models_from`` into a declared source name.

    Like ``declared_model_ids``, this is operator-authored YAML and a bad value
    must degrade rather than raise: a malformed ``base_url`` makes a row
    unroutable, but a mistyped ``models_from`` only costs the operator the
    declaration, and taking the gateway down over it would be the worse trade.
    So an unknown source, a blank one, or one that is not a string at all
    degrades to "" — the provider's catalog is discovered from its upstream,
    exactly as it was before the field existed.
    """
    if value is None:
        return ""
    name = str(value).strip()
    if not name:
        return ""
    if name not in MODEL_SOURCES:
        logger.warning(
            "Ignoring provider 'models_from': unknown source %r. Declared sources: %s",
            value, ", ".join(repr(s) for s in sorted(MODEL_SOURCES)) or "none",
        )
        return ""
    return name


def declared_model_ids(value: Any) -> tuple[str, ...]:
    """Normalize a provider row's ``models`` value into a tuple of ids.

    The value is operator-authored YAML, so a malformed one must degrade
    rather than raise: a bad ``base_url`` makes the row unroutable, but a bad
    ``models`` only costs the operator the declaration, and taking the whole
    gateway down over it would be a worse trade. A bare string is read as a
    one-entry declaration (``models: gpt-5.6-sol`` is plain YAML shorthand,
    not a typo); entries that are not usable ids are dropped with a warning;
    a value that is neither a string nor a list degrades to "not declared",
    leaving the provider exactly as it behaves without the field.
    """
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        if value is not None:
            logger.warning(
                "Ignoring provider 'models': expected a list of model ids, got %r", value
            )
        return ()

    ids: dict[str, None] = {}
    for entry in value:
        if not isinstance(entry, str):
            logger.warning("Ignoring model id %r: not a string", entry)
            continue
        model_id = entry.strip()
        if not model_id:
            logger.warning("Ignoring an empty model id in provider 'models'")
            continue
        ids[model_id] = None  # insertion-ordered, so this de-duplicates
    return tuple(ids)


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
        self._storage: str = "sqlite"
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
                auth=str(item.get("auth", "")).strip(),
                models=declared_model_ids(item.get("models")),
                models_from=declared_model_source(item.get("models_from")),
            )

        self._providers = providers
        self._log_request_body = bool(data.get("log_request_body", True))
        self._storage = str(data.get("storage", "sqlite")).strip()
        self._validate()

    def _validate(self) -> None:
        for name, provider in self._providers.items():
            if not provider.base_url:
                raise ValueError(
                    f"Provider '{name}' must have a base_url. "
                    f"Add a valid URL to the provider config."
                )
            source = auth_source(provider.auth)
            if source is None:
                raise ValueError(
                    f"Provider '{name}' has invalid auth '{provider.auth}'. "
                    f"Must be one of: {', '.join(repr(v) for v in VALID_AUTH_MODES if v) or 'empty'}."
                )
            if not provider.api_key and not source.keyless:
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


def upsert_provider(path: Path, fields: dict) -> None:
    """Insert or update a provider row in a YAML config file."""
    data: dict = {}
    if path.exists():
        with open(path) as f:
            loaded = yaml.safe_load(f) or {}
        if isinstance(loaded, dict):
            data = loaded
    raw = data.get("providers")
    providers = raw if isinstance(raw, list) else []
    name = str(fields.get("name", "")).strip()
    updated = False
    new_list = []
    for item in providers:
        if isinstance(item, dict) and str(item.get("name", "")).strip() == name:
            merged = dict(item)
            merged.update(fields)
            new_list.append(merged)
            updated = True
        else:
            new_list.append(item)
    if not updated:
        new_list.append(dict(fields))
    data["providers"] = new_list
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False)
