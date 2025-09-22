from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import ConfigError, YamlConfigLoader, normalise_runtime_config_payload
from .inky import display as inky_display
from .models.config import LayoutConfig, RuntimeConfig, ThemeConfig
from .storage.files import ensure_image_dir
from .widgets import WidgetRegistry, create_default_registry

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080
DEFAULT_IMAGE_DIR = Path("/image")
DEFAULT_ADMIN_RATE_LIMIT = 30
RUNTIME_CONFIG_FILENAME = "config.yaml"


logger = logging.getLogger(__name__)


def _model_dump(model: Any, **kwargs: Any) -> dict:
    """Return a dictionary representation compatible with Pydantic v1/v2."""
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)  # type: ignore[no-any-return]
    return model.dict(**kwargs)  # type: ignore[no-any-return]


class RateLimiter:
    """In-memory request rate limiter (per identifier)."""

    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = max(0, int(limit))
        self.window_seconds = max(1, int(window_seconds))
        self._events: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        if self.limit == 0:
            return
        now = time.monotonic()
        with self._lock:
            timestamps = self._events.setdefault(key, [])
            cutoff = now - self.window_seconds
            # remove expired timestamps
            while timestamps and timestamps[0] < cutoff:
                timestamps.pop(0)
            if len(timestamps) >= self.limit:
                raise RuntimeError("rate-limit-exceeded")
            timestamps.append(now)


@dataclass
class ServerConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    image_dir: Path = DEFAULT_IMAGE_DIR
    admin_token: Optional[str] = None
    rate_limit_per_minute: int = DEFAULT_ADMIN_RATE_LIMIT
    log_path: Optional[Path] = None


@dataclass
class AppState:
    config: ServerConfig
    templates: Jinja2Templates
    image_dir: Path
    static_dir: Path
    runtime_config_loader: YamlConfigLoader[RuntimeConfig]
    runtime_config: RuntimeConfig
    rate_limiter: RateLimiter
    widget_registry: WidgetRegistry
    last_rendered: Optional[str] = None
    scheduler_interval: int = 0
    theme_profile: ThemeConfig = field(default_factory=ThemeConfig)
    layout_profile: LayoutConfig = field(default_factory=LayoutConfig)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.scheduler_interval = self.runtime_config.device.carousel_minutes
        self.theme_profile = self.runtime_config.theme
        self.layout_profile = self.runtime_config.layout
        self._apply_runtime_config(self.runtime_config)

    @property
    def log_file(self) -> Path:
        return self.config.log_path or (self.image_dir / "photoframe.log")

    def set_runtime_config(self, config: RuntimeConfig, persist: bool = True) -> None:
        with self._lock:
            self.runtime_config = config
            self.scheduler_interval = config.device.carousel_minutes
            self.theme_profile = config.theme
            self.layout_profile = config.layout
            if persist:
                self.runtime_config_loader.save(config)
        self._apply_runtime_config(config)

    def _apply_runtime_config(self, config: RuntimeConfig) -> None:
        inky_display.set_rotation(config.device.auto_rotate)
        theme_dump = _model_dump(config.theme)
        layout_dump = _model_dump(config.layout)
        self.templates.env.globals.update(
            runtime_theme=theme_dump,
            runtime_layout=layout_dump,
            runtime_notes=config.notes,
        )


def get_app_state(request: Request) -> AppState:
    state = getattr(request.app.state, "photoframe", None)
    if state is None:
        raise RuntimeError("Application state has not been initialised")
    return state


def create_app(config: Optional[ServerConfig] = None) -> FastAPI:
    config = config or ServerConfig()
    ensure_image_dir(config.image_dir)

    base_dir = Path(__file__).resolve().parent
    template_dir = base_dir / "templates"
    static_dir = base_dir / "static"
    runtime_config_path = config.image_dir / RUNTIME_CONFIG_FILENAME
    loader = YamlConfigLoader(runtime_config_path, RuntimeConfig)
    legacy_json_path = config.image_dir / "config.json"
    if not runtime_config_path.exists() and legacy_json_path.exists():
        try:
            legacy_data = json.loads(legacy_json_path.read_text(encoding="utf-8"))
            if isinstance(legacy_data, dict):
                normalised = normalise_runtime_config_payload(legacy_data)
                legacy_config = RuntimeConfig(**normalised)
                loader.save(legacy_config)
                logger.info("Legacy config.json gemigreerd naar %s", runtime_config_path)
            else:
                logger.warning("Legacy config.json heeft een ongeldig formaat en wordt genegeerd")
        except Exception as exc:
            logger.warning("Kon legacy config.json niet migreren: %s", exc)
    try:
        runtime_config = loader.load()
    except ConfigError as exc:
        logger.warning("Kan configuratie niet laden (%s), gebruik defaults: %s", runtime_config_path, exc)
        runtime_config = RuntimeConfig()
        try:
            loader.save(runtime_config)
        except ConfigError:
            logger.exception("Kon default configuratie niet wegschrijven naar %s", runtime_config_path)

    limiter = RateLimiter(limit=config.rate_limit_per_minute, window_seconds=60)
    templates = Jinja2Templates(directory=str(template_dir))
    registry = create_default_registry()

    app = FastAPI(title="Inky Photoframe", version="2.0.0")
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.state.photoframe = AppState(
        config=config,
        templates=templates,
        image_dir=config.image_dir,
        static_dir=static_dir,
        runtime_config_loader=loader,
        runtime_config=runtime_config,
        rate_limiter=limiter,
        widget_registry=registry,
    )

    loader.start(lambda cfg: app.state.photoframe.set_runtime_config(cfg, persist=False))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, state: AppState = Depends(get_app_state)) -> HTMLResponse:
        return state.templates.TemplateResponse(
            "index.html",
            {"request": request, "title": "Inky Photoframe"},
        )

    @app.get("/index.html", include_in_schema=False)
    async def index_alias(request: Request, state: AppState = Depends(get_app_state)) -> HTMLResponse:
        return await index(request, state)

    from .api import config as config_routes
    from .api import logs, render, status, widgets

    app.include_router(status.router)
    app.include_router(render.router)
    app.include_router(config_routes.router)
    app.include_router(widgets.router)
    app.include_router(logs.router)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        loader.stop()

    return app


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_IMAGE_DIR",
    "DEFAULT_ADMIN_RATE_LIMIT",
    "ServerConfig",
    "AppState",
    "create_app",
    "get_app_state",
    "RateLimiter",
]
