"""Tests for CLI arg parsing (backward compat with test_proxy.py name)."""

from otel_agent.cli import build_parser


def test_parser_defaults():
    parser = build_parser()
    args = parser.parse_args(["proxy"])
    assert args.port == 45638
    assert args.db == "~/.otel-agent/telemetry.sqlite"


def test_parser_custom_values():
    parser = build_parser()
    args = parser.parse_args([
        "proxy", "--port", "9090",
        "--db", "/tmp/logs.db",
    ])
    assert args.port == 9090
    assert args.db == "/tmp/logs.db"


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


# ------------------------------------------------------------------
# Lifecycle: what the start path and the status command report
# ------------------------------------------------------------------

import os

import pytest

from otel_agent import lifecycle
from otel_agent.commands import proxy as proxy_mod


@pytest.fixture()
def agent_paths(tmp_path, monkeypatch):
    journal = tmp_path / "lifecycle.jsonl"
    log = tmp_path / "proxy.log"
    monkeypatch.setattr(lifecycle, "LIFECYCLE_FILE", journal)
    monkeypatch.setattr(proxy_mod, "LOG_FILE", log)
    monkeypatch.setattr(proxy_mod, "MAX_LOG_BYTES", 200)
    return journal, log


def _make_args():
    class Args:
        port = 45638
        db = "~/.otel-agent/telemetry.sqlite"
        config = "~/.otel-agent/config.yaml"
        foreground = False

    return Args()


def test_prepare_start_reports_unfinished_session(agent_paths):
    journal, log = agent_paths
    lifecycle.append_event("start", journal=journal, port=45638, pid=999999999)
    lifecycle.append_event("heartbeat", journal=journal, uptime_seconds=120, rss_peak_mb=340.5)

    proxy_mod._prepare_start(_make_args())

    events = lifecycle.read_events(journal=journal)
    unclean = [event for event in events if event["event"] == "unclean_exit"]
    assert len(unclean) == 1
    assert unclean[0]["previous_pid"] == 999999999
    assert unclean[0]["uptime_seconds"] == 120
    assert "without a shutdown record" in log.read_text()


def test_prepare_start_leaves_finished_session_alone(agent_paths):
    journal, log = agent_paths
    lifecycle.append_event("start", journal=journal)
    lifecycle.append_event("end", journal=journal, reason="signal")

    proxy_mod._prepare_start(_make_args())

    assert not [e for e in lifecycle.read_events(journal=journal) if e["event"] == "unclean_exit"]
    assert not log.exists() or "without a shutdown record" not in log.read_text()


def test_prepare_start_rotates_oversized_logs(agent_paths):
    journal, log = agent_paths
    log.write_text("x" * 500)

    proxy_mod._prepare_start(_make_args())

    assert log.with_name(log.name + ".1").exists()
    assert not log.exists()


def test_status_reports_unfinished_session(agent_paths, monkeypatch, capsys):
    journal, _log = agent_paths
    lifecycle.append_event("start", journal=journal, port=45638)
    lifecycle.append_event("heartbeat", journal=journal, uptime_seconds=600, rss_peak_mb=900.0)
    monkeypatch.setattr(proxy_mod, "get_proxy_status", lambda: None)
    monkeypatch.setattr(proxy_mod, "_print_last_session", proxy_mod._print_last_session)

    proxy_mod.handle_proxy_status(_make_args())

    out = capsys.readouterr().out
    assert "stopped without a shutdown record" in out
    assert "ran for:        600s" in out
    assert "peak RSS:       900.0MB" in out
    assert "--lifecycle" in out


def test_status_stays_quiet_for_current_session(agent_paths, monkeypatch, capsys):
    journal, _log = agent_paths
    lifecycle.append_event("start", journal=journal, port=45638)
    monkeypatch.setattr(
        proxy_mod, "get_proxy_status", lambda: {"pid": os.getpid(), "port": 45638}
    )

    proxy_mod.handle_proxy_status(_make_args())

    out = capsys.readouterr().out
    assert "Current session started" in out
    assert "stopped without a shutdown record" not in out


def test_status_stays_quiet_for_clean_exit(agent_paths, monkeypatch, capsys):
    journal, _log = agent_paths
    lifecycle.append_event("start", journal=journal)
    lifecycle.append_event("end", journal=journal, reason="signal")
    monkeypatch.setattr(proxy_mod, "get_proxy_status", lambda: None)

    proxy_mod.handle_proxy_status(_make_args())

    assert "stopped without a shutdown record" not in capsys.readouterr().out


def test_logs_lifecycle_prints_last_events(agent_paths, capsys):
    journal, _log = agent_paths
    for index in range(3):
        lifecycle.append_event("heartbeat", journal=journal, index=index)

    class Args:
        lifecycle_flag = True

    args = type("Args", (), {"lifecycle": True, "lines": 2})()
    proxy_mod.handle_proxy_logs(args)

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 2
    assert "index=2" in lines[-1]


def test_logs_lifecycle_without_journal_is_not_an_error(agent_paths, capsys):
    args = type("Args", (), {"lifecycle": True, "lines": 5})()
    proxy_mod.handle_proxy_logs(args)

    assert "No lifecycle records yet" in capsys.readouterr().out


def test_background_start_runs_child_unbuffered(agent_paths, monkeypatch, tmp_path):
    journal, _log = agent_paths
    captured = {}

    class FakeProc:
        pid = 4321

        def poll(self):
            return None

    def fake_popen(cmd, **kwargs):
        captured["env"] = kwargs.get("env")
        return FakeProc()

    monkeypatch.setattr(proxy_mod.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(proxy_mod, "_is_port_in_use", lambda port: False)
    monkeypatch.setattr(proxy_mod, "get_proxy_status", lambda: None)
    monkeypatch.setattr(proxy_mod, "write_pid", lambda pid: None)
    monkeypatch.setattr(proxy_mod.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(proxy_mod, "start_cursor_sidecar", lambda config: None)
    monkeypatch.setattr(proxy_mod, "PORT_FILE", tmp_path / "proxy.port")
    monkeypatch.setattr(proxy_mod, "ensure_agent_dir", lambda: tmp_path)

    proxy_mod.handle_proxy_start(_make_args())

    assert captured["env"]["PYTHONUNBUFFERED"] == "1"


def test_prepare_start_ignores_a_session_still_running(agent_paths, monkeypatch):
    """A live gateway's unfinished session is not an exit just because a second
    start attempt noticed it."""
    journal, log = agent_paths
    lifecycle.append_event("start", journal=journal, port=45638, pid=os.getpid())
    monkeypatch.setattr(proxy_mod, "is_running", lambda pid: True)

    proxy_mod._prepare_start(_make_args())

    assert not [e for e in lifecycle.read_events(journal=journal) if e["event"] == "unclean_exit"]
    assert not log.exists() or "without a shutdown record" not in log.read_text()
