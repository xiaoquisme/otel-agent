"""otel-agent dashboard subcommand."""

from __future__ import annotations

from pathlib import Path


def handle_dashboard(args) -> None:
    """Start the web dashboard server."""
    from otel_agent.dashboard.server import DashboardServer

    db_path = Path(args.db).expanduser()
    port = args.port

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Start the proxy first: otel-agent proxy")
        return

    server = DashboardServer(db_path=db_path, port=port)
    print(f"Dashboard running at http://localhost:{port}")
    print(f"Database: {db_path}")
    print("Ctrl+C to stop\n")
    server.serve()
