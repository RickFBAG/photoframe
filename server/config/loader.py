"""Utilities for loading and watching runtime configuration files."""

from __future__ import annotations

import logging
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, Generic, Mapping, Optional, Tuple, Type, TypeVar

try:
    import yaml
except Exception as exc:  # pragma: no cover - defensive import guard
    raise RuntimeError("PyYAML is vereist om configuratiebestanden te lezen") from exc

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


logger = logging.getLogger(__name__)


class ConfigError(RuntimeError):
    """Base exception for loader errors."""


class ConfigValidationError(ConfigError):
    """Raised when the configuration on disk is invalid."""

    def __init__(self, message: str, errors: Any) -> None:
        super().__init__(message)
        self.errors = errors


def _model_dump(model: Any, **kwargs: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)  # type: ignore[no-any-return]
    return model.dict(**kwargs)  # type: ignore[no-any-return]


def deep_merge(base: Mapping[str, Any], update: Mapping[str, Any]) -> Dict[str, Any]:
    """Recursively merge ``update`` into ``base`` without mutating either."""

    merged: Dict[str, Any] = deepcopy(dict(base))
    for key, value in update.items():
        if key in merged and isinstance(merged[key], Mapping) and isinstance(value, Mapping):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def normalise_runtime_config_payload(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Ensure legacy keys (pre-nested) are mapped to the new schema structure."""

    data: Dict[str, Any] = deepcopy(dict(raw))
    device = dict(data.get("device") or {})
    widgets = dict(data.get("widgets") or {})

    if "carousel_minutes" in data and "carousel_minutes" not in device:
        device["carousel_minutes"] = data.pop("carousel_minutes")
    if "auto_rotate" in data and "auto_rotate" not in device:
        device["auto_rotate"] = data.pop("auto_rotate")
    if "sleep_start" in data and "sleep_start" not in device:
        device["sleep_start"] = data.pop("sleep_start")
    if "sleep_end" in data and "sleep_end" not in device:
        device["sleep_end"] = data.pop("sleep_end")

    if "default_widget" in data and "default" not in widgets:
        widgets["default"] = data.pop("default_widget")
    if "overrides" not in widgets:
        widgets.setdefault("overrides", {})

    if device:
        data["device"] = device
    if widgets:
        data["widgets"] = widgets

    return data


class YamlConfigLoader(Generic[T]):
    """Load, persist and watch YAML configuration files for runtime changes."""

    def __init__(
        self,
        path: Path,
        model: Type[T],
        poll_interval: float = 2.0,
        log: Optional[logging.Logger] = None,
    ) -> None:
        self.path = path
        self.model = model
        self.poll_interval = max(0.5, float(poll_interval))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[T], None]] = None
        self._last_payload: Optional[Dict[str, Any]] = None
        self._last_mtime: Optional[float] = None
        self._log = log or logger

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def load(self) -> T:
        """Load configuration from disk, merging defaults from the schema."""

        with self._lock:
            config, payload = self._load_from_disk()
            self._last_payload = payload
            self._last_mtime = self._get_mtime()
        return config

    def save(self, config: T) -> None:
        """Persist a configuration model to disk as YAML."""

        payload = _model_dump(config, exclude_unset=False)
        text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(text, encoding="utf-8")
            self._last_payload = deepcopy(payload)
            self._last_mtime = self._get_mtime()

    def start(self, callback: Callable[[T], None]) -> None:
        """Start watching the file for on-disk modifications."""

        with self._lock:
            self._callback = callback
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._watch_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _load_from_disk(self) -> Tuple[T, Dict[str, Any]]:
        defaults = _model_dump(self.model())
        data: Dict[str, Any] = {}
        if self.path.exists():
            try:
                raw = yaml.safe_load(self.path.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                raise ConfigError(f"Kon configuratie niet parseren: {exc}") from exc
            if raw is None:
                raw = {}
            if not isinstance(raw, Mapping):
                raise ConfigError("Configuratiebestand moet een YAML mapping bevatten")
            data = normalise_runtime_config_payload(raw)
        merged = deep_merge(defaults, data)
        try:
            config = self.model(**merged)
        except ValidationError as exc:
            raise ConfigValidationError("Configuratie voldoet niet aan het schema", exc.errors()) from exc
        payload = _model_dump(config, exclude_unset=False)
        return config, payload

    def _get_mtime(self) -> Optional[float]:
        try:
            return self.path.stat().st_mtime
        except FileNotFoundError:
            return None

    def _watch_loop(self) -> None:
        self._log.debug("Start watching %s", self.path)
        while not self._stop.wait(self.poll_interval):
            current_mtime = self._get_mtime()
            with self._lock:
                last_mtime = self._last_mtime
            if current_mtime == last_mtime:
                continue
            try:
                config, payload = self._load_from_disk()
            except ConfigError as exc:
                self._log.warning("Kon runtime-config niet opnieuw laden: %s", exc)
                with self._lock:
                    self._last_mtime = current_mtime
                continue
            callback: Optional[Callable[[T], None]]
            changed = False
            with self._lock:
                if self._last_payload != payload:
                    self._last_payload = deepcopy(payload)
                    self._last_mtime = current_mtime
                    callback = self._callback
                    changed = True
                else:
                    callback = self._callback
                    self._last_mtime = current_mtime
            if changed and callback:
                try:
                    callback(config)
                except Exception:  # pragma: no cover - safeguard user callbacks
                    self._log.exception("Callback voor runtime-config genereerde een fout")
        self._log.debug("Stop watching %s", self.path)


__all__ = [
    "ConfigError",
    "ConfigValidationError",
    "YamlConfigLoader",
    "deep_merge",
    "normalise_runtime_config_payload",
]
