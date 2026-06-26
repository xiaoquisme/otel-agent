"""otel-agent CLI dispatcher."""

import argparse
import sys
from pathlib import Path

from otel_agent import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the main argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="otel-agent",
        description="LLM API telemetry proxy — intercept, log, redirect.",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s {__version__}",
    )

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # --- init ---
    init_p = sub.add_parser("init", help="Create default config file")
    init_p.add_argument(
        "-c", "--config", type=str,
        default="~/.otel-agent/config.yaml",
        help="Config file path",
    )

    # --- proxy ---
    proxy_p = sub.add_parser("proxy", help="Start the MITM proxy")
    proxy_p.add_argument(
        "-p", "--port", type=int, default=8080,
        help="Proxy listen port (default: 8080)",
    )
    proxy_p.add_argument(
        "-u", "--upstream", type=str, default="",
        help="Override upstream target (overrides config base_url)",
    )
    proxy_p.add_argument(
        "-d", "--db", type=str, default="telemetry.db",
        help="SQLite database path (default: telemetry.db)",
    )
    proxy_p.add_argument(
        "-c", "--config", type=str,
        default="~/.otel-agent/config.yaml",
        help="Config file path",
    )

    # --- view ---
    view_p = sub.add_parser("view", help="View logged requests")
    view_p.add_argument(
        "-d", "--db", type=str, default="telemetry.db",
        help="SQLite database path",
    )
    view_p.add_argument(
        "-f", "--filter", type=str, default="",
        help="Filter by upstream (substring match)",
    )
    view_p.add_argument(
        "-n", "--limit", type=int, default=20,
        help="Max rows to display (default: 20)",
    )

    # --- config ---
    config_p = sub.add_parser("config", help="Manage configuration")
    config_p.add_argument(
        "-c", "--config", type=str,
        default="~/.otel-agent/config.yaml",
        help="Config file path",
    )
    config_p.add_argument(
        "config_action", nargs="?", default="path",
        choices=["path", "show", "edit"],
        help="Action: path (print path), show (display masked), edit (open in editor)",
    )

    # --- doctor ---
    doctor_p = sub.add_parser("doctor", help="Check installation health")
    doctor_p.add_argument(
        "-c", "--config", type=str,
        default="~/.otel-agent/config.yaml",
        help="Config file path",
    )
    doctor_p.add_argument(
        "-p", "--port", type=int, default=8080,
        help="Port to check (default: 8080)",
    )

    # --- routes ---
    routes_p = sub.add_parser("routes", help="Display routing table")
    routes_p.add_argument(
        "-c", "--config", type=str,
        default="~/.otel-agent/config.yaml",
        help="Config file path",
    )

    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "init":
        from otel_agent.commands.init import handle_init
        handle_init(args)
    elif args.command == "proxy":
        from otel_agent.commands.proxy import handle_proxy
        handle_proxy(args)
    elif args.command == "view":
        from otel_agent.commands.view import handle_view
        handle_view(args)
    elif args.command == "config":
        from otel_agent.commands.config_cmd import handle_config
        handle_config(args)
    elif args.command == "doctor":
        from otel_agent.commands.doctor import handle_doctor
        handle_doctor(args)
    elif args.command == "routes":
        from otel_agent.commands.routes import handle_routes
        handle_routes(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
