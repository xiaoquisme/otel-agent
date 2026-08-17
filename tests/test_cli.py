"""Tests for otel-agent CLI dispatcher."""

import tempfile
from pathlib import Path

import pytest

from otel_agent.cli import build_parser


def test_parser_defaults():
    parser = build_parser()
    args = parser.parse_args(["proxy"])
    assert args.port == 45638
    assert args.db == "~/.otel-agent/telemetry.sqlite"
    assert args.config == "~/.otel-agent/config.yaml"


def test_parser_custom_values():
    parser = build_parser()
    args = parser.parse_args([
        "proxy", "--port", "9090",
        "--db", "/tmp/logs.db",
        "--config", "/tmp/my-config.yaml",
    ])
    assert args.port == 9090
    assert args.db == "/tmp/logs.db"
    assert args.config == "/tmp/my-config.yaml"


def test_parser_view_subcommand():
    parser = build_parser()
    args = parser.parse_args(["view", "--filter", "openai", "--limit", "50"])
    assert args.command == "view"
    assert args.filter == "openai"
    assert args.limit == 50


def test_parser_init_subcommand():
    parser = build_parser()
    args = parser.parse_args(["init", "--config", "/tmp/test.yaml"])
    assert args.command == "init"
    assert args.config == "/tmp/test.yaml"


def test_parser_config_subcommand():
    parser = build_parser()
    args = parser.parse_args(["config", "path"])
    assert args.command == "config"
    assert args.config_action == "path"


def test_parser_config_show():
    parser = build_parser()
    args = parser.parse_args(["config", "show"])
    assert args.config_action == "show"


def test_parser_config_edit():
    parser = build_parser()
    args = parser.parse_args(["config", "edit"])
    assert args.config_action == "edit"


def test_parser_doctor_subcommand():
    parser = build_parser()
    args = parser.parse_args(["doctor"])
    assert args.command == "doctor"
    assert args.config == "~/.otel-agent/config.yaml"
    assert args.port == 45638


def test_version_flag(capsys):
    parser = build_parser()
    try:
        parser.parse_args(["--version"])
    except SystemExit:
        pass
    captured = capsys.readouterr()
    assert "otel-agent" in captured.out


def test_no_command_shows_help(capsys):
    parser = build_parser()
    try:
        parser.parse_args([])
    except SystemExit:
        pass


def test_handle_init_creates_config(tmp_path):
    from otel_agent.commands.init import handle_init
    import argparse

    config_file = tmp_path / "config.yaml"
    args = argparse.Namespace(config=str(config_file))
    handle_init(args)
    assert config_file.exists()
    content = config_file.read_text()
    assert "openai" in content


def test_handle_init_warns_existing(tmp_path, capsys):
    from otel_agent.commands.init import handle_init
    import argparse

    config_file = tmp_path / "config.yaml"
    config_file.write_text("existing")
    args = argparse.Namespace(config=str(config_file))
    handle_init(args)
    captured = capsys.readouterr()
    assert "already exists" in captured.out


def test_handle_view_no_requests(tmp_path, capsys):
    from otel_agent.commands.view import handle_view
    from otel_agent.logger import TelemetryLogger
    import argparse

    db_path = tmp_path / "test.sqlite"
    logger = TelemetryLogger(db_path)
    logger.close()

    args = argparse.Namespace(db=str(db_path), filter="", limit=20)
    handle_view(args)
    captured = capsys.readouterr()
    assert "No requests logged yet" in captured.out


def test_handle_config_path(tmp_path, capsys):
    from otel_agent.commands.config_cmd import handle_config
    import argparse

    config_file = tmp_path / "config.yaml"
    args = argparse.Namespace(config=str(config_file), config_action="path")
    handle_config(args)
    captured = capsys.readouterr()
    assert str(config_file) in captured.out


def test_handle_doctor_checks(tmp_path, capsys):
    from otel_agent.commands.doctor import handle_doctor
    import argparse

    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
    api_format: openai
""")
    args = argparse.Namespace(config=str(config_file), port=18765)
    handle_doctor(args)
    captured = capsys.readouterr()
    assert "Python" in captured.out
    assert "fastapi" in captured.out


def test_handle_routes(tmp_path, capsys):
    from otel_agent.commands.routes import handle_routes
    import argparse

    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-a
    api_format: openai
  - name: anthropic
    base_url: https://api.anthropic.com
    api_key: sk-b
    api_format: anthropic
""")
    args = argparse.Namespace(config=str(config_file))
    handle_routes(args)
    captured = capsys.readouterr()
    assert "openai" in captured.out
    assert "anthropic" in captured.out
    assert "https://api.openai.com/v1" in captured.out
    assert "https://api.anthropic.com" in captured.out


def test_handle_routes_no_config(tmp_path, capsys):
    from otel_agent.commands.routes import handle_routes
    import argparse

    config_file = tmp_path / "config.yaml"
    config_file.write_text("providers: []")
    args = argparse.Namespace(config=str(config_file))
    handle_routes(args)
    captured = capsys.readouterr()
    assert "No providers configured" in captured.out


def test_default_db_path_is_absolute():
    from otel_agent.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["dashboard"])
    assert args.db.startswith("/") or args.db.startswith("~"), \
        f"Default DB path should be absolute, got: {args.db}"


def test_default_db_path_consistent_across_commands():
    from otel_agent.cli import build_parser
    parser = build_parser()

    proxy_args = parser.parse_args(["proxy"])
    dashboard_args = parser.parse_args(["dashboard"])
    view_args = parser.parse_args(["view"])

    assert proxy_args.db == dashboard_args.db == view_args.db, \
        f"Inconsistent default DB paths: proxy={proxy_args.db}, dashboard={dashboard_args.db}, view={view_args.db}"


def test_handle_dashboard_startup_note_says_sqlite_not_duckdb(tmp_path, capsys, monkeypatch):
    """Standalone dashboard without --proxy must not claim DuckDB access."""
    import argparse
    import uvicorn

    from otel_agent.commands.dashboard import handle_dashboard

    db_path = tmp_path / "telemetry.sqlite"
    db_path.write_bytes(b"")
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)

    args = argparse.Namespace(
        db=str(db_path), port=9090, proxy=None, foreground=True, dashboard_action=None,
    )
    handle_dashboard(args)
    captured = capsys.readouterr()
    assert "DuckDB" not in captured.out
    assert "Direct SQLite access used." in captured.out


def test_dashboard_default_is_not_foreground():
    from otel_agent.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["dashboard"])
    assert args.foreground is False
    assert args.dashboard_action is None


def test_dashboard_foreground_flag():
    from otel_agent.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["dashboard", "-f"])
    assert args.foreground is True


def test_dashboard_stop_action():
    from otel_agent.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["dashboard", "stop"])
    assert args.dashboard_action == "stop"


def test_dashboard_flags_still_parse_with_port():
    from otel_agent.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["dashboard", "-p", "3000"])
    assert args.port == 3000
    assert args.foreground is False


def test_handle_dashboard_background_prints_url_and_pid(tmp_path, capsys, monkeypatch):
    import argparse
    from types import SimpleNamespace

    from otel_agent.commands import dashboard as dash_mod

    db_path = tmp_path / "telemetry.sqlite"
    db_path.write_bytes(b"")
    log_file = tmp_path / "dashboard.log"
    port_file = tmp_path / "dashboard.port"
    written = {}

    monkeypatch.setattr(dash_mod, "DASHBOARD_LOG_FILE", log_file)
    monkeypatch.setattr(dash_mod, "DASHBOARD_PORT_FILE", port_file)
    monkeypatch.setattr(dash_mod, "get_dashboard_status", lambda: None)
    monkeypatch.setattr(dash_mod, "_is_port_in_use", lambda port: False)
    monkeypatch.setattr(dash_mod, "ensure_agent_dir", lambda: tmp_path)
    monkeypatch.setattr(dash_mod, "write_dashboard_pid", lambda pid: written.setdefault("pid", pid))
    monkeypatch.setattr(dash_mod, "time", SimpleNamespace(sleep=lambda _s: None))

    class FakeProc:
        pid = 4242

        def poll(self):
            return None

    monkeypatch.setattr(dash_mod.subprocess, "Popen", lambda *a, **k: FakeProc())

    args = argparse.Namespace(
        db=str(db_path), port=9090, proxy=None, foreground=False, dashboard_action=None,
    )
    dash_mod.handle_dashboard(args)
    captured = capsys.readouterr()
    assert "http://localhost:9090" in captured.out
    assert "4242" in captured.out
    assert written["pid"] == 4242
    assert port_file.read_text() == "9090"


def test_handle_dashboard_missing_db_does_not_spawn(tmp_path, capsys, monkeypatch):
    import argparse

    from otel_agent.commands import dashboard as dash_mod

    called = {"popen": False}
    monkeypatch.setattr(
        dash_mod.subprocess, "Popen", lambda *a, **k: called.__setitem__("popen", True)
    )

    args = argparse.Namespace(
        db=str(tmp_path / "missing.sqlite"),
        port=9090,
        proxy=None,
        foreground=False,
        dashboard_action=None,
    )
    dash_mod.handle_dashboard(args)
    captured = capsys.readouterr()
    assert "Start the proxy first" in captured.out
    assert called["popen"] is False


def test_handle_dashboard_already_running_exits(tmp_path, capsys, monkeypatch):
    import argparse

    from otel_agent.commands import dashboard as dash_mod

    db_path = tmp_path / "telemetry.sqlite"
    db_path.write_bytes(b"")
    monkeypatch.setattr(dash_mod, "get_dashboard_status", lambda: {"pid": 99, "port": 9090})
    called = {"popen": False}
    monkeypatch.setattr(
        dash_mod.subprocess, "Popen", lambda *a, **k: called.__setitem__("popen", True)
    )

    args = argparse.Namespace(
        db=str(db_path), port=9090, proxy=None, foreground=False, dashboard_action=None,
    )
    with pytest.raises(SystemExit) as exc:
        dash_mod.handle_dashboard(args)
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "dashboard stop" in captured.out
    assert called["popen"] is False


def test_handle_dashboard_port_in_use_exits(tmp_path, capsys, monkeypatch):
    import argparse

    from otel_agent.commands import dashboard as dash_mod

    db_path = tmp_path / "telemetry.sqlite"
    db_path.write_bytes(b"")
    monkeypatch.setattr(dash_mod, "get_dashboard_status", lambda: None)
    monkeypatch.setattr(dash_mod, "_is_port_in_use", lambda port: True)
    called = {"popen": False}
    monkeypatch.setattr(
        dash_mod.subprocess, "Popen", lambda *a, **k: called.__setitem__("popen", True)
    )

    args = argparse.Namespace(
        db=str(db_path), port=9090, proxy=None, foreground=False, dashboard_action=None,
    )
    with pytest.raises(SystemExit) as exc:
        dash_mod.handle_dashboard(args)
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "-p" in captured.out
    assert called["popen"] is False


def test_handle_dashboard_stop_invokes_helper(capsys, monkeypatch):
    import argparse

    from otel_agent.commands import dashboard as dash_mod

    called = {"stop": False}
    monkeypatch.setattr(dash_mod, "stop_dashboard", lambda: called.__setitem__("stop", True) or True)

    args = argparse.Namespace(dashboard_action="stop")
    dash_mod.handle_dashboard(args)
    captured = capsys.readouterr()
    assert called["stop"] is True
    assert "Dashboard stopped." in captured.out
