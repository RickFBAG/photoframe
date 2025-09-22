from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.error import URLError
from urllib.request import Request as URLRequest
from urllib.request import urlopen
from xml.etree import ElementTree

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import cache
from .carousel import CarouselState
from .cache import CacheStore
from .inky import display as inky_display
from .models.config import RuntimeConfig
from .storage.files import ensure_image_dir
from .widgets import WidgetRegistry

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080
DEFAULT_IMAGE_DIR = Path("/image")
DEFAULT_ADMIN_RATE_LIMIT = 30
DEFAULT_NEWS_FEEDS: tuple[str, ...] = (
    "https://www.nu.nl/rss/Algemeen",
    "https://tweakers.net/feeds/nieuws.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
)


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


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:  # pragma: no cover - trivial
        if data:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def _strip_tag(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _child_itertext(element: ElementTree.Element, name: str) -> Optional[str]:
    for child in element:
        if _strip_tag(child.tag).lower() == name:
            return "".join(child.itertext()).strip()
    return None


def _child_attr(element: ElementTree.Element, name: str, attribute: str) -> Optional[str]:
    for child in element:
        if _strip_tag(child.tag).lower() == name:
            value = child.get(attribute)
            if value:
                return value.strip()
    return None


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    try:
        parsed = parsedate_to_datetime(text)
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass
    # fallback for ISO 8601
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed_iso = datetime.fromisoformat(text)
        if parsed_iso.tzinfo is None:
            parsed_iso = parsed_iso.replace(tzinfo=timezone.utc)
        return parsed_iso.astimezone(timezone.utc)
    except ValueError:
        return None


def _clean_text(value: Optional[str]) -> str:
    if not value:
        return ""
    stripper = _HTMLStripper()
    try:
        stripper.feed(value)
        stripper.close()
    except Exception:
        return " ".join(value.split())
    cleaned = unescape(stripper.get_text())
    return " ".join(cleaned.split())


def _summarise(text: str, max_length: int = 240) -> str:
    if len(text) <= max_length:
        return text
    truncated = text[: max_length + 1]
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated.rstrip(".,;:-") + "…"


def _parse_rss_feed(root: ElementTree.Element, source_url: str) -> Iterable[dict[str, Any]]:
    channel = None
    for child in root:
        if _strip_tag(child.tag).lower() == "channel":
            channel = child
            break
    if channel is None:
        return []
    source_name = _child_itertext(channel, "title") or source_url
    items: list[dict[str, Any]] = []
    for item in channel:
        if _strip_tag(item.tag).lower() != "item":
            continue
        title = _child_itertext(item, "title") or "(zonder titel)"
        link = _child_itertext(item, "link") or source_url
        description = (
            _child_itertext(item, "description")
            or _child_itertext(item, "summary")
            or ""
        )
        pub = _parse_datetime(
            _child_itertext(item, "pubDate")
            or _child_itertext(item, "published")
            or _child_itertext(item, "updated")
        )
        cleaned = _clean_text(description)
        items.append(
            {
                "title": unescape(title.strip()),
                "link": link.strip(),
                "summary": _summarise(cleaned) if cleaned else "",
                "source": source_name,
                "published_at": pub.isoformat().replace("+00:00", "Z") if pub else None,
            }
        )
    return items


def _parse_atom_feed(root: ElementTree.Element, source_url: str) -> Iterable[dict[str, Any]]:
    source_name = _child_itertext(root, "title") or source_url
    items: list[dict[str, Any]] = []
    for entry in root:
        if _strip_tag(entry.tag).lower() != "entry":
            continue
        title = _child_itertext(entry, "title") or "(zonder titel)"
        link = _child_attr(entry, "link", "href") or _child_itertext(entry, "link") or source_url
        summary = (
            _child_itertext(entry, "summary")
            or _child_itertext(entry, "content")
            or ""
        )
        published = _parse_datetime(
            _child_itertext(entry, "updated")
            or _child_itertext(entry, "published")
        )
        cleaned = _clean_text(summary)
        items.append(
            {
                "title": unescape(title.strip()),
                "link": link.strip(),
                "summary": _summarise(cleaned) if cleaned else "",
                "source": source_name,
                "published_at": published.isoformat().replace("+00:00", "Z") if published else None,
            }
        )
    return items


def _parse_rdf_feed(root: ElementTree.Element, source_url: str) -> Iterable[dict[str, Any]]:
    source_name = _child_itertext(root, "title") or source_url
    items: list[dict[str, Any]] = []
    for item in root.findall(".//{*}item"):
        title = _child_itertext(item, "title") or "(zonder titel)"
        link = _child_itertext(item, "link") or source_url
        summary = (
            _child_itertext(item, "description")
            or _child_itertext(item, "summary")
            or ""
        )
        published = _parse_datetime(
            _child_itertext(item, "date") or _child_itertext(item, "pubDate")
        )
        cleaned = _clean_text(summary)
        items.append(
            {
                "title": unescape(title.strip()),
                "link": link.strip(),
                "summary": _summarise(cleaned) if cleaned else "",
                "source": source_name,
                "published_at": published.isoformat().replace("+00:00", "Z") if published else None,
            }
        )
    return items


def _parse_feed_document(payload: str, source_url: str) -> list[dict[str, Any]]:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return []
    tag = _strip_tag(root.tag).lower()
    if tag == "rss":
        return list(_parse_rss_feed(root, source_url))
    if tag == "feed":
        return list(_parse_atom_feed(root, source_url))
    # some feeds use <rdf:RDF> for RSS 1.0
    if tag in {"rdf", "rdf:rdf"}:
        return list(_parse_rdf_feed(root, source_url))
    return []


def _fetch_feed_sync(url: str, timeout: int = 10) -> list[dict[str, Any]]:
    request = URLRequest(url, headers={"User-Agent": "Photoframe/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            data = response.read()
            encoding = response.headers.get_content_charset("utf-8")
    except (URLError, TimeoutError, ValueError):
        return []
    try:
        text = data.decode(encoding or "utf-8", errors="replace")
    except LookupError:
        text = data.decode("utf-8", errors="replace")
    return _parse_feed_document(text, url)


async def _collect_news(urls: Iterable[str]) -> list[dict[str, Any]]:
    loop = asyncio.get_running_loop()
    tasks = [loop.run_in_executor(None, _fetch_feed_sync, url) for url in urls]
    items: list[dict[str, Any]] = []
    for result in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(result, Exception):
            continue
        items.extend(result)
    return items


@dataclass
class ServerConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    image_dir: Path = DEFAULT_IMAGE_DIR
    admin_token: Optional[str] = None
    rate_limit_per_minute: int = DEFAULT_ADMIN_RATE_LIMIT
    log_path: Optional[Path] = None
    cache_config_path: Optional[Path] = None


@dataclass
class AppState:
    """Container for FastAPI state shared across request handlers.

    The caches are configured via a YAML file (``cache.yaml`` by default).
    ``cache_settings`` exposes the normalised configuration while
    ``caches`` provides a convenience API that bundles the in-memory, file
    and SQLite backends for widget render results.
    """

    config: ServerConfig
    templates: Jinja2Templates
    image_dir: Path
    static_dir: Path
    runtime_config_path: Path
    runtime_config: RuntimeConfig
    rate_limiter: RateLimiter
    cache: CacheStore
    widget_registry: WidgetRegistry
    cache_config_path: Path
    cache_settings: cache.CacheSettings
    caches: cache.CacheManager
    carousel: CarouselState
    last_rendered: Optional[str] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def log_file(self) -> Path:
        return self.config.log_path or (self.image_dir / "photoframe.log")

    def set_runtime_config(self, config: RuntimeConfig) -> None:
        """Persist a new :class:`RuntimeConfig` to disk."""

        with self._lock:
            self.runtime_config = config
            payload = json.dumps(_model_dump(config), indent=2, ensure_ascii=False)
            self.runtime_config_path.write_text(payload, encoding="utf-8")


def get_app_state(request: Request) -> AppState:
    state = getattr(request.app.state, "photoframe", None)
    if state is None:
        raise RuntimeError("Application state has not been initialised")
    return state


def _load_runtime_config(path: Path) -> RuntimeConfig:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return RuntimeConfig(**data)
        except Exception:
            pass
    return RuntimeConfig()


def create_app(config: Optional[ServerConfig] = None) -> FastAPI:
    config = config or ServerConfig()
    ensure_image_dir(config.image_dir)

    base_dir = Path(__file__).resolve().parent
    template_dir = base_dir / "templates"
    static_dir = base_dir / "static"
    runtime_config_path = config.image_dir / "config.json"
    runtime_config = _load_runtime_config(runtime_config_path)

    cache_config_path = config.cache_config_path or (config.image_dir / "cache.yaml")
    if not cache_config_path.is_absolute():
        cache_config_path = (config.image_dir / cache_config_path).resolve()
    cache_settings = cache.load_cache_settings(cache_config_path, base_dir=config.image_dir)
    cache_manager = cache.create_cache_manager(cache_settings)
    carousel_state = CarouselState(minutes=runtime_config.carousel_minutes)

    limiter = RateLimiter(limit=config.rate_limit_per_minute, window_seconds=60)
    templates = Jinja2Templates(directory=str(template_dir))
    cache_store = CacheStore()
    registry = WidgetRegistry(cache=cache_store)

    inky_display.set_rotation(runtime_config.auto_rotate)

    app = FastAPI(title="Inky Photoframe", version="2.0.0")
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.state.photoframe = AppState(
        config=config,
        templates=templates,
        image_dir=config.image_dir,
        static_dir=static_dir,
        runtime_config_path=runtime_config_path,
        runtime_config=runtime_config,
        rate_limiter=limiter,
        cache=cache_store,
        widget_registry=registry,
        cache_config_path=cache_config_path,
        cache_settings=cache_settings,
        caches=cache_manager,
        carousel=carousel_state,
    )

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, state: AppState = Depends(get_app_state)) -> HTMLResponse:
        return state.templates.TemplateResponse(
            "index.html",
            {"request": request, "title": "Inky Photoframe"},
        )

    @app.get("/index.html", include_in_schema=False)
    async def index_alias(request: Request, state: AppState = Depends(get_app_state)) -> HTMLResponse:
        return await index(request, state)

    @app.get("/news", response_class=JSONResponse)
    async def news_endpoint(
        keywords: Optional[str] = None,
        limit: int = 12,
        hours: int = 72,
        state: AppState = Depends(get_app_state),
    ) -> JSONResponse:
        feeds = DEFAULT_NEWS_FEEDS

        async def _load() -> dict[str, Any]:
            items = await _collect_news(feeds)
            return {
                "items": items,
                "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }

        cached_bundle = await state.cache.get_or_load(
            "news",
            feeds,
            _load,
            ttl=300.0,
            stale_ttl=900.0,
        )

        if isinstance(cached_bundle, dict):
            raw_items_seq = cached_bundle.get("items") or []
        else:  # pragma: no cover - defensive fallback
            raw_items_seq = []
        raw_items = list(raw_items_seq)

        keyword_set = (
            {token.strip().lower() for token in (keywords or "").split(",") if token.strip()}
        )
        now = datetime.now(timezone.utc)
        fetched_at = (
            _parse_datetime(cached_bundle.get("fetched_at"))
            if isinstance(cached_bundle, dict)
            else None
        ) or now
        cutoff = now - timedelta(hours=max(0, hours)) if hours > 0 else None

        filtered: list[dict[str, Any]] = []
        for item in raw_items:
            published_iso = item.get("published_at")
            published_dt = _parse_datetime(published_iso)
            if cutoff and published_dt and published_dt < cutoff:
                continue
            if keyword_set:
                haystack = " ".join(
                    [item.get("title", ""), item.get("summary", ""), item.get("source", "")]
                ).lower()
                if not any(keyword in haystack for keyword in keyword_set):
                    continue
            filtered.append({**item, "published_at": published_iso})

        fallback_time = datetime(1970, 1, 1, tzinfo=timezone.utc)
        filtered.sort(
            key=lambda entry: _parse_datetime(entry.get("published_at")) or fallback_time,
            reverse=True,
        )

        limit = max(1, min(int(limit or 0) or 12, 50))
        limited = filtered[:limit]

        payload = {
            "feeds": list(feeds),
            "generated_at": fetched_at.isoformat().replace("+00:00", "Z"),
            "keywords": sorted(keyword_set),
            "item_count": len(limited),
            "items": limited,
        }
        return JSONResponse(payload)

    from .api import config as config_routes
    from .api import logs, render, status, weather, widgets

    app.include_router(status.router)
    app.include_router(render.router)
    app.include_router(config_routes.router)
    app.include_router(weather.router)
    app.include_router(widgets.router)
    app.include_router(logs.router)

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
