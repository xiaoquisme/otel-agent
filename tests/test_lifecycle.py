"""Tests for the gateway lifecycle journal."""

import json
import os
import threading
from pathlib import Path

import pytest

from otel_agent import lifecycle


@pytest.fixture()
def journal(tmp_path):
    return tmp_path / "lifecycle.jsonl"


def test_append_then_read_roundtrip(journal):
    assert lifecycle.append_event("start", journal=journal, port=45638) is True

    events = lifecycle.read_events(journal=journal)

    assert len(events) == 1
    assert events[0]["event"] == "start"
    assert events[0]["port"] == 45638
    assert events[0]["pid"] == os.getpid()
    assert events[0]["ts"].endswith("Z")


def test_read_events_missing_file_is_empty(tmp_path):
    assert lifecycle.read_events(journal=tmp_path / "absent.jsonl") == []


def test_read_events_skips_corrupt_lines(journal):
    journal.write_text(
        json.dumps({"ts": "2026-11-22T00:00:00Z", "event": "start", "pid": 1}) + "\n"
        + "{not json\n"
        + json.dumps({"ts": "2026-11-22T00:00:01Z", "event": "end", "pid": 1}) + "\n"
    )

    events = lifecycle.read_events(journal=journal)

    assert [event["event"] for event in events] == ["start", "end"]


def test_append_failure_does_not_raise(tmp_path):
    blocked = tmp_path / "file-not-dir"
    blocked.write_text("x")

    assert lifecycle.append_event("start", journal=blocked / "nested.jsonl") is False


def test_summarize_reports_unfinished_session(journal):
    lifecycle.append_event("start", journal=journal, port=45638)
    lifecycle.append_event("heartbeat", journal=journal, uptime_seconds=60, rss_peak_mb=120.5)

    summary = lifecycle.summarize_last_session(journal=journal)

    assert summary["pid"] == os.getpid()
    assert summary["ended"] is False
    assert summary["conclusion"] is None
    assert summary["last_heartbeat"]["uptime_seconds"] == 60
    assert summary["last_heartbeat_at"]


def test_summarize_reports_finished_session(journal):
    lifecycle.append_event("start", journal=journal)
    lifecycle.append_event("end", journal=journal, reason="shutdown")

    summary = lifecycle.summarize_last_session(journal=journal)

    assert summary["ended"] is True
    assert summary["conclusion"] == "end"


def test_summarize_keeps_unclean_conclusion(journal):
    """A concluded unclean exit must not be re-reported on every later start."""
    lifecycle.append_event("start", journal=journal)
    lifecycle.append_event("unclean_exit", journal=journal, previous_pid=1)

    summary = lifecycle.summarize_last_session(journal=journal)

    assert summary["ended"] is True
    assert summary["conclusion"] == "unclean_exit"


def test_summarize_empty_journal_returns_none(journal):
    assert lifecycle.summarize_last_session(journal=journal) is None


def test_summarize_uses_only_the_last_start(journal):
    lifecycle.append_event("start", journal=journal)
    lifecycle.append_event("end", journal=journal, reason="signal")
    lifecycle.append_event("start", journal=journal)
    lifecycle.append_event("heartbeat", journal=journal, uptime_seconds=5)

    summary = lifecycle.summarize_last_session(journal=journal)

    assert summary["ended"] is False


def test_rotate_creates_single_backup(journal):
    journal.write_text("a\n" * 10)

    assert lifecycle.rotate_if_needed(journal, max_bytes=5) is True
    assert journal.exists() is False
    backup = journal.with_name(journal.name + ".1")
    assert backup.read_text() == "a\n" * 10

    # A second rotation replaces the backup rather than piling up.
    journal.write_text("b\n" * 10)
    assert lifecycle.rotate_if_needed(journal, max_bytes=5) is True
    assert backup.read_text() == "b\n" * 10


def test_rotate_leaves_small_journal_alone(journal):
    journal.write_text("a\n")

    assert lifecycle.rotate_if_needed(journal, max_bytes=1024) is False
    assert journal.read_text() == "a\n"


def test_rotate_missing_journal_is_false(tmp_path):
    assert lifecycle.rotate_if_needed(tmp_path / "absent.jsonl") is False


def test_concurrent_appends_stay_json_parseable(journal):
    def writer(tag):
        for index in range(50):
            lifecycle.append_event("heartbeat", journal=journal, tag=tag, index=index)

    threads = [threading.Thread(target=writer, args=(tag,)) for tag in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    lines = [line for line in journal.read_text().splitlines() if line.strip()]
    assert len(lines) == 100
    for line in lines:
        assert json.loads(line)["event"] == "heartbeat"


def test_count_events_windows_by_timestamp(journal):
    journal.write_text(
        json.dumps({"ts": "2000-01-01T00:00:00Z", "event": "unclean_exit", "pid": 1}) + "\n"
        + json.dumps({"ts": lifecycle._utc_now(), "event": "unclean_exit", "pid": 2}) + "\n"
        + json.dumps({"ts": lifecycle._utc_now(), "event": "start", "pid": 3}) + "\n"
    )

    assert lifecycle.count_events("unclean_exit", days=7, journal=journal) == 1


def test_session_records_start_and_end_once(tmp_path):
    journal = tmp_path / "lifecycle.jsonl"
    session = lifecycle.LifecycleSession(port=45638, journal=journal)

    assert session.record_start() is True
    assert session.record_end("shutdown") is True
    assert session.record_end("atexit") is False

    events = lifecycle.read_events(journal=journal)
    assert [event["event"] for event in events] == ["start", "end"]
    assert events[1]["reason"] == "shutdown"


def test_session_heartbeat_records_sample(tmp_path):
    journal = tmp_path / "lifecycle.jsonl"
    session = lifecycle.LifecycleSession(journal=journal)

    assert session.record_heartbeat() is True

    heartbeat = lifecycle.read_events(journal=journal)[0]
    assert heartbeat["event"] == "heartbeat"
    assert heartbeat["uptime_seconds"] >= 0
    assert session.last_heartbeat_at is not None


def test_record_unclean_exit_carries_last_heartbeat(journal):
    previous = {
        "pid": 4242,
        "started_at": "2026-11-22T00:00:00Z",
        "last_heartbeat_at": "2026-11-22T01:00:00Z",
        "last_heartbeat": {"uptime_seconds": 3600, "rss_peak_mb": 512.0},
    }

    assert lifecycle.record_unclean_exit(previous, journal=journal) is True

    event = lifecycle.read_events(journal=journal)[0]
    assert event["event"] == "unclean_exit"
    assert event["previous_pid"] == 4242
    assert event["uptime_seconds"] == 3600
    assert event["rss_peak_mb"] == 512.0


def test_record_unclean_exit_without_heartbeat(journal):
    previous = {"pid": 4242, "started_at": "2026-11-22T00:00:00Z"}

    assert lifecycle.record_unclean_exit(previous, journal=journal) is True

    event = lifecycle.read_events(journal=journal)[0]
    assert event["previous_pid"] == 4242
    assert event["last_heartbeat_at"] is None
