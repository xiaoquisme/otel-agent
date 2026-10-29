"""Deterministic waste rules on synthetic session trajectories."""
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from otel_agent.dashboard.api import DashboardAPI
from otel_agent.dashboard.routes import router as dashboard_router
from otel_agent.dashboard.routes import set_api as set_dashboard_api
from otel_agent.logger import TelemetryLogger
from otel_agent.sessions import SLOW_STEP_MS, assemble_session
from otel_agent.viewer import format_session_detail
from otel_agent.waste import (
    DUPLICATE_LENGTH_RATIO,
    HEAVY_REQUEST_BYTES,
    RETRY_WINDOW_SECONDS,
    RULE_DUPLICATE,
    RULE_FAILED,
    RULE_HEAVY,
    RULE_RETRY,
    RULE_SLOW,
    RULE_SPIKE,
    SPIKE_ABSOLUTE_TOKENS,
    SPIKE_FLOOR_TOKENS,
    TINY_OUTPUT_TOKENS,
    diagnose_steps,
)

_START = datetime(2026, 4, 1, tzinfo=timezone.utc)


def _ts(seconds: float) -> str:
    return (_START + timedelta(seconds=seconds)).isoformat()


def _step(**overrides) -> dict:
    payload = {
        "id": 1,
        "timestamp": _ts(0),
        "method": "POST",
        "url": "http://localhost:45638/v1/chat/completions",
        "response_status": 200,
        "latency_ms": 80.0,
        "model_name": "openai/gpt-4o",
        "input_tokens": 100,
        "output_tokens": 40,
        "total_tokens": 140,
        "request_body": '{"model":"openai/gpt-4o","messages":[{"role":"user","content":"distinct-turn"}]}',
    }
    payload.update(overrides)
    return payload


def _rules(steps: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for finding in diagnose_steps(steps)["findings"]:
        grouped.setdefault(finding["rule_id"], []).append(finding)
    return grouped


def test_failed_and_slow_steps_become_findings():
    findings = _rules([
        _step(id=1, response_status=500, total_tokens=12, input_tokens=12, output_tokens=0),
        _step(id=2, response_status=None, latency_ms=10),
        _step(id=3, latency_ms=SLOW_STEP_MS, total_tokens=9),
        _step(id=4, latency_ms=SLOW_STEP_MS - 1),
        _step(id=5, response_status=204),
    ])
    assert [item["request_ids"] for item in findings[RULE_FAILED]] == [[1], [2]]
    assert findings[RULE_FAILED][0]["severity"] == "warn"
    assert findings[RULE_FAILED][0]["message"] == "Step 1 returned HTTP 500."
    assert findings[RULE_FAILED][1]["message"] == "Step 2 has no success status."
    assert findings[RULE_FAILED][0]["tokens_involved"] == 12
    assert [item["request_ids"] for item in findings[RULE_SLOW]] == [[3]]
    assert findings[RULE_SLOW][0]["severity"] == "info"
    assert "10s" in findings[RULE_SLOW][0]["message"]
    assert "12.0s" in findings[RULE_SLOW][0]["message"] or "10.0s" in findings[RULE_SLOW][0]["message"]


def test_retry_burst_matches_fingerprint_or_repeated_failure():
    body = '{"model":"openai/gpt-4o","messages":[{"role":"user","content":"retry this exact call"}]}'
    burst = _rules([
        _step(id=10, timestamp=_ts(0), response_status=429, request_body=body, total_tokens=20),
        _step(id=11, timestamp=_ts(5), url="http://localhost:45638/v1/tools", request_body='{"name":"search"}'),
        _step(id=12, timestamp=_ts(9), response_status=200, request_body=body, total_tokens=30),
    ])
    retry = burst[RULE_RETRY]
    assert len(retry) == 1
    assert retry[0]["request_ids"] == [10, 12]
    assert retry[0]["tokens_involved"] == 50
    assert "POST /v1/chat/completions" in retry[0]["message"]
    assert "openai/gpt-4o" in retry[0]["message"]
    assert RULE_DUPLICATE not in burst

    failures = _rules([
        _step(id=1, timestamp=_ts(0), response_status=500, request_body="a" * 40),
        _step(id=2, timestamp=_ts(3), response_status=502, request_body="b" * 40),
    ])
    assert failures[RULE_RETRY][0]["request_ids"] == [1, 2]

    continued = _rules([
        _step(id=1, timestamp=_ts(0), response_status=500, request_body="first prompt " + ("x" * 40)),
        _step(id=2, timestamp=_ts(4), response_status=200, request_body="next prompt " + ("y" * 40)),
    ])
    assert RULE_RETRY not in continued
    assert [item["request_ids"] for item in continued[RULE_FAILED]] == [[1]]

    other_model = _rules([
        _step(id=1, timestamp=_ts(0), response_status=500, model_name="openai/gpt-4o"),
        _step(id=2, timestamp=_ts(2), response_status=500, model_name="openai/gpt-4o-mini"),
    ])
    assert RULE_RETRY not in other_model

    late = _rules([
        _step(id=1, timestamp=_ts(0), response_status=500, request_body=body),
        _step(id=2, timestamp=_ts(RETRY_WINDOW_SECONDS + 1), response_status=500, request_body=body),
    ])
    assert RULE_RETRY not in late

    edge = _rules([
        _step(id=1, timestamp=_ts(0), response_status=500, request_body=body),
        _step(id=2, timestamp=_ts(RETRY_WINDOW_SECONDS), response_status=200, request_body=body),
    ])
    assert edge[RULE_RETRY][0]["request_ids"] == [1, 2]


def test_duplicate_calls_use_the_body_tail_not_a_shared_prefix():
    body = '{"messages":[{"role":"user","content":"do the same work again"}]}'
    same = _rules([
        _step(id=1, request_body=body, total_tokens=100, output_tokens=20, input_tokens=80),
        _step(id=2, timestamp=_ts(1), request_body=body, total_tokens=110, output_tokens=30, input_tokens=80),
    ])
    duplicate = same[RULE_DUPLICATE][0]
    assert duplicate["request_ids"] == [1, 2]
    assert duplicate["severity"] == "warn"
    assert duplicate["tokens_involved"] == 110
    assert "same POST /v1/chat/completions" in duplicate["message"]

    prefix = '{"messages":[{"role":"system","content":"' + ("rules " * 80)
    grown = _rules([
        _step(id=1, request_body=prefix + ' user says alpha"}]}'),
        _step(id=2, timestamp=_ts(1), request_body=prefix + ' user says beta"}]}'),
    ])
    assert RULE_DUPLICATE not in grown

    base = 10_000
    suffix = "tail-" + ("z" * 40)
    near = _rules([
        _step(id=1, request_bytes=base, request_suffix=suffix, request_body=None),
        _step(
            id=2,
            timestamp=_ts(1),
            request_bytes=base + int(base * DUPLICATE_LENGTH_RATIO),
            request_suffix=suffix,
            request_body=None,
        ),
    ])
    assert near[RULE_DUPLICATE][0]["request_ids"] == [1, 2]
    far = _rules([
        _step(id=1, request_bytes=base, request_suffix=suffix, request_body=None),
        _step(
            id=2,
            timestamp=_ts(1),
            request_bytes=base + int(base * DUPLICATE_LENGTH_RATIO) + 500,
            request_suffix=suffix,
            request_body=None,
        ),
    ])
    assert RULE_DUPLICATE not in far

    separated = _rules([
        _step(id=1, request_body=body),
        _step(id=2, timestamp=_ts(1), url="http://localhost:45638/v1/tools", request_body='{"tool":"search"}'),
        _step(id=3, timestamp=_ts(2), request_body=body),
    ])
    assert RULE_DUPLICATE not in separated


def test_token_spike_against_median_percentile_and_short_sessions():
    ordinary = [1000, 1100, 1200, 1300, 1400]
    flat = _rules([
        _step(id=index + 1, timestamp=_ts(index), total_tokens=tokens, input_tokens=tokens - 10, output_tokens=10)
        for index, tokens in enumerate(ordinary)
    ])
    assert RULE_SPIKE not in flat

    spiked = _rules([
        _step(id=index + 1, timestamp=_ts(index), total_tokens=tokens, input_tokens=tokens // 2, output_tokens=tokens // 2)
        for index, tokens in enumerate([1000, 1000, 1000, 1000, 9000])
    ])
    assert spiked[RULE_SPIKE][0]["request_ids"] == [5]
    assert "median" in spiked[RULE_SPIKE][0]["message"]
    assert spiked[RULE_SPIKE][0]["tokens_involved"] == 9000

    percentile = _rules([
        _step(id=index + 1, timestamp=_ts(index), total_tokens=tokens, input_tokens=10, output_tokens=10)
        for index, tokens in enumerate([1000, 1000, 1000, 1000, 2500])
    ])
    assert percentile[RULE_SPIKE][0]["request_ids"] == [5]
    assert "percentile" in percentile[RULE_SPIKE][0]["message"]

    short = _rules([
        _step(id=1, total_tokens=100, input_tokens=80, output_tokens=20),
        _step(id=2, timestamp=_ts(1), total_tokens=SPIKE_ABSOLUTE_TOKENS, input_tokens=100, output_tokens=20),
    ])
    assert short[RULE_SPIKE][0]["request_ids"] == [2]
    assert "threshold" in short[RULE_SPIKE][0]["message"]

    lone = _rules([_step(id=1, total_tokens=SPIKE_ABSOLUTE_TOKENS + 10)])
    assert RULE_SPIKE not in lone

    below_floor = _rules([
        _step(id=index + 1, timestamp=_ts(index), total_tokens=tokens, input_tokens=tokens, output_tokens=0)
        for index, tokens in enumerate([10, 10, 10, 40])
    ])
    assert all(tokens < SPIKE_FLOOR_TOKENS for tokens in (10, 40))
    assert RULE_SPIKE not in below_floor

    input_spike = _rules([
        _step(id=index + 1, timestamp=_ts(index), total_tokens=100, input_tokens=incoming, output_tokens=10)
        for index, incoming in enumerate([100, 100, 100, 100, 8000])
    ])
    assert input_spike[RULE_SPIKE][0]["request_ids"] == [5]
    assert "input tokens" in input_spike[RULE_SPIKE][0]["message"]


def test_heavy_context_uses_size_and_output_without_parsing():
    huge = "x" * (HEAVY_REQUEST_BYTES + 10)
    tiny = _rules([
        _step(id=7, request_body=huge, output_tokens=TINY_OUTPUT_TOKENS, total_tokens=HEAVY_REQUEST_BYTES, input_tokens=4000),
    ])
    assert tiny[RULE_HEAVY][0]["request_ids"] == [7]
    assert tiny[RULE_HEAVY][0]["tokens_involved"] == 4000
    assert "output tokens" in tiny[RULE_HEAVY][0]["message"]

    failed = _rules([
        _step(id=8, request_body=huge, response_status=500, output_tokens=None, total_tokens=None, input_tokens=None),
    ])
    assert failed[RULE_HEAVY][0]["request_ids"] == [8]
    assert failed[RULE_HEAVY][0]["tokens_involved"] is None
    assert "failed" in failed[RULE_HEAVY][0]["message"]

    productive = _rules([
        _step(id=9, request_body=huge, output_tokens=TINY_OUTPUT_TOKENS + 1, total_tokens=500, input_tokens=400),
    ])
    assert RULE_HEAVY not in productive

    small = _rules([
        _step(id=10, request_bytes=HEAVY_REQUEST_BYTES - 1, output_tokens=0, request_body=None),
    ])
    assert RULE_HEAVY not in small


def test_clean_session_has_empty_findings():
    steps = [
        _step(
            id=index + 1,
            timestamp=_ts(index * 30),
            request_body=f'{{"messages":[{{"role":"user","content":"turn {index} unique"}}]}}',
            total_tokens=200 + index * 15,
            input_tokens=150 + index,
            output_tokens=50,
        )
        for index in range(4)
    ]
    diagnosis = diagnose_steps(steps)
    assert diagnosis == {
        "findings": [],
        "finding_counts": {},
        "flagged_request_ids": [],
    }
    for finding in diagnosis["findings"]:
        assert finding["severity"] in {"info", "warn"}


def test_assemble_session_attaches_findings_without_leaking_the_body():
    body = '{"messages":[{"role":"user","content":"same call please"}]}'
    detail = assemble_session("run", [
        {
            "id": 3,
            "timestamp": _ts(0),
            "method": "POST",
            "url": "http://localhost:45638/v1/chat/completions",
            "response_status": 500,
            "latency_ms": 20,
            "model_name": "openai/gpt-4o",
            "total_tokens": None,
            "input_tokens": None,
            "output_tokens": None,
            "request_body": body,
        },
        {
            "id": 4,
            "timestamp": _ts(2),
            "method": "POST",
            "url": "http://localhost:45638/v1/chat/completions",
            "response_status": 200,
            "latency_ms": 30,
            "model_name": "openai/gpt-4o",
            "total_tokens": 15,
            "input_tokens": 10,
            "output_tokens": 5,
            "request_body": body,
        },
    ])
    assert detail["finding_counts"] == {RULE_FAILED: 1, RULE_RETRY: 1}
    assert detail["flagged_request_ids"] == [3, 4]
    assert detail["steps"][0]["waste_rules"] == [RULE_FAILED, RULE_RETRY]
    assert "request_body" not in detail["steps"][0]
    assert "request_suffix" not in detail["steps"][0]
    assert "request_bytes" not in detail["steps"][0]
    text = format_session_detail(detail)
    assert "findings (2):" in text
    assert "retry_burst" in text
    assert "requests=3,4" in text
    quiet = format_session_detail(assemble_session("quiet", []))
    assert "findings" not in quiet


def test_session_detail_api_returns_findings(tmp_path):
    db = tmp_path / "waste.sqlite"
    logger = TelemetryLogger(db)
    body = '{"model":"openai/gpt-4o","messages":[{"role":"user","content":"please retry"}]}'
    logger.log_request(
        method="POST",
        url="http://localhost:45638/v1/chat/completions",
        request_headers={},
        request_body=body,
        response_status=500,
        response_headers={},
        response_body="{}",
        latency_ms=40,
        upstream="https://api.openai.com/v1",
        model_name="openai/gpt-4o",
        input_tokens=20,
        output_tokens=0,
        total_tokens=20,
        timestamp=_ts(0),
        session_id="waste-demo",
        session_step="try-1",
    )
    logger.log_request(
        method="POST",
        url="http://localhost:45638/v1/chat/completions",
        request_headers={},
        request_body=body,
        response_status=200,
        response_headers={},
        response_body="{}",
        latency_ms=55,
        upstream="https://api.openai.com/v1",
        model_name="openai/gpt-4o",
        input_tokens=20,
        output_tokens=8,
        total_tokens=28,
        timestamp=_ts(3),
        session_id="waste-demo",
        session_step="try-2",
    )
    logger.close()

    app = FastAPI()
    api = DashboardAPI(db)
    set_dashboard_api(api)
    app.include_router(dashboard_router)
    client = TestClient(app)
    response = client.get("/api/sessions/waste-demo")
    assert response.status_code == 200
    body_json = response.json()
    assert body_json["finding_counts"] == {"failed_step": 1, "retry_burst": 1}
    assert body_json["flagged_request_ids"]
    assert body_json["findings"][0]["message"]
    assert "request_suffix" not in body_json["steps"][0]
    api.close()
