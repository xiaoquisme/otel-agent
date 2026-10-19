"""Abstract base class for storage backends.

Every storage backend must subclass :class:`StorageBackend` and implement
all abstract methods.  The factory :func:`create_storage` instantiates
the correct backend based on the ``storage`` config key.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypedDict


class RequestRecord(TypedDict, total=False):
    """Standard shape returned by query methods.

    Fields mirror the ``requests`` table columns.  Query helpers may return
    a subset of these fields depending on the operation.
    """

    id: int
    timestamp: str
    method: str
    url: str
    upstream: str
    request_headers: str | dict
    request_body: str
    response_status: int
    response_headers: str | dict
    response_body: str
    latency_ms: float
    format: str | None
    session_id: str | None
    session_step: str | None


class StorageBackend(ABC):
    """Interface that all storage backends must implement."""

    @abstractmethod
    def initialize(self) -> None:
        """Create tables, sequences, and indexes if they do not exist.

        Must be idempotent — safe to call multiple times.  Typically called
        once after constructing a read-write backend instance.
        """

    @abstractmethod
    def log_request(
        self,
        method: str,
        url: str,
        request_headers: dict,
        request_body: str,
        response_status: int,
        response_headers: dict,
        response_body: str,
        latency_ms: float,
        upstream: str = "",
        model_name: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        cache_read_tokens: int | None = None,
        cache_creation_tokens: int | None = None,
        timestamp: str | None = None,
        format: str | None = None,
        session_id: str | None = None,
        session_step: str | None = None,
    ) -> None:
        """Insert a single request record.

        ``session_id`` and ``session_step`` are optional. Omit them (or pass
        ``None``) and the row is stored with those columns null.
        """

    @abstractmethod
    def get_requests(
        self,
        search: str = "",
        method: str = "",
        status: int = 0,
        cursor: int = 0,
        limit: int = 50,
    ) -> dict:
        """Return paginated requests with cursor-based pagination.

        Returns::

            {
                "data": [...],        # list of request dicts
                "total": int,         # total matching rows
                "cursor": int,        # current cursor value
                "next_cursor": int,   # cursor for next page (0 if no more)
                "has_more": bool,     # whether more pages exist
            }
        """

    @abstractmethod
    def get_request(self, request_id: int) -> dict | None:
        """Return full details for a single request by id.

        ``request_headers`` and ``response_headers`` are returned as
        parsed dicts (JSON-decoded).  Returns ``None`` if not found.
        """

    @abstractmethod
    def get_all_filtered(
        self, search: str = "", method: str = "", status: int = 0
    ) -> list[dict]:
        """Return **all** matching requests (no pagination).

        Used for CSV/JSON export.
        """

    @abstractmethod
    def list_sessions(self, limit: int = 50, offset: int = 0) -> dict:
        """Return recent agent sessions, newest activity first.

        Rows with a null ``session_id`` are not sessions. Each item carries
        request count, token sums, first/last timestamps, and model/upstream
        summaries. Returns ``data``, ``total``, ``offset``, ``limit``, and
        ``has_more``.
        """

    @abstractmethod
    def get_session(self, session_id: str) -> dict | None:
        """Return one session as chronological steps plus rollups.

        Returns ``None`` when no row uses that id. Steps include the fields
        needed for a trajectory (time, endpoint, model, status, latency,
        tokens) and a short request-body preview. Full bodies stay on the
        single-request detail endpoint.
        """

    @abstractmethod
    def get_usage_summary(self, start: str, end: str) -> dict:
        """Return completed request usage for a UTC half-open range."""

    @abstractmethod
    def get_usage_series(
        self,
        start: str,
        end: str,
        bucket: str | None = None,
        tz: str | None = None,
    ) -> dict:
        """Return token totals bucketed across a UTC half-open range.

        ``bucket`` is ``hour``, ``day``, ``week``, ``month``, or ``None``
        to choose from the span. ``tz`` is an IANA timezone name; ``None``
        buckets in UTC.
        """

    @abstractmethod
    def close(self) -> None:
        """Release database resources."""
