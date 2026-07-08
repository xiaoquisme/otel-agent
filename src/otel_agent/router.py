"""Model-name-based routing — parse model strings and resolve providers."""

from __future__ import annotations

from otel_agent.config import Config, Provider


def parse_model(model: str) -> tuple[str, str]:
    """Parse a model string into (provider_name, upstream_model).

    Examples:
        'openai/gpt-5.4'            -> ('openai', 'gpt-5.4')
        'openrouter/openai/gpt-5.4' -> ('openrouter', 'openai/gpt-5.4')
        'xiaomi/mimo-v-2.5'         -> ('xiaomi', 'mimo-v-2.5')

    Raises ValueError if the model string has no '/' separator.
    """
    parts = model.split("/", 1)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"Model must include provider prefix (e.g., 'openai/gpt-5.4'). "
            f"Got: '{model}'"
        )
    return parts[0], parts[1]


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
