"""Model-name-based routing — parse model strings and resolve providers."""

from __future__ import annotations

import re

from otel_agent.config import Config, Provider

# Matches context-window suffixes like [500k], [1m], [128k] appended by
# gateway clients (e.g. Claude Code) to hint at the desired context length.
# Upstream APIs don't recognise this notation and reject the model name.
_CTX_SUFFIX_RE = re.compile(r"\[.*\]$")


def parse_model(model: str) -> tuple[str, str]:
    """Parse a model string into (provider_name, upstream_model).

    Strips trailing ``[...]`` context-window hints (e.g. ``[500k]``) that
    gateway clients append but upstream APIs don't understand.

    Examples:
        'openai/gpt-5.4'            -> ('openai', 'gpt-5.4')
        'openrouter/openai/gpt-5.4' -> ('openrouter', 'openai/gpt-5.4')
        'xiaomi/mimo-v-2.5'         -> ('xiaomi', 'mimo-v-2.5')
        'xai/grok-4.6[500k]'        -> ('xai', 'grok-4.6')

    Raises ValueError if the model string has no '/' separator.
    """
    parts = model.split("/", 1)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"Model must include provider prefix (e.g., 'openai/gpt-5.4'). "
            f"Got: '{model}'"
        )
    return parts[0], _CTX_SUFFIX_RE.sub("", parts[1])


def resolve_provider(provider_name: str, config: Config) -> Provider:
    """Look up a provider by name from config.

    Raises ValueError if the provider is not found.
    """
    provider = config.get_provider(provider_name)
    if provider is None:
        available = list(config.providers.keys())
        raise ValueError(
            f"Unknown provider '{provider_name}'. "
            f"Configured providers: {', '.join(available) or 'none'}. "
            f"Add the provider to ~/.otel-agent/config.yaml"
        )
    return provider
