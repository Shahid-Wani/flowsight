"""TTL cache for enrichment lookups.

Bounded cache with per-entry expiry: entries older than ``ttl`` are
dropped on access, and when the cache is full the oldest entries are
evicted. Prevents unbounded growth on long-running collectors.
"""

import time
from typing import Any


class TTLCache:
    """Dict cache with per-entry TTL and max-size eviction."""

    def __init__(self, ttl: float, max_size: int = 10_000):
        self.ttl = ttl
        self.max_size = max_size
        self._data: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        """Return the cached value, or None if missing/expired."""
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() >= expires_at:
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        """Store a value, evicting expired/oldest entries if full."""
        if key not in self._data and len(self._data) >= self.max_size:
            self._evict()
        self._data[key] = (value, time.monotonic() + self.ttl)

    def _evict(self) -> None:
        now = time.monotonic()
        expired = [key for key, (_, expires_at) in self._data.items() if expires_at <= now]
        for key in expired:
            del self._data[key]

        if len(self._data) >= self.max_size:
            drop_count = max(1, len(self._data) // 10)
            for key in list(self._data)[:drop_count]:
                del self._data[key]

    def clear(self) -> None:
        """Remove all entries."""
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)
