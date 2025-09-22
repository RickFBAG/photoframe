from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, MutableMapping, Optional

from .models import CacheEntry, SqliteCacheConfig


class SqliteCache:
    """SQLite-backed cache storing payloads alongside metadata."""

    def __init__(self, config: SqliteCacheConfig) -> None:
        self._enabled = bool(config.enabled and config.path)
        self._path = config.path if config.path else Path(":memory:")
        self._default_ttl = config.default_ttl
        self._lock = threading.Lock()
        if self._enabled:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._initialise()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialise(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    namespace TEXT NOT NULL,
                    cache_key TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    metadata TEXT,
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    PRIMARY KEY(namespace, cache_key)
                )
                """
            )
            conn.commit()

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
        payload: bytes,
        ttl: Optional[int] = None,
        metadata: Optional[MutableMapping[str, Any]] = None,
    ) -> CacheEntry:
        """Persist a payload and return a :class:`CacheEntry`."""

        if not self.enabled:
            raise RuntimeError("SqliteCache is disabled")
        now = time.time()
        expires_at = self._expiry(ttl, now)
        meta_text = json.dumps(dict(metadata or {}))
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO cache_entries(namespace, cache_key, payload, metadata, created_at, expires_at)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (namespace, key, sqlite3.Binary(payload), meta_text, now, expires_at),
                )
                conn.commit()
        return CacheEntry(
            namespace=namespace,
            key=key,
            payload=payload,
            metadata=json.loads(meta_text) if meta_text else {},
            created_at=now,
            expires_at=expires_at,
        )

    def get(self, namespace: str, key: str) -> Optional[CacheEntry]:
        """Return a cached payload or ``None`` when unavailable."""

        if not self.enabled:
            return None
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT payload, metadata, created_at, expires_at FROM cache_entries WHERE namespace=? AND cache_key=?",
                    (namespace, key),
                ).fetchone()
        if row is None:
            return None
        expires_at = row["expires_at"]
        if expires_at is not None and time.time() >= float(expires_at):
            self.invalidate(namespace, key)
            return None
        metadata = json.loads(row["metadata"] or "{}")
        return CacheEntry(
            namespace=namespace,
            key=key,
            payload=row["payload"],
            metadata=metadata,
            created_at=float(row["created_at"]),
            expires_at=float(expires_at) if expires_at is not None else None,
        )

    def read(self, namespace: str, key: str) -> Optional[bytes]:
        """Return the raw payload without metadata lookups."""

        entry = self.get(namespace, key)
        if entry is None:
            return None
        return bytes(entry.payload)

    def invalidate(self, namespace: str, key: Optional[str] = None) -> int:
        """Remove cached entries and return the number of affected rows."""

        if not self.enabled:
            return 0
        with self._lock:
            with self._connect() as conn:
                if key is None:
                    cursor = conn.execute("DELETE FROM cache_entries WHERE namespace=?", (namespace,))
                else:
                    cursor = conn.execute(
                        "DELETE FROM cache_entries WHERE namespace=? AND cache_key=?",
                        (namespace, key),
                    )
                conn.commit()
                return cursor.rowcount or 0

    def cleanup(self) -> int:
        """Purge expired entries and return the number of removed records."""

        if not self.enabled:
            return 0
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute("DELETE FROM cache_entries WHERE expires_at IS NOT NULL AND expires_at <= ?", (time.time(),))
                conn.commit()
                return cursor.rowcount or 0


__all__ = ["SqliteCache"]
