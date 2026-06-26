"""otel-agent: LLM API telemetry proxy."""

from importlib.metadata import version, PackageNotFoundError


def get_version() -> str:
    """Return the installed package version."""
    try:
        return version("otel-agent")
    except PackageNotFoundError:
        return "0.0.0 (dev)"


__version__ = get_version()
