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

    db_path = Path(args.db).expanduser()
    port = args.port

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Start the proxy first: otel-agent proxy")
        return

    # Create a minimal FastAPI app with just the dashboard routes
    app = FastAPI(title="otel-agent-dashboard", version="0.1.0")

    dashboard_api = DashboardAPI(db_path)
    set_dashboard_api(dashboard_api)
    app.include_router(dashboard_router)

    @app.get("/", response_class=FileResponse)
    async def serve_dashboard():
        """Serve the dashboard index.html."""
        html_path = Path(__file__).parent.parent / "dashboard" / "index.html"
        if html_path.exists():
            return FileResponse(html_path, media_type="text/html")
        from fastapi.responses import HTMLResponse
        return HTMLResponse("<h1>Dashboard</h1><p>index.html not found</p>")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        dashboard_api.close()

    print(f"Dashboard running at http://localhost:{port}")
    print(f"Database: {db_path}")
    print("Ctrl+C to stop\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
