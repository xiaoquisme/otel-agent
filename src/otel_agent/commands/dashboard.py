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
    import uvicorn

    from otel_agent.dashboard.api import DashboardAPI
    from otel_agent.dashboard.routes import router as dashboard_router, set_api as set_dashboard_api
    from otel_agent.dashboard.spa import find_frontend_dist, register_frontend, register_legacy_index

    # Locate frontend assets: installed package (frontend_dist/) or dev source (frontend/dist/)
    _pkg_dir = Path(__file__).parent  # .../otel_agent/commands
    frontend_dist = find_frontend_dist(
        _pkg_dir.parent / "dashboard" / "frontend_dist",  # installed wheel
        _pkg_dir.parent.parent.parent / "frontend" / "dist",  # dev: project root
    )

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
    register_frontend(app, frontend_dist)
    if frontend_dist is None:
        register_legacy_index(app, Path(__file__).parent.parent / "dashboard" / "index.html")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        dashboard_api.close()

    print(f"Dashboard running at http://localhost:{port}")
    print(f"Database: {db_path}")
    if proxy_port:
        print(f"Proxy: http://127.0.0.1:{proxy_port}")
    else:
        print("Note: No --proxy specified. Direct SQLite access used.")
        print("If proxy is running, use --proxy <port> to avoid lock conflicts.")
    print("Ctrl+C to stop\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
