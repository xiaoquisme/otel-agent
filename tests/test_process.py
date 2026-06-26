"""Tests for process management."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from otel_agent.process import (
    ensure_agent_dir,
    write_pid,
    read_pid,
    is_running,
    get_proxy_status,
    cleanup_pid,
    stop_proxy,
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
