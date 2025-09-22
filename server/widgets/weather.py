from __future__ import annotations

import asyncio
import datetime as dt
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import httpx
import yaml
from PIL import Image, ImageDraw, ImageFont

from . import WidgetBase, WidgetError, WidgetField
from .cache import TTLCache
from .renderer_helpers import (
    ForecastEntry,
    apply_atkinson_texture,
    apply_floyd_steinberg_palette,
    create_canvas,
    default_palette,
    draw_forecast_panel,
    draw_location_marker,
    draw_map,
    draw_stale_overlay,
    draw_temperature_block,
    draw_text_box,
    draw_weather_icon,
)

CACHE_TTL_SECONDS = 15 * 60
MAX_RETRY_ATTEMPTS = 3
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 8.0
CONFIG_ENV_VAR = "PHOTOFREME_WEATHER_CONFIG"


@dataclass
class ProviderConfig:
    endpoint: str
    forecast_days: int
    timezone: str
    daily: Sequence[str]


@dataclass
class LocationConfig:
    name: str
    latitude: float
    longitude: float


@dataclass
class UnitsConfig:
    temperature: str
    wind: str


@dataclass
class WeatherConfig:
    location: LocationConfig
    units: UnitsConfig
    provider: ProviderConfig


@dataclass
class ForecastDay:
    date: dt.date
    temp_min: float
    temp_max: float
    code: int
    icon: str

    @property
    def label(self) -> str:
        return self.date.strftime("%a")


@dataclass
class WeatherSnapshot:
    temperature: float
    weather_code: int
    icon: str
    description: str
    windspeed: Optional[float]
    forecast: List[ForecastDay]
    fetched_at: dt.datetime


class WeatherServiceError(RuntimeError):
    pass


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise WeatherServiceError(f"Configuratiebestand {path} heeft een ongeldig formaat")
    return data


def _deep_merge(base: Dict[str, Any], extra: Mapping[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = dict(base)
    for key, value in extra.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(dict(result[key]), value)
        else:
            result[key] = value
    return result


def _config_paths(custom_path: Optional[Path]) -> List[Path]:
    paths: List[Path] = []
    default_path = Path(__file__).with_name("weather.default.yaml")
    override_env = os.getenv(CONFIG_ENV_VAR)
    if custom_path is not None:
        paths.append(custom_path)
    if override_env:
        paths.append(Path(override_env))
    candidate = Path(__file__).with_name("weather.yaml")
    if candidate.exists():
        paths.append(candidate)
    paths.append(default_path)
    return paths


def _load_config(custom_path: Optional[Path] = None) -> WeatherConfig:
    merged: Dict[str, Any] = {}
    for path in reversed(_config_paths(custom_path)):
        if path.exists():
            merged = _deep_merge(merged, _load_yaml(path))
    try:
        location_raw = merged.get("location", {})
        location = LocationConfig(
            name=str(location_raw.get("name") or "Onbekende locatie"),
            latitude=float(location_raw.get("latitude", 0.0)),
            longitude=float(location_raw.get("longitude", 0.0)),
        )
        units_raw = merged.get("units", {})
        units = UnitsConfig(
            temperature=str(units_raw.get("temperature", "celsius")),
            wind=str(units_raw.get("wind", "km/h")),
        )
        provider_raw = merged.get("provider", {})
        daily = provider_raw.get("daily") or ["temperature_2m_max", "temperature_2m_min", "weathercode"]
        provider = ProviderConfig(
            endpoint=str(provider_raw.get("endpoint")),
            forecast_days=int(provider_raw.get("forecast_days", 4)),
            timezone=str(provider_raw.get("timezone", "auto")),
            daily=tuple(daily),
        )
    except (TypeError, ValueError) as exc:
        raise WeatherServiceError(f"Ongeldige configuratie: {exc}") from exc

    if not provider.endpoint:
        raise WeatherServiceError("Geen endpoint geconfigureerd voor de weerprovider")

    return WeatherConfig(location=location, units=units, provider=provider)


WEATHER_ICON_MAP: Dict[int, str] = {
    0: "sun",
    1: "sun",
    2: "sun",
    3: "cloud",
    45: "cloud",
    48: "cloud",
    51: "rain",
    53: "rain",
    55: "rain",
    56: "rain",
    57: "rain",
    61: "rain",
    63: "rain",
    65: "rain",
    66: "rain",
    67: "rain",
    71: "snow",
    73: "snow",
    75: "snow",
    77: "snow",
    80: "rain",
    81: "rain",
    82: "rain",
    85: "snow",
    86: "snow",
    95: "storm",
    96: "storm",
    99: "storm",
}

WEATHER_DESCRIPTIONS: Dict[str, str] = {
    "sun": "Zonnig",
    "cloud": "Bewolkt",
    "rain": "Regen",
    "snow": "Sneeuw",
    "storm": "Onweer",
}


def _map_icon(code: int) -> str:
    return WEATHER_ICON_MAP.get(code, "cloud")


class WeatherWidget(WidgetBase):
    def __init__(self, config_path: Optional[Path] = None) -> None:
        super().__init__(
            slug="weather",
            name="Weerkaart",
            description="Toont actuele temperatuur en een korte verwachting.",
            fields=[
                WidgetField(
                    name="title",
                    label="Titel",
                    field_type="string",
                    default="",
                    description="Optionele titel bovenaan de kaart.",
                ),
            ],
        )
        self._config_path = config_path
        self._cache: TTLCache[WeatherSnapshot] = TTLCache()

    def render(self, config: Mapping[str, Any], size: tuple[int, int]) -> Image.Image:
        try:
            widget_config = _load_config(self._config_path)
        except WeatherServiceError as exc:
            raise WidgetError(str(exc)) from exc
        title_override = str(config.get("title") or "").strip()
        cache_key = f"{widget_config.location.latitude:.3f},{widget_config.location.longitude:.3f}:{widget_config.units.temperature}"

        cached, cached_stale = self._cache.get(cache_key, CACHE_TTL_SECONDS)
        stale = False
        snapshot: Optional[WeatherSnapshot] = None

        if cached and not cached_stale:
            snapshot = cached
        else:
            try:
                snapshot = self._run_fetch(widget_config)
                self._cache.set(cache_key, snapshot)
            except WeatherServiceError:
                if cached:
                    snapshot = cached
                    stale = True
                else:
                    return self._render_error(size, widget_config.location.name)

        stale = stale or cached_stale
        assert snapshot is not None
        return self._render(widget_config, snapshot, size, title_override or widget_config.location.name, stale)

    def _run_fetch(self, config: WeatherConfig) -> WeatherSnapshot:
        async def _execute() -> WeatherSnapshot:
            return await self._fetch_weather(config)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_execute())

        result: List[WeatherSnapshot] = []
        error: List[BaseException] = []

        def runner() -> None:
            try:
                result.append(asyncio.run(_execute()))
            except BaseException as exc:  # pragma: no cover - defensive guard
                error.append(exc)

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()
        if error:
            exc = error[0]
            if isinstance(exc, WeatherServiceError):
                raise exc
            raise WeatherServiceError(str(exc)) from exc
        if not result:
            raise WeatherServiceError("Kon weergegevens niet ophalen")
        return result[0]

    async def _fetch_weather(self, config: WeatherConfig) -> WeatherSnapshot:
        params = {
            "latitude": config.location.latitude,
            "longitude": config.location.longitude,
            "current_weather": "true",
            "timezone": config.provider.timezone,
            "daily": ",".join(config.provider.daily),
            "forecast_days": max(3, config.provider.forecast_days),
        }
        temp_unit = config.units.temperature.lower()
        if temp_unit in {"fahrenheit", "celsius"}:
            params["temperature_unit"] = temp_unit
        wind_unit = config.units.wind.lower()
        wind_map = {
            "km/h": "kmh",
            "kmh": "kmh",
            "mph": "mph",
            "m/s": "ms",
            "ms": "ms",
        }
        if wind_unit in wind_map:
            params["windspeed_unit"] = wind_map[wind_unit]

        timeout = httpx.Timeout(10.0, connect=5.0, read=10.0)
        delay = INITIAL_BACKOFF_SECONDS
        last_error: Optional[Exception] = None
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(MAX_RETRY_ATTEMPTS):
                try:
                    response = await client.get(config.provider.endpoint, params=params)
                    response.raise_for_status()
                    payload = response.json()
                    return self._parse_payload(payload)
                except (httpx.HTTPError, ValueError, KeyError) as exc:
                    last_error = exc
                    if attempt == MAX_RETRY_ATTEMPTS - 1:
                        break
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, MAX_BACKOFF_SECONDS)
        raise WeatherServiceError(str(last_error or "Onbekende fout bij ophalen weergegevens"))

    def _parse_payload(self, payload: Mapping[str, Any]) -> WeatherSnapshot:
        try:
            current = payload["current_weather"]
            daily = payload["daily"]
        except KeyError as exc:
            raise WeatherServiceError("Onvolledig antwoord van weerprovider") from exc

        try:
            temperature = float(current["temperature"])
            code = int(current.get("weathercode", 0))
            windspeed = float(current.get("windspeed")) if "windspeed" in current else None
            times = daily.get("time", [])
            maxes = daily.get("temperature_2m_max", [])
            mins = daily.get("temperature_2m_min", [])
            codes = daily.get("weathercode", [])
        except (TypeError, ValueError) as exc:
            raise WeatherServiceError("Onverwacht antwoord van weerprovider") from exc

        forecast: List[ForecastDay] = []
        for index, iso_date in enumerate(times[:3]):
            try:
                date = dt.date.fromisoformat(str(iso_date))
            except ValueError:
                continue
            temp_max = float(maxes[index]) if index < len(maxes) else temperature
            temp_min = float(mins[index]) if index < len(mins) else temperature
            code_value = int(codes[index]) if index < len(codes) else code
            forecast.append(
                ForecastDay(
                    date=date,
                    temp_min=temp_min,
                    temp_max=temp_max,
                    code=code_value,
                    icon=_map_icon(code_value),
                )
            )

        snapshot = WeatherSnapshot(
            temperature=temperature,
            weather_code=code,
            icon=_map_icon(code),
            description=WEATHER_DESCRIPTIONS.get(_map_icon(code), "Weer"),
            windspeed=windspeed,
            forecast=forecast,
            fetched_at=dt.datetime.now(),
        )
        return snapshot

    def _render(
        self,
        config: WeatherConfig,
        snapshot: WeatherSnapshot,
        size: tuple[int, int],
        title: str,
        stale: bool,
    ) -> Image.Image:
        palette = default_palette()
        canvas = create_canvas(size, palette)
        draw = ImageDraw.Draw(canvas)
        draw_map(draw, size, palette)
        marker = draw_location_marker(
            draw,
            size,
            palette,
            config.location.latitude,
            config.location.longitude,
        )

        font_large = self._load_font(36)
        font_medium = self._load_font(24)
        font_small = self._load_font(16)

        draw_text_box(draw, title, (20, 16), palette, font_medium)
        draw_temperature_block(draw, (20, 60), snapshot.temperature, config.units.temperature, palette, font_large, font_small, stale)
        draw_weather_icon(draw, (marker[0], marker[1] - 40), snapshot.icon, palette, size=72)

        if snapshot.windspeed is not None:
            wind_text = f"Wind: {snapshot.windspeed:.0f} {config.units.wind}"
            draw_text_box(draw, wind_text, (20, size[1] - font_small.size - 16), palette, font_small)

        forecast_entries = [
            ForecastEntry(
                label=day.label,
                temp_min=day.temp_min,
                temp_max=day.temp_max,
                icon=day.icon,
            )
            for day in snapshot.forecast
        ]
        panel_width = max(size[0] // 3, 160)
        panel_area = (size[0] - panel_width - 20, 40, size[0] - 20, size[1] - 40)
        draw_forecast_panel(draw, panel_area, forecast_entries, palette, font_small, font_medium)

        timestamp = snapshot.fetched_at.strftime("%H:%M")
        draw_text_box(draw, f"Update: {timestamp}", (20, size[1] - font_small.size * 2 - 24), palette, font_small)

        canvas = apply_atkinson_texture(canvas, strength=0.25)
        if stale:
            canvas = canvas.convert("RGBA")
            draw_stale_overlay(canvas, palette)
            canvas = canvas.convert("RGB")

        canvas = apply_floyd_steinberg_palette(canvas, palette)
        return canvas

    def _render_error(self, size: tuple[int, int], location_name: str) -> Image.Image:
        palette = default_palette()
        image = create_canvas(size, palette)
        draw = ImageDraw.Draw(image)
        font = self._load_font(20)
        draw_text_box(draw, f"Geen weerdata voor {location_name}", (20, size[1] // 2 - 10), palette, font)
        image = apply_floyd_steinberg_palette(apply_atkinson_texture(image, 0.3), palette)
        return image

    def _load_font(self, size: int) -> ImageFont.ImageFont:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except Exception:  # pragma: no cover - fallback when font is unavailable
            return ImageFont.load_default()


__all__ = ["WeatherWidget"]
