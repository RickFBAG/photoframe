from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Generic, MutableMapping, Optional, Tuple, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """Represents a cached value along with the moment it was stored."""

    value: T
    timestamp: float


class TTLCache(Generic[T]):
    """Simple thread-safe in-memory TTL cache used by widgets."""

    def __init__(self) -> None:
        self._store: MutableMapping[str, CacheEntry[T]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, ttl_seconds: float) -> Tuple[Optional[T], bool]:
        """Return a cached value and whether it is stale.

        When the key is missing the value will be ``None`` and ``stale`` will be
        ``True`` so callers know the cache does not contain usable data.
        """

        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None, True
            stale = (now - entry.timestamp) > ttl_seconds
            return entry.value, stale

    def set(self, key: str, value: T) -> None:
        with self._lock:
            self._store[key] = CacheEntry(value=value, timestamp=time.monotonic())

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
