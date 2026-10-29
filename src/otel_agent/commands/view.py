"""otel-agent view subcommand."""

from pathlib import Path
from otel_agent.viewer import (
    format_request,
    format_session_detail,
    format_session_summary,
    query_requests,
    query_session,
    query_sessions,
)


def handle_view(args) -> None:
    """Display logged requests, or agent sessions when asked."""
    db_path = Path(args.db).expanduser()
    session_id = getattr(args, "session", "") or ""
    if session_id:
        detail = query_session(db_path, session_id)
        if detail is None:
            print(f"No session {session_id}.")
            return
        print(format_session_detail(detail))
        return
    if getattr(args, "sessions", False):
        result = query_sessions(db_path, limit=args.limit)
        rows = result.get("data") or []
        if not rows:
            print("No sessions logged yet.")
            return
        for row in rows:
            print(format_session_summary(row))
        return
    rows = query_requests(db_path, args.filter, args.limit)
    if not rows:
        print("No requests logged yet.")
    for r in rows:
        print(format_request(r))
