from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Any, MutableMapping, Optional

from .models import CacheEntry, FilesCacheConfig


class FilesCache:
    """On-disk cache storing PNG payloads segregated by namespace."""

    def __init__(self, config: FilesCacheConfig) -> None:
        self._enabled = bool(config.enabled and config.directory)
        self._directory = config.directory if config.directory else Path(".")
        self._default_ttl = config.default_ttl
        self._lock = threading.Lock()
        if self._enabled:
            self._directory.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _expiry(self, ttl: Optional[int], now: float) -> Optional[float]:
        if ttl is None:
            ttl = self._default_ttl
        if ttl is None or ttl <= 0:
            return None
        return now + ttl

    def _slugify(self, name: str) -> str:
        slug = re.sub(r"\s+", "-", name.strip().lower())
        slug = re.sub(r"[^a-z0-9._-]", "-", slug)
        return slug or "default"

    def _filename(self, key: str) -> str:
        slug = self._slugify(key)[:40]
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
        return f"{slug}-{digest}.png"

    def _path_for(self, namespace: str, key: str) -> Path:
        ns_dir = self._directory / self._slugify(namespace)
        return ns_dir / self._filename(key)

    def store(
        self,
        namespace: str,
        key: str,
        payload: bytes,
        ttl: Optional[int] = None,
        metadata: Optional[MutableMapping[str, Any]] = None,
    ) -> CacheEntry:
        """Persist a PNG payload and return a :class:`CacheEntry`."""

        if not self.enabled:
            raise RuntimeError("FilesCache is disabled")
        now = time.time()
        target = self._path_for(namespace, key)
        with self._lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            meta = {
                "namespace": namespace,
                "key": key,
                "created_at": now,
                "expires_at": self._expiry(ttl, now),
                "metadata": dict(metadata or {}),
            }
            meta_path = Path(str(target) + ".json")
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
        return CacheEntry(
            namespace=namespace,
            key=key,
            payload=target,
            metadata=dict(metadata or {}),
            created_at=now,
            expires_at=meta["expires_at"],
        )

    def get(self, namespace: str, key: str) -> Optional[CacheEntry]:
        """Return a :class:`CacheEntry` if present and not expired."""

        if not self.enabled:
            return None
        target = self._path_for(namespace, key)
        meta_path = Path(str(target) + ".json")
        if not target.exists() or not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {
                "created_at": target.stat().st_mtime,
                "expires_at": None,
                "metadata": {},
            }
        expires_at = meta.get("expires_at")
        if expires_at is not None and time.time() >= float(expires_at):
            self.invalidate(namespace, key)
            return None
        return CacheEntry(
            namespace=namespace,
            key=key,
            payload=target,
            metadata=dict(meta.get("metadata") or {}),
            created_at=float(meta.get("created_at", target.stat().st_mtime)),
            expires_at=float(expires_at) if expires_at is not None else None,
        )

    def read(self, namespace: str, key: str) -> Optional[bytes]:
        """Return the raw PNG payload if still cached."""

        entry = self.get(namespace, key)
        if entry is None:
            return None
        path: Path = entry.payload  # type: ignore[assignment]
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None

    def invalidate(self, namespace: str, key: Optional[str] = None) -> int:
        """Remove cached files for the given namespace/key."""

        if not self.enabled:
            return 0
        removed = 0
        with self._lock:
            if key is not None:
                target = self._path_for(namespace, key)
                removed += self._unlink(target)
                removed += self._unlink(Path(str(target) + ".json"))
            else:
                ns_dir = self._directory / self._slugify(namespace)
                if ns_dir.exists():
                    for child in ns_dir.glob("*"):
                        removed += self._unlink(child)
                    try:
                        ns_dir.rmdir()
                    except OSError:
                        pass
        return removed

    def cleanup(self) -> int:
        """Purge expired entries from disk."""

        if not self.enabled:
            return 0
        purged = 0
        now = time.time()
        for meta_path in self._directory.glob("**/*.png.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                meta = {}
            expires_at = meta.get("expires_at")
            if expires_at is not None and now >= float(expires_at):
                png_path = Path(str(meta_path)[:-5])  # strip .json
                purged += self._unlink(png_path)
                purged += self._unlink(meta_path)
        return purged

    def _unlink(self, path: Path) -> int:
        try:
            path.unlink()
            return 1
        except FileNotFoundError:
            return 0


__all__ = ["FilesCache"]
