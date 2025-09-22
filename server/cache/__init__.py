from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Generic, Hashable, MutableMapping, Optional, TypeVar

from .files import FilesCache
from .memory import MemoryCache
from .models import CacheSettings
from .sqlite import SqliteCache

try:  # pragma: no cover - optional dependency
    import yaml
except Exception:  # pragma: no cover - fall back to JSON-only mode
    yaml = None  # type: ignore[assignment]

__all__ = [
    "CacheEntry",
    "CacheManager",
    "CacheStore",
    "CacheSettings",
    "create_cache_manager",
    "load_cache_settings",
]

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


def _parse_cache_config(text: str, suffix: str) -> Dict[str, Any]:
    """Parse a cache configuration file into a mapping."""

    if not text.strip():
        return {}
    suffix = suffix.lower()
    if suffix == ".json":
        return json.loads(text)
    if suffix in {".yaml", ".yml"}:
        if yaml is None:  # pragma: no cover - dependency missing
            raise RuntimeError("YAML configuration requires PyYAML to be installed")
        data = yaml.safe_load(text)  # type: ignore[no-untyped-call]
        return dict(data or {})
    # Fallback: try JSON first, then YAML when available.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if yaml is None:
            raise
        data = yaml.safe_load(text)  # type: ignore[no-untyped-call]
        return dict(data or {})


def load_cache_settings(path: Path, base_dir: Path) -> CacheSettings:
    """Load :class:`CacheSettings` from ``path``.

    ``path`` may point to a YAML or JSON configuration file. When the file is
    missing or empty the default cache settings are returned.
    """

    config_path = Path(path)
    base_dir = Path(base_dir)
    data: Optional[Dict[str, Any]] = None
    if config_path.exists():
        try:
            text = config_path.read_text(encoding="utf-8")
            data = _parse_cache_config(text, config_path.suffix)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("Failed to load cache configuration from %s", config_path, exc_info=exc)
            data = {}
        config_dir = config_path.parent
    else:
        config_dir = base_dir
    return CacheSettings.from_mapping(data, base_dir=base_dir, config_dir=config_dir)


class CacheManager:
    """Coordinate the individual cache backends used by the application."""

    def __init__(self, memory: MemoryCache, files: FilesCache, sqlite: SqliteCache) -> None:
        self.memory = memory
        self.files = files
        self.sqlite = sqlite

    def store(
        self,
        namespace: str,
        key: str,
        payload: bytes,
        *,
        ttl: Optional[int] = None,
        metadata: Optional[MutableMapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Store a payload in all enabled cache backends."""

        stored: Dict[str, Any] = {}
        meta = dict(metadata or {})
        if self.memory.enabled:
            stored["memory"] = self.memory.store(namespace, key, payload, ttl=ttl, metadata=dict(meta))
        if self.files.enabled:
            stored["files"] = self.files.store(namespace, key, payload, ttl=ttl, metadata=dict(meta))
        if self.sqlite.enabled:
            stored["sqlite"] = self.sqlite.store(namespace, key, payload, ttl=ttl, metadata=dict(meta))
        return stored

    def get(self, namespace: str, key: str) -> Any:
        """Return the first available cache entry for ``namespace``/``key``."""

        if self.memory.enabled:
            entry = self.memory.get(namespace, key)
            if entry is not None:
                return entry
        if self.files.enabled:
            entry = self.files.get(namespace, key)
            if entry is not None:
                return entry
        if self.sqlite.enabled:
            entry = self.sqlite.get(namespace, key)
            if entry is not None:
                return entry
        return None

    def read(self, namespace: str, key: str) -> Optional[bytes]:
        """Return the cached payload as raw bytes if available."""

        if self.memory.enabled:
            entry = self.memory.get(namespace, key)
            if entry is not None:
                payload = entry.payload
                if isinstance(payload, (bytes, bytearray)):
                    return bytes(payload)
        if self.files.enabled:
            payload = self.files.read(namespace, key)
            if payload is not None:
                return payload
        if self.sqlite.enabled:
            payload = self.sqlite.read(namespace, key)
            if payload is not None:
                return payload
        return None

    def invalidate(self, namespace: str, key: Optional[str] = None) -> int:
        """Invalidate cached entries across all backends."""

        removed = 0
        removed += self.memory.invalidate(namespace, key)
        removed += self.files.invalidate(namespace, key)
        removed += self.sqlite.invalidate(namespace, key)
        return removed

    def cleanup(self) -> int:
        """Trigger cleanup/expiry checks on all caches."""

        purged = 0
        purged += self.memory.cleanup()
        purged += self.files.cleanup()
        purged += self.sqlite.cleanup()
        return purged


def create_cache_manager(settings: CacheSettings) -> CacheManager:
    """Construct a :class:`CacheManager` from :class:`CacheSettings`."""

    memory_cache = MemoryCache(settings.memory)
    files_cache = FilesCache(settings.files)
    sqlite_cache = SqliteCache(settings.sqlite)
    return CacheManager(memory_cache, files_cache, sqlite_cache)
