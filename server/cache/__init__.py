from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Generic, Hashable, Optional, TypeVar

__all__ = ["CacheStore", "CacheEntry"]

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """Container for cached values with expiry metadata."""

    value: T
    expires_at: float
    stale_at: float

    def is_fresh(self, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        return self.expires_at > now

    def is_stale(self, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        return self.stale_at > now


class _TTLCache(Generic[T]):
    """A simple in-memory cache with TTL and stale handling."""

    def __init__(self) -> None:
        self._entries: Dict[Hashable, CacheEntry[T]] = {}
        self._locks: Dict[Hashable, asyncio.Lock] = {}

    async def get_or_load(
        self,
        key: Hashable,
        loader: Callable[[], Awaitable[T]],
        ttl: float,
        stale_ttl: float,
    ) -> T:
        now = time.monotonic()
        entry = self._entries.get(key)
        if entry and entry.is_fresh(now):
            return entry.value
        if entry and entry.is_stale(now):
            self._schedule_refresh(key, loader, ttl, stale_ttl)
            return entry.value

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            # Another coroutine might have refreshed the value while we waited.
            entry = self._entries.get(key)
            now = time.monotonic()
            if entry and entry.is_fresh(now):
                return entry.value

            value = await loader()
            self._entries[key] = CacheEntry(
                value=value,
                expires_at=now + max(ttl, 0.0),
                stale_at=now + max(stale_ttl, ttl, 0.0),
            )
            return value

    def clear(self) -> None:
        self._entries.clear()
        self._locks.clear()

    def _schedule_refresh(
        self,
        key: Hashable,
        loader: Callable[[], Awaitable[T]],
        ttl: float,
        stale_ttl: float,
    ) -> None:
        lock = self._locks.setdefault(key, asyncio.Lock())
        if lock.locked():
            # Another coroutine is already refreshing this key.
            return

        async def _refresh() -> None:
            async with lock:
                try:
                    value = await loader()
                except Exception:  # pragma: no cover - defensive logging
                    LOGGER.exception("Failed to refresh cache entry for key %r", key)
                    return
                now = time.monotonic()
                self._entries[key] = CacheEntry(
                    value=value,
                    expires_at=now + max(ttl, 0.0),
                    stale_at=now + max(stale_ttl, ttl, 0.0),
                )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover - no loop available
            # Execute the refresh synchronously when no event loop is running.
            async def _fallback() -> None:
                await _refresh()

            asyncio.run(_fallback())
        else:
            loop.create_task(_refresh())


class CacheStore:
    """Simple container for namespaced TTL caches."""

    def __init__(self) -> None:
        self._caches: Dict[str, _TTLCache[Any]] = {}

    def namespace(self, name: str) -> _TTLCache[Any]:
        cache = self._caches.get(name)
        if cache is None:
            cache = _TTLCache()
            self._caches[name] = cache
        return cache

    async def get_or_load(
        self,
        namespace: str,
        key: Hashable,
        loader: Callable[[], Awaitable[T]],
        ttl: float,
        stale_ttl: float,
    ) -> T:
        cache = self.namespace(namespace)
        return await cache.get_or_load(key, loader, ttl, stale_ttl)

    def clear(self, namespace: Optional[str] = None) -> None:
        if namespace is None:
            self._caches.clear()
            return
        cache = self._caches.get(namespace)
        if cache:
            cache.clear()
