"""Abstract base class for storage backends.

Every storage backend must subclass :class:`StorageBackend` and implement
all eight abstract methods.  The factory :func:`create_storage` instantiates
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
        format: str | None = None,
    ) -> None:
        """Insert a single request record."""

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
    def get_requests_since(self, last_id: int) -> list[dict]:
        """Return requests with ``id > last_id``, ordered by id ascending.

        Used by the SSE live-feed endpoint.
        """

    @abstractmethod
    def get_max_id(self) -> int:
        """Return the current maximum request id, or 0 if the table is empty."""

    @abstractmethod
    def get_all_filtered(
        self, search: str = "", method: str = "", status: int = 0
    ) -> list[dict]:
        """Return **all** matching requests (no pagination).

        Used for CSV/JSON export.
        """

    @abstractmethod
    def get_usage_summary(self, start: str, end: str) -> dict:
        """Return completed request usage for a UTC half-open range."""

    @abstractmethod
    def close(self) -> None:
        """Release database resources."""
