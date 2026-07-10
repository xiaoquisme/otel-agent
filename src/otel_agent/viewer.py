"""CLI viewer — reads request logs from the storage backend."""

from __future__ import annotations

from pathlib import Path

from otel_agent.storage import create_storage


def query_requests(db_path: Path, upstream_filter: str = "", limit: int = 50) -> list:
    storage = create_storage("duckdb", db_path, read_only=True)
    try:
        if upstream_filter:
            results = storage.get_all_filtered(search=upstream_filter)
        else:
            results = storage.get_all_filtered()
        return results[:limit]
    finally:
        storage.close()


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
