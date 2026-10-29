"""CLI viewer — reads request logs from the storage backend."""

from __future__ import annotations

from pathlib import Path

from otel_agent.storage import create_storage


def query_requests(db_path: Path, upstream_filter: str = "", limit: int = 50) -> list:
    storage = create_storage("sqlite", db_path, read_only=True)
    try:
        if upstream_filter:
            results = storage.get_all_filtered(search=upstream_filter)
        else:
            results = storage.get_all_filtered()
        return results[:limit]
    finally:
        storage.close()


def query_sessions(db_path: Path, limit: int = 20) -> dict:
    """Recent agent sessions from the telemetry database."""
    storage = create_storage("sqlite", db_path, read_only=True)
    try:
        return storage.list_sessions(limit=limit, offset=0)
    finally:
        storage.close()


def query_session(db_path: Path, session_id: str) -> dict | None:
    """One session trajectory, or None when that id was never logged."""
    storage = create_storage("sqlite", db_path, read_only=True)
    try:
        return storage.get_session(session_id)
    finally:
        storage.close()


def format_session_summary(row: dict) -> str:
    """One line for ``otel-agent view --sessions``."""
    models = ", ".join(row.get("models") or []) or "—"
    return (
        f"{row['session_id']}  requests={row['request_count']}  "
        f"tokens={row['total_tokens']}  errors={row['error_count']}  "
        f"{row['first_timestamp']} → {row['last_timestamp']}  models={models}"
    )


def format_session_detail(detail: dict) -> str:
    """Multi-line trajectory for ``otel-agent view --session``."""
    lines = [
        f"session {detail['session_id']}  {detail['request_count']} requests  "
        f"{detail['total_tokens']} tokens  {detail['total_latency_ms']:.0f}ms"
    ]
    last_turn = None
    for index, step in enumerate(detail.get("steps") or [], start=1):
        turn = step.get("turn_index")
        if turn and turn != last_turn:
            label = step.get("turn_label") or ""
            lines.append(f"turn {turn}" + (f"  {label}" if label else ""))
            last_turn = turn
        flags = ",".join(step.get("flags") or [])
        flag_text = f"  [{flags}]" if flags else ""
        step_label = step.get("session_step")
        step_text = f"  step={step_label}" if step_label else ""
        latency = step.get("latency_ms")
        latency_text = f"{latency:.0f}ms" if isinstance(latency, (int, float)) else "—"
        lines.append(
            f"  {index}  {step['timestamp']}  {step['method']} {step['url']}  "
            f"{step.get('response_status')}  {latency_text}  "
            f"tokens={step.get('total_tokens')}  cum={step.get('cumulative_total_tokens')}"
            f"{step_text}{flag_text}"
        )
    findings = detail.get("findings") or []
    if findings:
        lines.append(f"findings ({len(findings)}):")
        for finding in findings:
            ids = ",".join(str(request_id) for request_id in finding.get("request_ids") or [])
            tokens = finding.get("tokens_involved")
            token_text = f"  tokens={tokens}" if tokens is not None else ""
            lines.append(
                f"  [{finding.get('severity')}] {finding.get('rule_id')}  "
                f"requests={ids}{token_text}  {finding.get('message')}"
            )
    return "\n".join(lines)


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
