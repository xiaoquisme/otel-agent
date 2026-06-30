"""Tests for otel-agent CLI dispatcher."""

import tempfile
from pathlib import Path
from otel_agent.cli import build_parser


def test_parser_defaults():
    parser = build_parser()
    args = parser.parse_args(["proxy"])
    assert args.port == 8080
    assert args.upstream == ""
    assert args.db == "~/.otel-agent/telemetry.db"
    assert args.config == "~/.otel-agent/config.yaml"


def test_parser_custom_values():
    parser = build_parser()
    args = parser.parse_args([
        "proxy", "--port", "9090",
        "--upstream", "https://api.anthropic.com",
        "--db", "/tmp/logs.db",
        "--config", "/tmp/my-config.yaml",
    ])
    assert args.port == 9090
    assert args.upstream == "https://api.anthropic.com"
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
    assert args.port == 8080


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

    db_path = tmp_path / "test.db"
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


def test_handle_config_show_masks_keys(tmp_path, capsys):
    from otel_agent.commands.config_cmd import handle_config
    import argparse

    config_file = tmp_path / "config.yaml"
    config_file.write_text("providers:\n  openai:\n    keys:\n      - key: sk-pro...3456\n        active: true\n")
    args = argparse.Namespace(config=str(config_file), config_action="show")
    handle_config(args)
    captured = capsys.readouterr()
    assert "sk-pro***" in captured.out
    assert "sk-pro...3456" not in captured.out


def test_handle_doctor_checks(tmp_path, capsys):
    from otel_agent.commands.doctor import handle_doctor
    import argparse

    config_file = tmp_path / "config.yaml"
    config_file.write_text("providers: {}")
    args = argparse.Namespace(config=str(config_file), port=18765)
    handle_doctor(args)
    captured = capsys.readouterr()
    assert "Python" in captured.out
    assert "mitmproxy" in captured.out


def test_handle_routes(tmp_path, capsys):
    from otel_agent.commands.routes import handle_routes
    import argparse

    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    - name: xiaomi
      base_url: https://api.openai.com/v1
      api_key: sk-a
      active: true
  anthropic:
    - name: deesseek
      base_url: https://api.anthropic.com
      api_key: sk-b
      active: true
""")
    args = argparse.Namespace(config=str(config_file))
    handle_routes(args)
    captured = capsys.readouterr()
    assert "/openai" in captured.out
    assert "/anthropic" in captured.out
    assert "openai" in captured.out
    assert "anthropic" in captured.out
    assert "https://api.openai.com/v1" in captured.out
    assert "https://api.anthropic.com" in captured.out


def test_handle_routes_no_config(tmp_path, capsys):
    from otel_agent.commands.routes import handle_routes
    import argparse

    config_file = tmp_path / "config.yaml"
    config_file.write_text("providers: {}")
    args = argparse.Namespace(config=str(config_file))
    handle_routes(args)
    captured = capsys.readouterr()
    assert "No providers configured" in captured.out


def test_default_db_path_is_absolute():
    """Default DB path must be absolute (starts with / or ~)."""
    from otel_agent.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["dashboard"])
    assert args.db.startswith("/") or args.db.startswith("~"), \
        f"Default DB path should be absolute, got: {args.db}"


def test_default_db_path_consistent_across_commands():
    """All commands use the same default DB path."""
    from otel_agent.cli import build_parser
    parser = build_parser()

    proxy_args = parser.parse_args(["proxy"])
    dashboard_args = parser.parse_args(["dashboard"])
    view_args = parser.parse_args(["view"])

    assert proxy_args.db == dashboard_args.db == view_args.db, \
        f"Inconsistent default DB paths: proxy={proxy_args.db}, dashboard={dashboard_args.db}, view={view_args.db}"
