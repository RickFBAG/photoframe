from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional


@dataclass(slots=True)
class CacheEntry:
    """Single cache entry stored by one of the cache backends."""

    namespace: str
    key: str
    payload: Any
    metadata: MutableMapping[str, Any]
    created_at: float
    expires_at: Optional[float]

    def is_expired(self, now: Optional[float] = None) -> bool:
        """Return ``True`` if the entry has expired."""

        if self.expires_at is None:
            return False
        if now is None:
            import time

            now = time.time()
        return now >= self.expires_at


@dataclass(slots=True)
class MemoryCacheConfig:
    enabled: bool = True
    max_items: int = 128
    default_ttl: Optional[int] = 300

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "MemoryCacheConfig":
        payload = dict(data or {})
        enabled = bool(payload.get("enabled", True))
        max_items = int(payload.get("max_items", 128))
        default_ttl = payload.get("default_ttl", payload.get("ttl", 300))
        if default_ttl is not None:
            default_ttl = int(default_ttl)
        return cls(enabled=enabled, max_items=max_items, default_ttl=default_ttl)


@dataclass(slots=True)
class FilesCacheConfig:
    enabled: bool = True
    directory: Path | None = None
    default_ttl: Optional[int] = 900

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any] | None,
        base_dir: Path,
        config_dir: Path,
    ) -> "FilesCacheConfig":
        payload = dict(data or {})
        enabled = bool(payload.get("enabled", True))
        directory_value = payload.get("directory")
        directory: Path | None
        if directory_value:
            directory = Path(directory_value)
            if not directory.is_absolute():
                # Relative paths are resolved against the YAML config location first,
                # and fall back to the image directory.
                directory = (config_dir / directory).resolve()
        else:
            directory = (base_dir / "cache" / "png").resolve()
        default_ttl = payload.get("default_ttl", payload.get("ttl", 900))
        if default_ttl is not None:
            default_ttl = int(default_ttl)
        return cls(enabled=enabled, directory=directory, default_ttl=default_ttl)


@dataclass(slots=True)
class SqliteCacheConfig:
    enabled: bool = True
    path: Path | None = None
    default_ttl: Optional[int] = 86400

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any] | None,
        base_dir: Path,
        config_dir: Path,
    ) -> "SqliteCacheConfig":
        payload = dict(data or {})
        enabled = bool(payload.get("enabled", True))
        path_value = payload.get("path") or payload.get("file")
        path: Path | None
        if path_value:
            path = Path(path_value)
            if not path.is_absolute():
                path = (config_dir / path).resolve()
        else:
            path = (base_dir / "cache" / "metadata.sqlite").resolve()
        default_ttl = payload.get("default_ttl", payload.get("ttl", 86400))
        if default_ttl is not None:
            default_ttl = int(default_ttl)
        return cls(enabled=enabled, path=path, default_ttl=default_ttl)


@dataclass(slots=True)
class CacheSettings:
    memory: MemoryCacheConfig
    files: FilesCacheConfig
    sqlite: SqliteCacheConfig

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any] | None,
        base_dir: Path,
        config_dir: Path,
    ) -> "CacheSettings":
        payload = dict(data or {})
        memory_cfg = MemoryCacheConfig.from_mapping(payload.get("memory"))
        files_cfg = FilesCacheConfig.from_mapping(payload.get("files"), base_dir, config_dir)
        sqlite_cfg = SqliteCacheConfig.from_mapping(payload.get("sqlite"), base_dir, config_dir)
        return cls(memory=memory_cfg, files=files_cfg, sqlite=sqlite_cfg)


__all__ = [
    "CacheEntry",
    "CacheSettings",
    "FilesCacheConfig",
    "MemoryCacheConfig",
    "SqliteCacheConfig",
]
