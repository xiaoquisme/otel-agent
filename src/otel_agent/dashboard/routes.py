"""FastAPI router for the otel-agent dashboard.

Provides the dashboard JSON endpoints:
  GET /              — index.html (served by server.py mount)
  GET /api/requests  — paginated request list
  GET /api/requests/{id} — single request detail with structured messages
  GET /api/requests/{id}/download — pretty-printed JSON attachment
  GET /api/export    — CSV/JSON export
  GET /api/cache/clear — clear the COUNT cache
  GET /api/usage     — usage summary for a time range
  GET /api/usage/series — token totals bucketed across a time range
  GET /api/sessions  — recent agent sessions with rollups
  GET /api/sessions/{session_id} — one session as a chronological trajectory
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response

from otel_agent.dashboard.api import DashboardAPI
from otel_agent.sessions import MAX_SESSION_ID_LEN, clean_session_label
from otel_agent.usage_series import USAGE_BUCKETS

router = APIRouter(prefix="/api")

# Module-level singleton; set by create_dashboard_app() or mount_dashboard().
_api: DashboardAPI | None = None


def set_api(api: DashboardAPI) -> None:
    """Set the module-level DashboardAPI instance used by route handlers."""
    global _api
    _api = api


def get_api() -> DashboardAPI:
    """Return the current DashboardAPI instance (raises if not set)."""
    if _api is None:
        raise RuntimeError("DashboardAPI not initialised — call set_api() first")
    return _api


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("/requests")
def get_requests(
    search: str = Query(""),
    method: str = Query(""),
    status: int = Query(0),
    cursor: int = Query(0),
    limit: int = Query(50),
) -> dict:
    """Paginated request list."""
    api = get_api()
    limit = min(max(limit, 1), 500)
    cursor = max(cursor, 0)
    return api.get_requests(
        search=search, method=method, status=status,
        cursor=cursor, limit=limit,
    )


@router.get("/requests/{request_id}")
def get_request_detail(request_id: int) -> JSONResponse:
    """Single request detail with structured messages for frontend rendering."""
    api = get_api()
    result = api.get_structured_request(request_id)
    if result is None:
        return JSONResponse({"error": "Request not found"}, status_code=404)
    return JSONResponse(result)


def _maybe_parse_json(value: Any) -> Any:
    """Parse JSON text in place; leave non-JSON strings and other types as-is."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def downloadable_request(record: dict) -> dict:
    """Copy a structured request and decode JSON body/header strings."""
    payload = dict(record)
    for field in ("request_body", "response_body", "request_headers", "response_headers"):
        if field in payload:
            payload[field] = _maybe_parse_json(payload[field])
    return payload


@router.get("/requests/{request_id}/download")
def download_request(request_id: int) -> Response:
    """Pretty-printed JSON attachment for a single request."""
    api = get_api()
    result = api.get_structured_request(request_id)
    if result is None:
        return JSONResponse({"error": "Request not found"}, status_code=404)
    payload = downloadable_request(result)
    content = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="request-{request_id}.json"',
        },
    )


@router.get("/export")
def export_data(
    format: str = Query("csv"),
    search: str = Query(""),
    method: str = Query(""),
    status: int = Query(0),
) -> Response:
    """Export filtered requests as CSV or JSON."""
    api = get_api()
    rows = api.get_all_filtered(search=search, method=method, status=status)

    if format == "json":
        content = json.dumps(rows, indent=2).encode("utf-8")
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="requests.json"'},
        )

    # CSV fallback
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    content = output.getvalue().encode("utf-8")
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="requests.csv"'},
    )


@router.get("/cache/clear")
def cache_clear() -> dict:
    """Clear the COUNT cache."""
    api = get_api()
    api.clear_cache()
    return {"status": "ok"}


def _parse_usage_range(start: str, end: str) -> tuple[datetime, datetime] | JSONResponse:
    """Validate a half-open UTC range shared by the usage endpoints."""
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return JSONResponse(
            {"error": "Invalid datetime format. Use ISO-8601 UTC."},
            status_code=400,
        )
    if end_dt <= start_dt:
        return JSONResponse({"error": "end must be after start"}, status_code=400)
    return start_dt, end_dt


@router.get("/usage")
def usage_summary(
    start: str = Query(...),
    end: str = Query(...),
) -> JSONResponse:
    """Usage summary for a UTC time range."""
    parsed = _parse_usage_range(start, end)
    if isinstance(parsed, JSONResponse):
        return parsed

    result = get_api().get_usage_summary(start, end)
    return JSONResponse(result)


@router.get("/usage/series")
def usage_series(
    start: str = Query(...),
    end: str = Query(...),
    bucket: str | None = Query(None),
    tz: str | None = Query(None),
) -> JSONResponse:
    """Token totals over time for a UTC range.

    ``bucket`` is ``hour``, ``day``, ``week``, ``month``, or omitted to
    choose from the span. ``tz`` is an IANA timezone used to align marks
    with the viewer's calendar; omitted means UTC.
    """
    parsed = _parse_usage_range(start, end)
    if isinstance(parsed, JSONResponse):
        return parsed
    if bucket not in (None, "", "auto") and bucket not in USAGE_BUCKETS:
        return JSONResponse(
            {"error": "Invalid bucket. Use hour, day, week, or month."},
            status_code=400,
        )
    try:
        result = get_api().get_usage_series(start, end, bucket or None, tz or None)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


@router.get("/sessions")
def list_sessions(
    limit: int = Query(50),
    offset: int = Query(0),
) -> dict:
    """Recent agent sessions with request, token, and time rollups."""
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    return get_api().list_sessions(limit=limit, offset=offset)


@router.get("/sessions/{session_id:path}")
def get_session(session_id: str) -> JSONResponse:
    """One session as chronological steps with cumulative tokens."""
    session_id = session_id.strip().strip("/")
    cleaned = clean_session_label(session_id, MAX_SESSION_ID_LEN)
    if cleaned is None:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    result = get_api().get_session(cleaned)
    if result is None:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return JSONResponse(result)
