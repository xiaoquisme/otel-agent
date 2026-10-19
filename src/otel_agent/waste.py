"""Deterministic waste findings for one agent-session trajectory.

Rules read the step dicts already built for ``GET /api/sessions/{id}`` plus
two cheap body signals: ``request_bytes`` (character length) and
``request_suffix`` (a bounded tail). They do not parse JSON and they do not
call a model. Tune thresholds here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from otel_agent.sessions import SLOW_STEP_MS, step_flags

# A failure plus another call on the same target inside this window.
RETRY_WINDOW_SECONDS = 45.0
# Used only when a timestamp cannot be parsed. Steps are chronological.
RETRY_MAX_GAP_STEPS = 4
# A later success counts as a retry when the body tail matches. Another
# failure on the same model and endpoint counts even when the body differs.
RETRY_SUCCESS_REQUIRES_SIMILAR_BODY = True

# Consecutive calls with the same model, endpoint, and body tail.
FINGERPRINT_SUFFIX_CHARS = 256
DUPLICATE_MIN_SUFFIX_CHARS = 24
DUPLICATE_LENGTH_RATIO = 0.02

# Outlier vs the session median, or above a high percentile of the session.
SPIKE_MIN_SAMPLES = 4
SPIKE_MEDIAN_RATIO = 3.0
SPIKE_FLOOR_TOKENS = 1_000
SPIKE_PERCENTILE = 0.90
SPIKE_PERCENTILE_LIFT = 2.0
# Short trajectories have no percentile. Flag only a very large step that
# also dwarfs the smallest step in the session.
SPIKE_ABSOLUTE_TOKENS = 50_000

# Large stored request, tiny or failed output. Length is characters, which
# matches SQLite ``length()`` on TEXT and stays off the proxy write path.
HEAVY_REQUEST_BYTES = 64 * 1024
TINY_OUTPUT_TOKENS = 32

RULE_FAILED = "failed_step"
RULE_SLOW = "slow_step"
RULE_RETRY = "retry_burst"
RULE_DUPLICATE = "duplicate_call"
RULE_SPIKE = "token_spike"
RULE_HEAVY = "heavy_context"

SEVERITY_INFO = "info"
SEVERITY_WARN = "warn"


def diagnose_steps(steps: list[dict]) -> dict:
    """Return waste findings for chronological steps.

    Each finding has ``rule_id``, ``severity`` (``info`` or ``warn``),
    ``request_ids``, ``message``, and ``tokens_involved`` (int or None).
    The result also carries ``finding_counts`` and ``flagged_request_ids``.
    Body rules no-op when a step has neither ``request_body`` nor
    ``request_bytes`` / ``request_suffix``.
    """
    findings: list[dict] = []
    findings.extend(_failed_findings(steps))
    findings.extend(_slow_findings(steps))
    retry = _retry_findings(steps)
    findings.extend(retry)
    findings.extend(_duplicate_findings(steps, retry))
    findings.extend(_spike_findings(steps))
    findings.extend(_heavy_findings(steps))
    return _summary(findings)


def apply_waste_findings(detail: dict, rows: list[dict]) -> dict:
    """Attach findings to a session detail and rule ids onto each step.

    ``rows`` align with ``detail["steps"]`` and may carry ``request_body``,
    ``request_bytes``, and ``request_suffix``. Those signals are not copied
    onto the public step.
    """
    steps = detail.get("steps") or []
    enriched = [_with_body_signals(step, row) for step, row in zip(steps, rows)]
    if len(enriched) != len(steps):
        enriched = [dict(step) for step in steps]
    diagnosis = diagnose_steps(enriched)
    detail["findings"] = diagnosis["findings"]
    detail["finding_counts"] = diagnosis["finding_counts"]
    detail["flagged_request_ids"] = diagnosis["flagged_request_ids"]
    rules_for: dict[int, list[str]] = {}
    for finding in diagnosis["findings"]:
        for request_id in finding["request_ids"]:
            bucket = rules_for.setdefault(request_id, [])
            if finding["rule_id"] not in bucket:
                bucket.append(finding["rule_id"])
    for step in steps:
        request_id = _request_id(step)
        step["waste_rules"] = rules_for.get(request_id, []) if request_id is not None else []
    return detail


def _with_body_signals(step: dict, row: dict) -> dict:
    item = dict(step)
    nbytes = _as_int(row.get("request_bytes"))
    suffix = row.get("request_suffix") if isinstance(row.get("request_suffix"), str) else None
    body = row.get("request_body")
    if isinstance(body, str):
        if nbytes is None:
            nbytes = len(body)
        if suffix is None:
            suffix = body[-FINGERPRINT_SUFFIX_CHARS:]
    if nbytes is not None:
        item["request_bytes"] = nbytes
    if suffix is not None:
        item["request_suffix"] = suffix
    return item


def _summary(findings: list[dict]) -> dict:
    counts: dict[str, int] = {}
    flagged: list[int] = []
    for finding in findings:
        counts[finding["rule_id"]] = counts.get(finding["rule_id"], 0) + 1
        flagged.extend(finding["request_ids"])
    return {
        "findings": findings,
        "finding_counts": counts,
        "flagged_request_ids": sorted(set(flagged)),
    }


def _finding(
    rule_id: str,
    severity: str,
    steps: list[dict],
    message: str,
    tokens_involved: int | None,
) -> dict:
    return {
        "rule_id": rule_id,
        "severity": severity,
        "request_ids": [request_id for step in steps if (request_id := _request_id(step)) is not None],
        "message": message,
        "tokens_involved": tokens_involved,
    }


def _failed_findings(steps: list[dict]) -> list[dict]:
    findings = []
    for index, step in enumerate(steps):
        if "failed" not in _flags(step):
            continue
        status = _as_int(step.get("response_status"))
        label = _step_label(index)
        if status is not None and (status < 200 or status >= 400):
            message = f"{label} returned HTTP {status}."
        else:
            message = f"{label} has no success status."
        findings.append(_finding(
            RULE_FAILED, SEVERITY_WARN, [step], message, _step_tokens(step),
        ))
    return findings


def _slow_findings(steps: list[dict]) -> list[dict]:
    findings = []
    threshold = f"{SLOW_STEP_MS / 1000:.0f}s"
    for index, step in enumerate(steps):
        if "slow" not in _flags(step):
            continue
        latency = _as_float(step.get("latency_ms"))
        label = _step_label(index)
        if latency is None:
            message = f"{label} exceeded the {threshold} latency threshold."
        else:
            message = f"{label} took {_fmt_latency(latency)} (threshold {threshold})."
        findings.append(_finding(
            RULE_SLOW, SEVERITY_INFO, [step], message, _step_tokens(step),
        ))
    return findings


def _retry_findings(steps: list[dict]) -> list[dict]:
    consumed: set[int] = set()
    findings = []
    for index, step in enumerate(steps):
        if index in consumed or not _is_failed(step):
            continue
        cluster = [index]
        for later in range(index + 1, len(steps)):
            if not _in_retry_window(step, steps[later], later - index):
                break
            if later in consumed:
                continue
            if _is_retry_of(step, steps[later]):
                cluster.append(later)
        if len(cluster) < 2:
            continue
        consumed.update(cluster)
        chosen = [steps[pos] for pos in cluster]
        model = _model(step)
        target = _endpoint(step)
        where = f" on {model}" if model else ""
        message = (
            f"{_span(cluster)} repeat {target}{where} "
            f"within {RETRY_WINDOW_SECONDS:.0f}s of a failure."
        )
        findings.append(_finding(
            RULE_RETRY, SEVERITY_WARN, chosen, message, _sum_tokens(chosen),
        ))
    return findings


def _duplicate_findings(steps: list[dict], retry_findings: list[dict]) -> list[dict]:
    covered = [set(finding["request_ids"]) for finding in retry_findings]
    findings = []
    index = 0
    while index < len(steps):
        end = index + 1
        while end < len(steps) and _near_duplicate(steps[end - 1], steps[end]):
            end += 1
        if end == index + 1:
            index += 1
            continue
        chosen = steps[index:end]
        positions = list(range(index, end))
        request_ids = {_request_id(step) for step in chosen}
        request_ids.discard(None)
        if request_ids and any(request_ids <= group for group in covered):
            index = end
            continue
        model = _model(steps[index])
        where = f" on {model}" if model else ""
        message = (
            f"{_span(positions)} sent the same {_endpoint(steps[index])} request{where}."
        )
        repeated = chosen[1:]
        findings.append(_finding(
            RULE_DUPLICATE, SEVERITY_WARN, chosen, message, _sum_tokens(repeated),
        ))
        index = end
    return findings


def _spike_findings(steps: list[dict]) -> list[dict]:
    totals = [_step_tokens(step) for step in steps]
    inputs = [_as_int(step.get("input_tokens")) for step in steps]
    total_samples = [value for value in totals if value is not None]
    input_samples = [value for value in inputs if value is not None]
    findings = []
    for index, step in enumerate(steps):
        total = totals[index]
        reason = _outlier_reason(total_samples, total) if total is not None else None
        kind = "total"
        tokens = total
        if reason is None:
            incoming = inputs[index]
            reason = _outlier_reason(input_samples, incoming) if incoming is not None else None
            kind = "input"
            tokens = incoming
        if reason is None or tokens is None:
            continue
        label = _step_label(index)
        if kind == "input":
            message = f"{label} sent {_fmt_tokens(tokens)} input tokens, {reason}."
        else:
            message = f"{label} used {_fmt_tokens(tokens)} tokens, {reason}."
        findings.append(_finding(RULE_SPIKE, SEVERITY_WARN, [step], message, tokens))
    return findings


def _heavy_findings(steps: list[dict]) -> list[dict]:
    findings = []
    for index, step in enumerate(steps):
        nbytes = _bytes(step)
        if nbytes is None or nbytes < HEAVY_REQUEST_BYTES:
            continue
        output = _as_int(step.get("output_tokens"))
        failed = _is_failed(step)
        tiny = output is not None and output <= TINY_OUTPUT_TOKENS
        if not failed and not tiny:
            continue
        label = _step_label(index)
        size = _fmt_bytes(nbytes)
        if failed and tiny:
            message = (
                f"{label} sent {size} and returned {output} output tokens on a failed call."
            )
        elif failed:
            message = f"{label} sent {size} and failed."
        else:
            message = f"{label} sent {size} and returned {output} output tokens."
        involved = _as_int(step.get("input_tokens"))
        if involved is None:
            involved = _step_tokens(step)
        findings.append(_finding(RULE_HEAVY, SEVERITY_WARN, [step], message, involved))
    return findings


def _outlier_reason(samples: list[int], tokens: int | None) -> str | None:
    if tokens is None or not samples:
        return None
    if len(samples) >= SPIKE_MIN_SAMPLES:
        median = _median(samples)
        ratio_line = max(float(SPIKE_FLOOR_TOKENS), median * SPIKE_MEDIAN_RATIO)
        if tokens >= ratio_line:
            return f"above {SPIKE_MEDIAN_RATIO:g}× the session median ({_fmt_tokens(median)})"
        high = _percentile(samples, SPIKE_PERCENTILE)
        lift_line = max(float(SPIKE_FLOOR_TOKENS), median * SPIKE_PERCENTILE_LIFT)
        if tokens > high and tokens >= lift_line:
            percentile = int(SPIKE_PERCENTILE * 100)
            return f"above the session {percentile}th percentile ({_fmt_tokens(high)})"
        return None
    if len(samples) < 2 or tokens < SPIKE_ABSOLUTE_TOKENS:
        return None
    low = min(samples)
    if low > SPIKE_FLOOR_TOKENS or tokens < low * SPIKE_MEDIAN_RATIO:
        return None
    return (
        f"above the {_fmt_tokens(SPIKE_ABSOLUTE_TOKENS)} token threshold "
        f"and {SPIKE_MEDIAN_RATIO:g}× the smallest step ({_fmt_tokens(low)})"
    )


def _is_retry_of(origin: dict, other: dict) -> bool:
    if _near_duplicate(origin, other):
        return True
    if not _same_target(origin, other):
        return False
    if not RETRY_SUCCESS_REQUIRES_SIMILAR_BODY:
        return True
    return _is_failed(other)


def _near_duplicate(left: dict, right: dict) -> bool:
    left_id = _fingerprint(left)
    right_id = _fingerprint(right)
    if left_id is not None and left_id == right_id:
        return True
    left_suffix = _suffix(left)
    right_suffix = _suffix(right)
    if len(left_suffix) < DUPLICATE_MIN_SUFFIX_CHARS or left_suffix != right_suffix:
        return False
    if not _same_target(left, right):
        return False
    left_len = _bytes(left)
    right_len = _bytes(right)
    if left_len is None or right_len is None or left_len <= 0 or right_len <= 0:
        return False
    return abs(left_len - right_len) / max(left_len, right_len) <= DUPLICATE_LENGTH_RATIO


def _fingerprint(step: dict) -> str | None:
    suffix = _suffix(step)
    nbytes = _bytes(step)
    if not suffix or nbytes is None:
        return None
    return f"{_endpoint(step)}|{_model(step)}|{nbytes}|{suffix}"


def _suffix(step: dict) -> str:
    raw = step.get("request_suffix")
    if not isinstance(raw, str):
        body = step.get("request_body")
        raw = body[-FINGERPRINT_SUFFIX_CHARS:] if isinstance(body, str) else ""
    return raw[-FINGERPRINT_SUFFIX_CHARS:]


def _bytes(step: dict) -> int | None:
    value = _as_int(step.get("request_bytes"))
    if value is not None and value >= 0:
        return value
    body = step.get("request_body")
    if isinstance(body, str):
        return len(body)
    return None


def _same_target(left: dict, right: dict) -> bool:
    return _endpoint(left) == _endpoint(right) and _model(left) == _model(right)


def _endpoint(step: dict) -> str:
    method = str(step.get("method") or "GET").upper()
    url = str(step.get("url") or "")
    path = urlsplit(url).path or url or "/"
    return f"{method} {path}"


def _model(step: dict) -> str:
    value = step.get("model_name")
    return str(value) if value else ""


def _in_retry_window(origin: dict, other: dict, gap: int) -> bool:
    start = _parse_time(origin.get("timestamp"))
    end = _parse_time(other.get("timestamp"))
    if start is not None and end is not None:
        return (end - start).total_seconds() <= RETRY_WINDOW_SECONDS
    return gap <= RETRY_MAX_GAP_STEPS


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _flags(step: dict) -> list[str]:
    flags = step.get("flags")
    if isinstance(flags, list):
        return [str(flag) for flag in flags]
    return step_flags(_as_int(step.get("response_status")), _as_float(step.get("latency_ms")))


def _is_failed(step: dict) -> bool:
    return "failed" in _flags(step)


def _step_tokens(step: dict) -> int | None:
    total = _as_int(step.get("total_tokens"))
    if total is not None:
        return total
    incoming = _as_int(step.get("input_tokens"))
    outgoing = _as_int(step.get("output_tokens"))
    if incoming is None and outgoing is None:
        return None
    return (incoming or 0) + (outgoing or 0)


def _sum_tokens(steps: list[dict]) -> int | None:
    total = 0
    seen = False
    for step in steps:
        tokens = _step_tokens(step)
        if tokens is None:
            continue
        seen = True
        total += tokens
    return total if seen else None


def _request_id(step: dict) -> int | None:
    return _as_int(step.get("id"))


def _step_label(index: int) -> str:
    return f"Step {index + 1}"


def _span(positions: list[int]) -> str:
    numbers = [pos + 1 for pos in positions]
    if len(numbers) == 1:
        return f"Step {numbers[0]}"
    contiguous = numbers == list(range(numbers[0], numbers[-1] + 1))
    if contiguous:
        return f"Steps {numbers[0]}–{numbers[-1]}"
    return "Steps " + ", ".join(str(number) for number in numbers)


def _median(values: list[int]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def _percentile(values: list[int], percentile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = percentile * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _fmt_tokens(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.1f}"


def _fmt_latency(ms: float) -> str:
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.1f}s"


def _fmt_bytes(nbytes: int) -> str:
    if nbytes >= 1_048_576:
        return f"{nbytes / 1_048_576:.1f} MB"
    if nbytes >= 1024:
        return f"{nbytes / 1024:.0f} KB"
    return f"{nbytes} B"


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
