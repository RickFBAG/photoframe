from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional

from .files import FilesCache
from .memory import MemoryCache
from .models import CacheEntry, CacheSettings
from .sqlite import SqliteCache


def _read_yaml(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        if not text.strip():
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:  # pragma: no cover - error path
            raise RuntimeError(f"Cannot parse cache configuration {path!s}: install PyYAML") from exc
    else:
        data = yaml.safe_load(text)  # type: ignore[assignment]
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise TypeError(f"Cache configuration must be a mapping, got {type(data).__name__}")
    return data


def load_cache_settings(config_path: Path, base_dir: Path) -> CacheSettings:
    """Load cache settings from ``config_path`` or return defaults."""

    if not config_path.is_absolute():
        config_path = (base_dir / config_path).resolve()
    if config_path.exists():
        data = _read_yaml(config_path)
        config_dir = config_path.parent
    else:
        data = {}
        config_dir = base_dir
    return CacheSettings.from_mapping(data, base_dir=base_dir, config_dir=config_dir)


@dataclass(slots=True)
class CacheManager:
    """High-level convenience wrapper combining all cache backends."""

    memory: Optional[MemoryCache] = None
    files: Optional[FilesCache] = None
    sqlite: Optional[SqliteCache] = None

    def store(
        self,
        namespace: str,
        key: str,
        payload: bytes,
        ttl: Optional[int] = None,
        metadata: Optional[MutableMapping[str, Any]] = None,
    ) -> Optional[CacheEntry]:
        """Store a payload across the configured caches."""

        entry: Optional[CacheEntry] = None
        if self.memory and self.memory.enabled:
            entry = self.memory.store(namespace, key, payload, ttl=ttl, metadata=metadata)
        if self.sqlite and self.sqlite.enabled:
            entry = self.sqlite.store(namespace, key, payload, ttl=ttl, metadata=metadata)
        return entry

    def store_png(
        self,
        namespace: str,
        key: str,
        payload: bytes,
        ttl: Optional[int] = None,
        metadata: Optional[MutableMapping[str, Any]] = None,
    ) -> Optional[CacheEntry]:
        """Store a PNG payload in memory, on disk and optionally SQLite."""

        meta = dict(metadata or {})
        if self.files and self.files.enabled:
            file_entry = self.files.store(namespace, key, payload, ttl=ttl, metadata=meta)
            meta.setdefault("file_path", str(file_entry.payload))
        entry = None
        if self.sqlite and self.sqlite.enabled:
            entry = self.sqlite.store(namespace, key, payload, ttl=ttl, metadata=meta)
        if self.memory and self.memory.enabled:
            entry = self.memory.store(namespace, key, payload, ttl=ttl, metadata=meta)
        return entry

    def get(self, namespace: str, key: str) -> Optional[CacheEntry]:
        """Return a cached payload if available."""

        if self.memory and self.memory.enabled:
            entry = self.memory.get(namespace, key)
            if entry is not None:
                return entry
        if self.sqlite and self.sqlite.enabled:
            entry = self.sqlite.get(namespace, key)
            if entry is not None and self.memory and self.memory.enabled:
                self.memory.store_entry(entry)
                return entry
            if entry is not None:
                return entry
        return None

    def get_png_bytes(self, namespace: str, key: str) -> Optional[bytes]:
        """Return PNG bytes from cache, falling back to disk when required."""

        entry = self.get(namespace, key)
        if entry is not None:
            payload = entry.payload
            if isinstance(payload, (bytes, bytearray, memoryview)):
                return bytes(payload)
        if self.files and self.files.enabled:
            file_entry = self.files.get(namespace, key)
            if file_entry is None:
                return None
            path = file_entry.payload
            if not isinstance(path, Path):
                return None
            try:
                data = path.read_bytes()
            except FileNotFoundError:
                self.files.invalidate(namespace, key)
                return None
            if self.memory and self.memory.enabled:
                memory_entry = CacheEntry(
                    namespace=namespace,
                    key=key,
                    payload=data,
                    metadata=dict(file_entry.metadata),
                    created_at=file_entry.created_at,
                    expires_at=file_entry.expires_at,
                )
                self.memory.store_entry(memory_entry)
            return data
        return None

    def invalidate(self, namespace: str, key: Optional[str] = None) -> None:
        """Invalidate all cache layers for a namespace/key."""

        if self.memory and self.memory.enabled:
            self.memory.invalidate(namespace, key)
        if self.sqlite and self.sqlite.enabled:
            self.sqlite.invalidate(namespace, key)
        if self.files and self.files.enabled:
            self.files.invalidate(namespace, key)

    def cleanup(self) -> dict[str, int]:
        """Run cleanup on all caches and return a purge summary."""

        summary: dict[str, int] = {}
        if self.memory and self.memory.enabled:
            summary["memory"] = self.memory.cleanup()
        if self.sqlite and self.sqlite.enabled:
            summary["sqlite"] = self.sqlite.cleanup()
        if self.files and self.files.enabled:
            summary["files"] = self.files.cleanup()
        return summary


def create_cache_manager(settings: CacheSettings) -> CacheManager:
    """Instantiate caches based on the provided :class:`CacheSettings`."""

    memory = MemoryCache(settings.memory) if settings.memory.enabled else None
    files = FilesCache(settings.files) if settings.files.enabled else None
    sqlite = SqliteCache(settings.sqlite) if settings.sqlite.enabled else None
    return CacheManager(memory=memory, files=files, sqlite=sqlite)


__all__ = [
    "CacheEntry",
    "CacheManager",
    "CacheSettings",
    "create_cache_manager",
    "load_cache_settings",
]
