"""otel-agent routes subcommand."""

from pathlib import Path
from otel_agent.config import Config


def handle_routes(args) -> None:
    """Display the provider routing table."""
    config_path = Path(args.config).expanduser()
    config = Config(config_path)

    routes = config.routes
    if not routes:
        print("No providers configured. Run: otel-agent init")
        return

    print(f"{'Provider':<16} {'API Format':<12} {'Upstream'}")
    print(f"{'-'*14:<16} {'-'*10:<12} {'-'*40}")

    for r in routes:
        print(f"{r['provider']:<16} {r['api_format']:<12} {r['base_url']}")

    print(f"\nUsage: set model='<provider>/<model>' in your request.")
    print(f"  e.g., model='openai/gpt-5.4' routes to the 'openai' provider")
    print(f"  e.g., model='openrouter/openai/gpt-5.4' routes to 'openrouter'")
