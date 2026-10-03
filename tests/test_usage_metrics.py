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
    db_path = tmp_path / "usage.sqlite"
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
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "cacheable_input_tokens": 10,
        "cache_hit_rate": 0.0,
        "request_count": 1,
    }]


def test_usage_summary_cache_hit_rate_across_dialects(tmp_path) -> None:
    """Anthropic-style rows (cache creation reported) count cache tokens in
    the input denominator; OpenAI-style rows already include them in
    input_tokens."""
    db_path = tmp_path / "cache.sqlite"
    logger = TelemetryLogger(db_path)
    timestamp = datetime.now(timezone.utc).isoformat()

    def log(**kw) -> None:
        logger.log_request(
            method="POST", url="u", request_headers={}, request_body="",
            response_status=200, response_headers={}, response_body="{}",
            latency_ms=1.0, timestamp=timestamp, **kw,
        )

    # Anthropic-style: input excludes cache → cacheable = 200 + 700 + 100
    log(model_name="anthropic/claude", input_tokens=200, output_tokens=10,
        total_tokens=210, cache_read_tokens=700, cache_creation_tokens=100)
    # OpenAI-style: input includes cache → cacheable = input_tokens
    log(model_name="openai/gpt-4o", input_tokens=100, output_tokens=5,
        total_tokens=105, cache_read_tokens=50, cache_creation_tokens=None)

    summary = logger.storage.get_usage_summary(
        "2000-01-01T00:00:00+00:00", "2100-01-01T00:00:00+00:00"
    )
    logger.close()

    assert summary["cache_read_tokens"] == 750
    assert summary["cache_creation_tokens"] == 100
    assert summary["cacheable_input_tokens"] == 1100
    assert summary["cache_hit_rate"] == round(750 / 1100, 4)

    per_model = {m["model_name"]: m for m in summary["models"]}
    assert per_model["anthropic/claude"]["cacheable_input_tokens"] == 1000
    assert per_model["anthropic/claude"]["cache_hit_rate"] == 0.7
    assert per_model["openai/gpt-4o"]["cacheable_input_tokens"] == 100
    assert per_model["openai/gpt-4o"]["cache_hit_rate"] == 0.5


def test_usage_summary_without_any_input_has_null_hit_rate(tmp_path) -> None:
    db_path = tmp_path / "nocache.sqlite"
    logger = TelemetryLogger(db_path)
    logger.log_request(
        method="POST", url="u", request_headers={}, request_body="",
        response_status=200, response_headers={}, response_body="{}",
        latency_ms=1.0, output_tokens=5, total_tokens=5,
    )
    summary = logger.storage.get_usage_summary(
        "2000-01-01T00:00:00+00:00", "2100-01-01T00:00:00+00:00"
    )
    logger.close()
    assert summary["cacheable_input_tokens"] == 0
    assert summary["cache_hit_rate"] is None


def test_usage_summary_counts_completed_records_without_usage_as_excluded(tmp_path) -> None:
    db_path = tmp_path / "excluded.sqlite"
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
