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


def _log(logger: TelemetryLogger, **kwargs) -> None:
    logger.log_request(
        method="POST",
        url="https://example.test/v1/chat/completions",
        request_headers={},
        request_body="",
        response_status=kwargs.pop("response_status", 200),
        response_headers={},
        response_body="{}",
        latency_ms=1.0,
        **kwargs,
    )


def _points(series: dict) -> dict[str, dict]:
    return {point["bucket_start"]: point for point in series["points"]}


def test_usage_series_hourly_matches_summary_and_skips_gaps(tmp_path) -> None:
    logger = TelemetryLogger(tmp_path / "series.sqlite")
    start, end = "2026-03-02T00:00:00+00:00", "2026-03-03T00:00:00+00:00"
    _log(logger, timestamp="2026-03-02T15:10:00+00:00", input_tokens=10, output_tokens=4, total_tokens=14)
    _log(logger, timestamp="2026-03-02T15:40:00+00:00", input_tokens=1, output_tokens=1, total_tokens=2)
    _log(logger, timestamp="2026-03-02T16:00:00Z", input_tokens=5, output_tokens=5, total_tokens=10)
    _log(logger, timestamp="2026-03-02T15:05:00+00:00", response_status=500, input_tokens=100, output_tokens=100, total_tokens=200)
    _log(logger, timestamp="2026-03-02T15:20:00+00:00")
    _log(logger, timestamp="2026-03-01T23:00:00+00:00", input_tokens=50, output_tokens=50, total_tokens=100)

    series = logger.storage.get_usage_series(start, end, bucket="hour")
    summary = logger.storage.get_usage_summary(start, end)
    logger.close()

    assert series["bucket"] == "hour"
    assert series["timezone"] == "UTC"
    assert len(series["points"]) == 24
    points = _points(series)
    assert points["2026-03-02T15:00:00Z"]["input_tokens"] == 11
    assert points["2026-03-02T15:00:00Z"]["output_tokens"] == 5
    assert points["2026-03-02T15:00:00Z"]["total_tokens"] == 16
    assert points["2026-03-02T15:00:00Z"]["request_count"] == 2
    assert points["2026-03-02T16:00:00Z"]["total_tokens"] == 10
    assert points["2026-03-02T14:00:00Z"]["total_tokens"] == 0
    assert sum(point["total_tokens"] for point in series["points"]) == summary["total_tokens"] == 26
    assert sum(point["input_tokens"] for point in series["points"]) == summary["input_tokens"]
    assert sum(point["output_tokens"] for point in series["points"]) == summary["output_tokens"]


def test_usage_series_week_buckets_start_on_monday(tmp_path) -> None:
    logger = TelemetryLogger(tmp_path / "weeks.sqlite")
    _log(logger, timestamp="2026-03-01T12:00:00+00:00", input_tokens=6, output_tokens=4, total_tokens=10)
    _log(logger, timestamp="2026-03-02T08:00:00+00:00", input_tokens=5, output_tokens=2, total_tokens=7)
    _log(logger, timestamp="2026-03-08T22:00:00+00:00", input_tokens=1, output_tokens=2, total_tokens=3)
    series = logger.storage.get_usage_series(
        "2026-02-23T00:00:00+00:00", "2026-03-16T00:00:00+00:00", bucket="week",
    )
    logger.close()

    points = _points(series)
    assert list(points) == [
        "2026-02-23T00:00:00Z",
        "2026-03-02T00:00:00Z",
        "2026-03-09T00:00:00Z",
    ]
    assert points["2026-02-23T00:00:00Z"]["total_tokens"] == 10
    assert points["2026-03-02T00:00:00Z"]["total_tokens"] == 10
    assert points["2026-03-09T00:00:00Z"]["total_tokens"] == 0


def test_usage_series_aligns_days_to_viewer_timezone(tmp_path) -> None:
    """A UTC evening that is still the previous local day stays on that local day."""
    logger = TelemetryLogger(tmp_path / "tz.sqlite")
    _log(logger, timestamp="2026-03-03T07:30:00+00:00", input_tokens=8, output_tokens=2, total_tokens=10)
    series = logger.storage.get_usage_series(
        "2026-03-02T08:00:00+00:00",
        "2026-03-03T08:00:00+00:00",
        bucket="day",
        tz="America/Los_Angeles",
    )
    hourly = logger.storage.get_usage_series(
        "2026-03-02T08:00:00+00:00",
        "2026-03-03T08:00:00+00:00",
        bucket="hour",
        tz="America/Los_Angeles",
    )
    logger.close()

    assert series["timezone"] == "America/Los_Angeles"
    assert len(series["points"]) == 1
    assert _points(series)["2026-03-02T08:00:00Z"]["total_tokens"] == 10
    assert len(hourly["points"]) == 24
    assert _points(hourly)["2026-03-03T07:00:00Z"]["total_tokens"] == 10


def test_usage_series_half_hour_offset_uses_local_hour(tmp_path) -> None:
    logger = TelemetryLogger(tmp_path / "ist.sqlite")
    _log(logger, timestamp="2026-03-02T18:45:00+00:00", input_tokens=3, output_tokens=1, total_tokens=4)
    series = logger.storage.get_usage_series(
        "2026-03-02T18:30:00+00:00",
        "2026-03-03T18:30:00+00:00",
        bucket="hour",
        tz="Asia/Kolkata",
    )
    logger.close()

    points = _points(series)
    assert points["2026-03-02T18:30:00Z"]["total_tokens"] == 4
    assert "2026-03-02T18:00:00Z" not in points
    assert len(series["points"]) == 24


def test_usage_series_auto_bucket_and_all_time_trim(tmp_path) -> None:
    logger = TelemetryLogger(tmp_path / "auto.sqlite")
    _log(logger, timestamp="2026-03-04T01:00:00+00:00", input_tokens=2, output_tokens=2, total_tokens=4)
    day = logger.storage.get_usage_series("2026-03-02T00:00:00+00:00", "2026-03-03T00:00:00+00:00")
    week = logger.storage.get_usage_series("2026-03-01T00:00:00+00:00", "2026-03-11T00:00:00+00:00")
    coarse = logger.storage.get_usage_series(
        "2026-03-01T00:00:00+00:00", "2026-03-21T00:00:00+00:00", bucket="hour",
    )
    all_time = logger.storage.get_usage_series("2000-01-01T00:00:00+00:00", "2100-01-01T00:00:00+00:00")
    logger.close()

    assert day["bucket"] == "hour"
    assert len(day["points"]) == 24
    assert week["bucket"] == "day"
    assert len(week["points"]) == 10
    assert coarse["bucket"] == "day"
    assert len(coarse["points"]) == 20
    assert all_time["bucket"] == "month"
    assert all_time["points"][0]["bucket_start"] == "2026-03-01T00:00:00Z"
    assert all_time["points"][0]["total_tokens"] == 4
    assert all(point["bucket_start"] >= "2026-03-01T00:00:00Z" for point in all_time["points"])


def test_usage_series_spring_forward_skips_missing_local_hour(tmp_path) -> None:
    """A DST spring-forward local day has 23 hourly marks and skips 02:00."""
    from zoneinfo import ZoneInfo

    logger = TelemetryLogger(tmp_path / "dst.sqlite")
    _log(logger, timestamp="2026-03-08T09:30:00+00:00", input_tokens=4, output_tokens=1, total_tokens=5)
    series = logger.storage.get_usage_series(
        "2026-03-08T08:00:00+00:00",
        "2026-03-09T07:00:00+00:00",
        bucket="hour",
        tz="America/Los_Angeles",
    )
    logger.close()

    la = ZoneInfo("America/Los_Angeles")
    hours = [
        datetime.strptime(point["bucket_start"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(la).hour
        for point in series["points"]
    ]
    assert len(series["points"]) == 23
    assert hours[:3] == [0, 1, 3]
    assert 2 not in hours
    assert _points(series)["2026-03-08T09:00:00Z"]["total_tokens"] == 5


def test_usage_series_rejects_unknown_timezone(tmp_path) -> None:
    logger = TelemetryLogger(tmp_path / "bad-tz.sqlite")
    try:
        try:
            logger.storage.get_usage_series(
                "2026-03-02T00:00:00+00:00", "2026-03-03T00:00:00+00:00", tz="Not/AZone",
            )
        except ValueError as exc:
            assert "Unknown timezone" in str(exc)
        else:
            raise AssertionError("expected ValueError")
    finally:
        logger.close()
