from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, MutableMapping, Optional

from .models import CacheEntry, MemoryCacheConfig


class MemoryCache:
    """An in-memory LRU cache with TTL-aware entries."""

    def __init__(self, config: MemoryCacheConfig) -> None:
        self._enabled = config.enabled and config.max_items > 0
        self._max_items = max(0, config.max_items)
        self._default_ttl = config.default_ttl
        self._entries: "OrderedDict[tuple[str, str], CacheEntry]" = OrderedDict()
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        """Return ``True`` when the cache actively stores items."""

        return self._enabled

    def _expiry(self, ttl: Optional[int], now: float) -> Optional[float]:
        if ttl is None:
            ttl = self._default_ttl
        if ttl is None or ttl <= 0:
            return None
        return now + ttl

    def store(
        self,
        namespace: str,
        key: str,
        payload: Any,
        ttl: Optional[int] = None,
        metadata: Optional[MutableMapping[str, Any]] = None,
    ) -> CacheEntry:
        """Store an item and return the resulting :class:`CacheEntry`."""

        now = time.time()
        entry = CacheEntry(
            namespace=namespace,
            key=key,
            payload=payload,
            metadata=dict(metadata or {}),
            created_at=now,
            expires_at=self._expiry(ttl, now),
        )
        return self.store_entry(entry)

    def store_entry(self, entry: CacheEntry) -> CacheEntry:
        """Insert an existing :class:`CacheEntry` into the cache."""

        if not self.enabled:
            return entry
        with self._lock:
            cache_key = (entry.namespace, entry.key)
            self._entries[cache_key] = entry
            self._entries.move_to_end(cache_key)
            self._evict_unlocked()
        return entry

    def get(self, namespace: str, key: str) -> Optional[CacheEntry]:
        """Return a cached entry or ``None`` when unavailable/expired."""

        if not self.enabled:
            return None
        cache_key = (namespace, key)
        with self._lock:
            entry = self._entries.get(cache_key)
            if entry is None:
                return None
            if entry.is_expired():
                self._entries.pop(cache_key, None)
                return None
            # promote to most recently used
            self._entries.move_to_end(cache_key)
            return entry

    def invalidate(self, namespace: str, key: Optional[str] = None) -> int:
        """Invalidate entries for a namespace and optional key.

        Returns the number of evicted entries.
        """

        if not self.enabled:
            return 0
        removed = 0
        with self._lock:
            if key is not None:
                cache_key = (namespace, key)
                if cache_key in self._entries:
                    self._entries.pop(cache_key, None)
                    removed = 1
            else:
                to_delete = [k for k in self._entries if k[0] == namespace]
                for cache_key in to_delete:
                    self._entries.pop(cache_key, None)
                removed = len(to_delete)
        return removed

    def cleanup(self) -> int:
        """Remove expired entries and return the number of purged items."""

        if not self.enabled:
            return 0
        purged = 0
        now = time.time()
        with self._lock:
            to_delete = [k for k, entry in self._entries.items() if entry.is_expired(now)]
            for cache_key in to_delete:
                self._entries.pop(cache_key, None)
            purged = len(to_delete)
        return purged

    def _evict_unlocked(self) -> None:
        if self._max_items <= 0:
            self._entries.clear()
            return
        while len(self._entries) > self._max_items:
            self._entries.popitem(last=False)


__all__ = ["MemoryCache"]
