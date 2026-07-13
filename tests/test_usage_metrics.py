"""Behavior tests for dashboard usage metrics."""

from __future__ import annotations

from datetime import datetime, timezone

from otel_agent import server
from otel_agent.logger import TelemetryLogger


def test_normalize_usage_accepts_openai_and_anthropic_shapes() -> None:
    normalize = getattr(server, "normalize_usage")

    assert normalize({"usage": {"prompt_tokens": 10, "completion_tokens": 5}}) == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
    }
    assert normalize({"usage": {"input_tokens": 7, "output_tokens": 3}}) == {
        "input_tokens": 7,
        "output_tokens": 3,
        "total_tokens": 10,
    }


def test_normalize_usage_rejects_invalid_values_without_inventing_tokens() -> None:
    normalize = getattr(server, "normalize_usage")

    assert normalize({"usage": {"prompt_tokens": -1, "completion_tokens": True}}) == {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
    }
    assert normalize({"usage": {"total_tokens": 9}}) == {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": 9,
    }


def test_usage_summary_uses_current_range_and_groups_models(tmp_path) -> None:
    db_path = tmp_path / "usage.duckdb"
    logger = TelemetryLogger(db_path)
    timestamp = datetime.now(timezone.utc).isoformat()
    logger.log_request(
        method="POST",
        url="https://example.test/v1/chat/completions",
        request_headers={},
        request_body="",
        response_status=200,
        response_headers={},
        response_body="{}",
        latency_ms=1.0,
        upstream="https://example.test",
        model_name="openai/gpt-4o",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        timestamp=timestamp,
    )
    summary = logger.storage.get_usage_summary(
        "2000-01-01T00:00:00+00:00", "2100-01-01T00:00:00+00:00"
    )
    logger.close()

    assert summary["total_tokens"] == 15
    assert summary["input_tokens"] == 10
    assert summary["output_tokens"] == 5
    assert summary["eligible_request_count"] == 1
    assert summary["excluded_request_count"] == 0
    assert summary["models"] == [{
        "model_name": "openai/gpt-4o",
        "total_tokens": 15,
        "input_tokens": 10,
        "output_tokens": 5,
        "request_count": 1,
    }]


def test_usage_summary_counts_completed_records_without_usage_as_excluded(tmp_path) -> None:
    db_path = tmp_path / "excluded.duckdb"
    logger = TelemetryLogger(db_path)
    logger.log_request(
        method="POST",
        url="https://example.test/v1/chat/completions",
        request_headers={},
        request_body="",
        response_status=200,
        response_headers={},
        response_body="{}",
        latency_ms=1.0,
        upstream="https://example.test",
    )
    summary = logger.storage.get_usage_summary(
        "2000-01-01T00:00:00+00:00", "2100-01-01T00:00:00+00:00"
    )
    logger.close()

    assert summary["total_tokens"] == 0
    assert summary["eligible_request_count"] == 0
    assert summary["excluded_request_count"] == 1
