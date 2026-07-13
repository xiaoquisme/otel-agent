"""FastAPI router for the otel-agent dashboard.

Provides 7 endpoints:
  GET /              — index.html (served by server.py mount)
  GET /api/requests  — paginated request list
  GET /api/requests/{id} — single request detail
  GET /api/events    — SSE stream of new requests
  GET /api/export    — CSV/JSON export
  GET /api/cache/clear — clear the COUNT cache
  GET /api/usage     — usage summary for a time range
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response, StreamingResponse

from otel_agent.dashboard.api import DashboardAPI

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
    """Single request detail with pre-rendered LLM bodies."""
    api = get_api()
    result = api.get_rendered_request(request_id)
    if result is None:
        return JSONResponse({"error": "Request not found"}, status_code=404)
    return JSONResponse(result)


@router.get("/render/{request_id}")
def render_request(request_id: int) -> JSONResponse:
    """Pre-rendered LLM bodies for a request."""
    api = get_api()
    result = api.get_rendered_request(request_id)
    if result is None:
        return JSONResponse({"error": "Request not found"}, status_code=404)
    return JSONResponse({
        "id": result["id"],
        "format": result.get("format"),
        "rendered_request": result.get("rendered_request"),
        "rendered_response": result.get("rendered_response"),
    })


@router.get("/events")
async def sse_events():
    """Server-Sent Events stream of new requests."""
    api = get_api()
    state = {"last_id": api.get_max_id()}

    async def event_generator():
        while True:
            new_requests = api.get_requests_since(state["last_id"])
            for req in new_requests:
                data = json.dumps(req)
                yield f"data: {data}\n\n"
                state["last_id"] = req["id"]
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
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


@router.get("/usage")
def usage_summary(
    start: str = Query(...),
    end: str = Query(...),
) -> JSONResponse:
    """Usage summary for a UTC time range."""
    api = get_api()

    # Validate ISO-8601 format
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

    if (end_dt - start_dt).total_seconds() > 48 * 3600:
        return JSONResponse({"error": "Range must not exceed 48 hours"}, status_code=400)

    result = api.get_usage_summary(start, end)
    return JSONResponse(result)
