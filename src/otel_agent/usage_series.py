"""Bucket completed-request token totals for the usage chart.

Timestamps are stored as UTC ISO-8601 text. Periods on the dashboard are
local calendar ranges, so each series is rolled up in an IANA timezone
(``UTC`` when the caller does not send one). Aggregation in SQLite is by
UTC minute; folding those minutes into hours, days, weeks, or months
happens here so half-hour offsets and DST transitions stay aligned with
the clock the viewer selected.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

USAGE_BUCKETS = ("hour", "day", "week", "month")
MAX_POINTS = 400
_LONG_RANGE = timedelta(days=62)
_COARSER = {"hour": "day", "day": "week", "week": "month"}

MinuteRow = tuple[str, int, int, int, int]


def resolve_timezone(name: str | None) -> ZoneInfo:
    """Return a timezone, treating a missing name as UTC.

    Raises:
        ValueError: The name is not an IANA timezone.
    """
    if name is None or name == "" or name.upper() == "UTC":
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {name}") from exc


def select_bucket(
    start: datetime,
    end: datetime,
    requested: str | None,
    tz: ZoneInfo,
    now: datetime,
) -> str:
    """Pick a bucket that stays readable for the requested span.

    An explicit bucket is kept unless it would draw more than
    ``MAX_POINTS`` marks, in which case it is coarsened (hour → day →
    week → month). ``None`` or ``"auto"`` follows the span: hourly through
    a day and a half, daily through 45 days, weekly through 180 days, and
    monthly after that.
    """
    start = _as_utc(start)
    end = _as_utc(end)
    now = _as_utc(now)
    if requested not in (None, "", "auto") and requested not in USAGE_BUCKETS:
        raise ValueError(
            "Invalid bucket. Use hour, day, week, or month."
        )
    if requested in USAGE_BUCKETS:
        bucket = requested
    else:
        span = (end - start).total_seconds()
        if span <= 36 * 3600:
            bucket = "hour"
        elif span <= 45 * 86400:
            bucket = "day"
        elif span <= 180 * 86400:
            bucket = "week"
        else:
            bucket = "month"
    window_end = end if end <= now else now
    while bucket != "month" and _exceeds(start, window_end, bucket, tz, MAX_POINTS):
        bucket = _COARSER[bucket]
    return bucket


def build_usage_series(
    start: str,
    end: str,
    start_dt: datetime,
    end_dt: datetime,
    bucket: str,
    minutes: Iterable[MinuteRow],
    tz: ZoneInfo,
    now: datetime | None = None,
) -> dict:
    """Zero-fill ``bucket`` marks and sum minute rows into them.

    ``start`` and ``end`` are echoed as the caller sent them. Marks after
    the current instant are omitted unless a recorded minute actually falls
    there. Ranges longer than 62 days begin at the first bucket that has
    tokens so an all-time query does not draw empty months back to the
    sentinel start.
    """
    if bucket not in USAGE_BUCKETS:
        raise ValueError("Invalid bucket. Use hour, day, week, or month.")
    current = _as_utc(now or datetime.now(timezone.utc))
    start_dt = _as_utc(start_dt)
    end_dt = _as_utc(end_dt)
    rolled: dict[str, list[int]] = {}
    for minute_key, input_tokens, output_tokens, total_tokens, request_count in minutes:
        instant = _parse_minute(minute_key)
        if instant is None:
            continue
        floor = _floor_local(instant, bucket, tz)
        key = _bucket_id(floor)
        slot = rolled.setdefault(key, [0, 0, 0, 0])
        slot[0] += int(input_tokens)
        slot[1] += int(output_tokens)
        slot[2] += int(total_tokens)
        slot[3] += int(request_count)

    fill_end = end_dt if end_dt <= current else current
    data_instants = [
        _parse_bucket_id(key)
        for key, values in rolled.items()
        if values[0] or values[1] or values[2]
    ]
    data_instants = [item for item in data_instants if item is not None]
    if data_instants:
        last_data = max(data_instants)
        if fill_end <= last_data < end_dt:
            fill_end = _instant_after(last_data, bucket, tz)
    long_range = (end_dt - start_dt) > _LONG_RANGE
    if long_range and not data_instants:
        marks: list[datetime] = []
    elif long_range:
        fill_start = _floor_local(min(data_instants), bucket, tz)
        marks = _walk(fill_start, fill_end, bucket, tz)
    elif fill_end <= start_dt:
        marks = []
    else:
        marks = _walk(_floor_local(start_dt, bucket, tz), fill_end, bucket, tz)

    seen = {_bucket_id(mark) for mark in marks}
    for key, instant in (
        (key, _parse_bucket_id(key)) for key in rolled if rolled[key][2] or rolled[key][0] or rolled[key][1]
    ):
        if instant is None or key in seen:
            continue
        if start_dt <= instant < end_dt:
            marks.append(_floor_local(instant, bucket, tz))
            seen.add(key)
    marks.sort(key=lambda item: item.astimezone(timezone.utc))

    points = []
    for mark in marks:
        key = _bucket_id(mark)
        input_tokens, output_tokens, total_tokens, request_count = rolled.get(key, (0, 0, 0, 0))
        points.append({
            "bucket_start": key,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "request_count": request_count,
        })
    return {
        "start": start,
        "end": end,
        "bucket": bucket,
        "timezone": str(tz),
        "points": points,
    }


def _exceeds(start: datetime, end: datetime, bucket: str, tz: ZoneInfo, limit: int) -> bool:
    """True when the local bucket walk would emit more than ``limit`` marks."""
    if end <= start:
        return False
    # Coarse spans cannot fit the cap even after DST lengthens a few days.
    span = (_as_utc(end) - _as_utc(start)).total_seconds()
    if bucket == "hour" and span > (limit + 2) * 3600:
        return True
    if bucket == "day" and span > (limit + 2) * 86400:
        return True
    if bucket == "week" and span > (limit + 2) * 7 * 86400:
        return True
    cursor = _floor_local(start, bucket, tz)
    end = _as_utc(end)
    count = 0
    seen: set[str] = set()
    while _as_utc(cursor) < end:
        key = _bucket_id(cursor)
        if key not in seen:
            seen.add(key)
            count += 1
            if count > limit:
                return True
        nxt = _civil_add(cursor, bucket, tz)
        if _as_utc(nxt) <= _as_utc(cursor):
            break
        cursor = nxt
    return False


def _walk(origin: datetime, end: datetime, bucket: str, tz: ZoneInfo) -> list[datetime]:
    """Local bucket boundaries from ``origin`` up to, but not including, ``end``.

    The newest ``MAX_POINTS`` marks are kept when a span is still too wide
    after coarsening (monthly history longer than the cap).
    """
    end = _as_utc(end)
    cursor = origin
    marks: list[datetime] = []
    seen: set[str] = set()
    while _as_utc(cursor) < end:
        key = _bucket_id(cursor)
        if key not in seen:
            seen.add(key)
            marks.append(cursor)
            if len(marks) > MAX_POINTS:
                dropped = marks.pop(0)
                seen.discard(_bucket_id(dropped))
        nxt = _civil_add(cursor, bucket, tz)
        if _as_utc(nxt) <= _as_utc(cursor):
            break
        cursor = nxt
    return marks


def _floor_local(instant: datetime, bucket: str, tz: ZoneInfo) -> datetime:
    local = _as_utc(instant).astimezone(tz)
    naive = local.replace(tzinfo=None, microsecond=0)
    if bucket == "hour":
        naive = naive.replace(minute=0, second=0)
    elif bucket in ("day", "week"):
        naive = naive.replace(hour=0, minute=0, second=0)
        if bucket == "week":
            naive -= timedelta(days=naive.weekday())
    else:
        naive = naive.replace(day=1, hour=0, minute=0, second=0)
    return _localize(naive, tz)


def _civil_add(local: datetime, bucket: str, tz: ZoneInfo) -> datetime:
    naive = local.astimezone(tz).replace(tzinfo=None, microsecond=0)
    if bucket == "hour":
        naive += timedelta(hours=1)
    elif bucket == "day":
        naive += timedelta(days=1)
    elif bucket == "week":
        naive += timedelta(weeks=1)
    else:
        year = naive.year + (1 if naive.month == 12 else 0)
        month = 1 if naive.month == 12 else naive.month + 1
        naive = naive.replace(year=year, month=month, day=1)
    return _localize(naive, tz)


def _instant_after(instant: datetime, bucket: str, tz: ZoneInfo) -> datetime:
    return _as_utc(_civil_add(_floor_local(instant, bucket, tz), bucket, tz))


def _localize(naive: datetime, tz: ZoneInfo) -> datetime:
    """Attach ``tz`` to a wall time, stepping past a DST gap."""
    aware = naive.replace(tzinfo=tz)
    if _wall_time(aware) == naive:
        return aware
    for _ in range(3):
        naive = naive + timedelta(hours=1)
        aware = naive.replace(tzinfo=tz)
        if _wall_time(aware) == naive:
            return aware
    return aware


def _wall_time(aware: datetime) -> datetime:
    return aware.astimezone(timezone.utc).astimezone(aware.tzinfo).replace(tzinfo=None)


def _bucket_id(local_floor: datetime) -> str:
    return _as_utc(local_floor).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_bucket_id(key: str) -> datetime | None:
    try:
        return datetime.strptime(key, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_minute(key: str) -> datetime | None:
    text = key.strip().replace(" ", "T")
    if len(text) < 16:
        return None
    try:
        return datetime.strptime(text[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
