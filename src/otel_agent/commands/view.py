"""otel-agent view subcommand."""

from pathlib import Path
from otel_agent.viewer import query_requests, format_request


def handle_view(args) -> None:
    """Display logged requests."""
    rows = query_requests(Path(args.db), args.filter, args.limit)
    if not rows:
        print("No requests logged yet.")
    for r in rows:
        print(format_request(r))
