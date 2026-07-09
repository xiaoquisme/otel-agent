"""CLI viewer — reads request logs from DuckDB."""

from __future__ import annotations

from pathlib import Path

from otel_agent.db_compat import get_connection


def query_requests(db_path: Path, upstream_filter: str = "", limit: int = 50) -> list:
    conn = get_connection(db_path, read_only=True)

    if upstream_filter:
        result = conn.execute(
            "SELECT * FROM requests WHERE upstream LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{upstream_filter}%", limit),
        )
    else:
        result = conn.execute(
            "SELECT * FROM requests ORDER BY id DESC LIMIT ?", (limit,)
        )

    rows = result.fetchall()
    columns = [desc[0] for desc in result.description] if result.description else []
    conn.close()
    return [dict(zip(columns, r)) for r in rows]


def format_request(row: dict) -> str:
    resp_hdrs = row.get("response_headers") or ""
    if isinstance(resp_hdrs, dict):
        resp_hdrs = str(resp_hdrs)
    req_body = (row.get("request_body") or "")[:200]
    return (
        f"[{row['id']}] {row['timestamp']} | {row['method']} {row['url']}\n"
        f"  upstream: {row.get('upstream') or 'N/A'}\n"
        f"  status: {row.get('response_status', '?')} | latency: {row.get('latency_ms', 0):.0f}ms\n"
        f"  request: {req_body}\n"
        f"  headers: {resp_hdrs[:200]}"
    )
