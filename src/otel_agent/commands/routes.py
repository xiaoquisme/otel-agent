"otel-agent routes subcommand."

from pathlib import Path
from otel_agent.config import Config


def handle_routes(args) -> None:
    """Display the routing table."""
    config_path = Path(args.config).expanduser()
    config = Config(config_path)

    routes = config.routes
    if not routes:
        print("No providers configured. Run: otel-agent init")
        return

    # Header
    print(f"{'Path Prefix':<16} {'Provider':<16} {'Type':<12} {'Upstream'}")
    print(f"{'-'*14:<16} {'-'*8:<16} {'-'*4:<12} {'-'*30}")

    for r in routes:
        print(f"{r['prefix']:<16} {r['provider']:<16} {r['type']:<12} {r['base_url']}")
