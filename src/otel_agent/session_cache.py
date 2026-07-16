"""Session cache for sticky routing.

Caches session→provider mappings with TTL to pin multi-turn
conversations to the same provider.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass


@dataclass
class SessionEntry:
    """A cached session routing decision."""
    provider_name: str
    tier: str
    timestamp: float


class SessionCache:
    """Cache for session-sticky routing decisions.

    Default TTL: 30 minutes. Automatically cleans up expired entries
    at most once per 60 seconds on set().
    """

    def __init__(self, ttl_minutes: float = 30.0) -> None:
        self.ttl_seconds = ttl_minutes * 60
        self._cache: dict[str, SessionEntry] = {}
        self._last_cleanup: float = 0

    def _make_key(self, session_id: str | None, messages: list[dict]) -> str:
        """Create a cache key from session ID or message fingerprint."""
        if session_id:
            return f"header:{session_id}"
        # Hash first user message for fingerprint
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    fingerprint = content[:100]
                    return f"hash:{hashlib.sha256(fingerprint.encode()).hexdigest()[:32]}"
        return "default"

    def get(self, session_id: str | None, messages: list[dict]) -> SessionEntry | None:
        """Look up a cached session routing decision."""
        key = self._make_key(session_id, messages)
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.monotonic() - entry.timestamp > self.ttl_seconds:
            del self._cache[key]
            return None
        return entry

    def set(
        self,
        session_id: str | None,
        messages: list[dict],
        provider_name: str,
        tier: str,
    ) -> None:
        """Cache a session routing decision."""
        key = self._make_key(session_id, messages)
        self._cache[key] = SessionEntry(
            provider_name=provider_name,
            tier=tier,
            timestamp=time.monotonic(),
        )
        # Throttled cleanup: at most once per 60 seconds
        now = time.monotonic()
        if now - self._last_cleanup > 60:
            self._last_cleanup = now
            self.cleanup()

    def clear(self) -> None:
        """Clear all cached sessions."""
        self._cache.clear()

    def cleanup(self) -> int:
        """Remove expired entries. Returns number of entries removed."""
        now = time.monotonic()
        expired = [
            key for key, entry in self._cache.items()
            if now - entry.timestamp > self.ttl_seconds
        ]
        for key in expired:
            del self._cache[key]
        return len(expired)
