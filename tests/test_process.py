"""Tests for process management."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from otel_agent.process import (
    ensure_agent_dir,
    write_pid,
    read_pid,
    write_dashboard_pid,
    read_dashboard_pid,
    is_running,
    get_proxy_status,
    get_dashboard_status,
    cleanup_pid,
    cleanup_dashboard_pid,
    stop_proxy,
    stop_dashboard,
)


def test_ensure_agent_dir_creates(tmp_path):
    with patch("otel_agent.process.AGENT_DIR", tmp_path / ".otel-agent"):
        result = ensure_agent_dir()
        assert result.exists()
        assert result.is_dir()


def test_write_read_pid(tmp_path):
    with patch("otel_agent.process.PID_FILE", tmp_path / "proxy.pid"):
        write_pid(12345)
        assert read_pid() == 12345


def test_read_pid_missing(tmp_path):
    with patch("otel_agent.process.PID_FILE", tmp_path / "nonexistent.pid"):
        assert read_pid() is None


def test_read_pid_invalid(tmp_path):
    with patch("otel_agent.process.PID_FILE", tmp_path / "proxy.pid"):
        (tmp_path / "proxy.pid").write_text("not-a-number")
        assert read_pid() is None


def test_is_running_self():
    assert is_running(os.getpid()) is True


def test_is_running_nonexistent():
    assert is_running(999999999) is False


def test_get_proxy_status_running(tmp_path):
    with patch("otel_agent.process.PID_FILE", tmp_path / "proxy.pid"):
        write_pid(os.getpid())
        status = get_proxy_status()
        assert status is not None
        assert status["pid"] == os.getpid()


def test_get_proxy_status_not_running(tmp_path):
    with patch("otel_agent.process.PID_FILE", tmp_path / "proxy.pid"):
        assert get_proxy_status() is None


def test_get_proxy_status_stale_pid(tmp_path):
    """Stale PID file should be cleaned up."""
    with patch("otel_agent.process.PID_FILE", tmp_path / "proxy.pid"):
        write_pid(999999999)
        status = get_proxy_status()
        assert status is None
        assert not (tmp_path / "proxy.pid").exists()


def test_cleanup_pid(tmp_path):
    with patch("otel_agent.process.PID_FILE", tmp_path / "proxy.pid"):
        write_pid(12345)
        assert (tmp_path / "proxy.pid").exists()
        cleanup_pid()
        assert not (tmp_path / "proxy.pid").exists()


def test_cleanup_pid_missing(tmp_path):
    with patch("otel_agent.process.PID_FILE", tmp_path / "nonexistent.pid"):
        cleanup_pid()  # Should not raise


def test_stop_proxy_not_running(tmp_path):
    with patch("otel_agent.process.PID_FILE", tmp_path / "proxy.pid"):
        assert stop_proxy() is False


def test_write_read_dashboard_pid(tmp_path):
    with patch("otel_agent.process.DASHBOARD_PID_FILE", tmp_path / "dashboard.pid"):
        write_dashboard_pid(12345)
        assert read_dashboard_pid() == 12345


def test_read_dashboard_pid_missing(tmp_path):
    with patch("otel_agent.process.DASHBOARD_PID_FILE", tmp_path / "nonexistent.pid"):
        assert read_dashboard_pid() is None


def test_read_dashboard_pid_invalid(tmp_path):
    with patch("otel_agent.process.DASHBOARD_PID_FILE", tmp_path / "dashboard.pid"):
        (tmp_path / "dashboard.pid").write_text("not-a-number")
        assert read_dashboard_pid() is None


def test_get_dashboard_status_running(tmp_path):
    with patch("otel_agent.process.DASHBOARD_PID_FILE", tmp_path / "dashboard.pid"):
        write_dashboard_pid(os.getpid())
        status = get_dashboard_status()
        assert status is not None
        assert status["pid"] == os.getpid()
        assert status["port"] == 9090


def test_get_dashboard_status_stale_pid(tmp_path):
    with patch("otel_agent.process.DASHBOARD_PID_FILE", tmp_path / "dashboard.pid"):
        write_dashboard_pid(999999999)
        status = get_dashboard_status()
        assert status is None
        assert not (tmp_path / "dashboard.pid").exists()


def test_cleanup_dashboard_pid(tmp_path):
    with patch("otel_agent.process.DASHBOARD_PID_FILE", tmp_path / "dashboard.pid"):
        write_dashboard_pid(12345)
        assert (tmp_path / "dashboard.pid").exists()
        cleanup_dashboard_pid()
        assert not (tmp_path / "dashboard.pid").exists()


def test_stop_dashboard_not_running(tmp_path):
    with patch("otel_agent.process.DASHBOARD_PID_FILE", tmp_path / "dashboard.pid"):
        assert stop_dashboard() is False


def test_dashboard_helpers_do_not_touch_proxy_pid(tmp_path):
    proxy_pid = tmp_path / "proxy.pid"
    dash_pid = tmp_path / "dashboard.pid"
    with (
        patch("otel_agent.process.PID_FILE", proxy_pid),
        patch("otel_agent.process.DASHBOARD_PID_FILE", dash_pid),
    ):
        write_pid(111)
        write_dashboard_pid(222)
        cleanup_dashboard_pid()
        assert proxy_pid.exists()
        assert read_pid() == 111
        assert not dash_pid.exists()
