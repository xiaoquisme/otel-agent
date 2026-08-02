"""otel-agent dashboard subcommand.

Starts a standalone dashboard server using FastAPI (with only the dashboard
routes).  When the proxy is running, the dashboard is already served at the
proxy's root URL — use ``otel-agent proxy`` instead.
"""
from __future__ import annotations

from pathlib import Path

def handle_dashboard(args) -> None:
    """Start the web dashboard server."""
    from fastapi import FastAPI
    from fastapi.responses import FileResponse
    import uvicorn

    from otel_agent.dashboard.api import DashboardAPI
    from otel_agent.dashboard.routes import router as dashboard_router, set_api as set_dashboard_api

    # Locate frontend assets: installed package (frontend_dist/) or dev source (frontend/dist/)
    _pkg_dir = Path(__file__).parent  # .../otel_agent/commands
    _candidates = [
        _pkg_dir.parent / "dashboard" / "frontend_dist",  # installed wheel
        _pkg_dir.parent.parent.parent / "frontend" / "dist",  # dev: project root
    ]
    frontend_dist = next((p for p in _candidates if (p / "index.html").exists()), None)

    db_path = Path(args.db).expanduser()
    port = args.port

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Start the proxy first: otel-agent proxy")
        return

    # Create a minimal FastAPI app with just the dashboard routes
    app = FastAPI(title="otel-agent-dashboard", version="0.1.0")

    proxy_port = getattr(args, "proxy", None)
    dashboard_api = DashboardAPI(db_path, proxy_port=proxy_port)
    set_dashboard_api(dashboard_api)
    app.include_router(dashboard_router)

    if frontend_dist is not None:
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

    @app.get("/", response_class=FileResponse)
    async def serve_dashboard():
        """Serve the dashboard index.html."""
        if frontend_dist is not None:
            html = frontend_dist / "index.html"
            return FileResponse(html, media_type="text/html")
        # Fallback: serve old monolithic index.html (pre-React)
        legacy_path = Path(__file__).parent.parent / "dashboard" / "index.html"
        if legacy_path.exists():
            return FileResponse(legacy_path, media_type="text/html")
        from fastapi.responses import HTMLResponse
        return HTMLResponse("<h1>Dashboard</h1><p>index.html not found</p>")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        dashboard_api.close()

    print(f"Dashboard running at http://localhost:{port}")
    print(f"Database: {db_path}")
    if proxy_port:
        print(f"Proxy: http://127.0.0.1:{proxy_port}")
    else:
        print("Note: No --proxy specified. Direct DuckDB access used.")
        print("If proxy is running, use --proxy <port> to avoid lock conflicts.")
    print("Ctrl+C to stop\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
