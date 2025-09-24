"""Configuration management for the Smart Display application."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Dict, MutableMapping


@dataclass
class CalendarSource:
    """Configuration for a single calendar feed."""

    name: str
    url: str


@dataclass
class AgendaSettings:
    """Settings for the agenda widget."""

    enabled: bool = True
    lookahead_days: int = 3
    max_events: int = 6
    calendars: list[CalendarSource] = field(default_factory=list)


@dataclass
class NewsSettings:
    """Settings for the news widget."""

    enabled: bool = True
    feed_url: str = "https://feeds.bbci.co.uk/news/world/rss.xml"
    max_items: int = 4


@dataclass
class MarketSettings:
    """Settings for the market widget."""

    enabled: bool = True
    symbol: str = "EUNL.AS"
    history_days: int = 5


@dataclass
class DisplaySettings:
    """Hardware display configuration."""

    width: int = 800
    height: int = 480
    rotation: int = 0
    border_colour: str = "white"
    enable_hardware: bool = True
    fallback_image: str = "output/latest.png"


@dataclass
class WebSettings:
    """Configuration for the companion web UI."""

    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080


@dataclass
class AppConfig:
    """Top-level application configuration."""

    refresh_minutes: int = 15
    display: DisplaySettings = field(default_factory=DisplaySettings)
    agenda: AgendaSettings = field(default_factory=AgendaSettings)
    news: NewsSettings = field(default_factory=NewsSettings)
    market: MarketSettings = field(default_factory=MarketSettings)
    web: WebSettings = field(default_factory=WebSettings)


class ConfigManager:
    """Thread-safe configuration loader and writer."""

    def __init__(self, path: Path | str = Path("config/config.json")) -> None:
        self.path = Path(path)
        self._lock = Lock()

    def load(self) -> AppConfig:
        """Load configuration from disk, creating defaults when absent."""

        with self._lock:
            data = self._load_unlocked_dict()
            return _build_config(data)

    def load_dict(self) -> Dict[str, Any]:
        """Load configuration and return it as a plain dictionary."""

        return asdict(self.load())

    def save(self, config: AppConfig) -> None:
        """Persist configuration to disk."""

        with self._lock:
            self._write_unlocked(config)

    def update(self, patch: Dict[str, Any]) -> AppConfig:
        """Apply a patch to the configuration and persist it."""

        with self._lock:
            data = self._load_unlocked_dict()
            _deep_update(data, patch)
            config = _build_config(data)
            self._write_unlocked(config)
            return config

    def _load_unlocked_dict(self) -> Dict[str, Any]:
        if not self.path.exists():
            default = AppConfig()
            self._write_unlocked(default)
            return asdict(default)
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write_unlocked(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")


def _deep_update(base: MutableMapping[str, Any], updates: MutableMapping[str, Any]) -> None:
    for key, value in updates.items():
        if isinstance(value, MutableMapping) and isinstance(base.get(key), MutableMapping):
            _deep_update(base[key], value)
        else:
            base[key] = value


def _build_config(data: MutableMapping[str, Any]) -> AppConfig:
    config = AppConfig()
    config.refresh_minutes = int(data.get("refresh_minutes", config.refresh_minutes))

    _apply_mapping(config.display, data.get("display", {}))
    _apply_mapping(config.news, data.get("news", {}))
    _apply_mapping(config.market, data.get("market", {}))
    _apply_mapping(config.web, data.get("web", {}))

    agenda_data = dict(data.get("agenda", {}))
    calendars = []
    for item in agenda_data.pop("calendars", []):
        if isinstance(item, MutableMapping):
            calendars.append(
                CalendarSource(
                    name=str(item.get("name", "")),
                    url=str(item.get("url", "")),
                )
            )
    _apply_mapping(config.agenda, agenda_data)
    config.agenda.calendars = calendars

    return config


def _apply_mapping(target: Any, overrides: MutableMapping[str, Any]) -> None:
    for key, value in overrides.items():
        if hasattr(target, key):
            setattr(target, key, value)


__all__ = [
    "AgendaSettings",
    "AppConfig",
    "CalendarSource",
    "ConfigManager",
    "DisplaySettings",
    "MarketSettings",
    "NewsSettings",
    "WebSettings",
]
