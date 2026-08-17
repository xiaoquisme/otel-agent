"""Serve the React dashboard as a SPA.

Deep links such as ``/request/10879`` must return ``index.html`` so the
client router can take over. API routes stay on ``/api`` and are registered
separately.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse


def find_frontend_dist(*extra: Path) -> Path | None:
    """Return the first directory that contains ``index.html``."""
    for path in extra:
        if (path / "index.html").exists():
            return path
    return None


def register_frontend(app: FastAPI, frontend_dist: Path | None) -> None:
    """Mount hashed assets and serve ``index.html`` for browser routes."""
    if frontend_dist is None:
        return

    from fastapi.staticfiles import StaticFiles

    assets_dir = frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static-assets")

    favicon = frontend_dist / "favicon.svg"
    if favicon.exists():

        @app.get("/favicon.svg", response_class=FileResponse)
        async def serve_favicon():
            return FileResponse(favicon, media_type="image/svg+xml")

    icons = frontend_dist / "icons.svg"
    if icons.exists():

        @app.get("/icons.svg", response_class=FileResponse)
        async def serve_icons():
            return FileResponse(icons, media_type="image/svg+xml")

    index_html = frontend_dist / "index.html"

    @app.get("/", response_class=FileResponse)
    async def serve_dashboard():
        return FileResponse(index_html, media_type="text/html")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("assets/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return FileResponse(index_html, media_type="text/html")


def register_legacy_index(app: FastAPI, html_path: Path) -> None:
    """Fallback when the React build is missing."""

    @app.get("/", response_class=FileResponse)
    async def serve_dashboard():
        if html_path.exists():
            return FileResponse(html_path, media_type="text/html")
        return HTMLResponse("<h1>Dashboard</h1><p>index.html not found</p>")
