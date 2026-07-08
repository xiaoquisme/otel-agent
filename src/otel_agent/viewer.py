import sqlite3
from pathlib import Path


def query_requests(db_path: Path, upstream_filter: str = "", limit: int = 50) -> list:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    if upstream_filter:
        rows = conn.execute(
            "SELECT * FROM requests WHERE upstream LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{upstream_filter}%", limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM requests ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def format_request(row: dict) -> str:
    resp_hdrs = row.get("response_headers", "")
    if isinstance(resp_hdrs, dict):
        resp_hdrs = str(resp_hdrs)
    return (
        f"[{row['id']}] {row['timestamp']} | {row['method']} {row['url']}\n"
        f"  upstream: {row.get('upstream', 'N/A')}\n"
        f"  status: {row.get('response_status', '?')} | latency: {row.get('latency_ms', 0):.0f}ms\n"
        f"  request: {row.get('request_body', '')[:200]}\n"
        f"  headers: {resp_hdrs[:200]}"
    )
