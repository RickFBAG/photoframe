from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib import error as urlerror
from urllib import parse, request

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..app import AppState, get_app_state

router = APIRouter(tags=["weather"])


class WeatherCurrent(BaseModel):
    time: str = Field(..., description="Timestamp of the observation in ISO format")
    temperature: Optional[float] = Field(None, description="Current air temperature")
    windspeed: Optional[float] = Field(None, description="Wind speed in km/h")
    winddirection: Optional[float] = Field(None, description="Wind direction in degrees")
    weathercode: Optional[int] = Field(None, description="Open-Meteo weather condition code")


class WeatherDay(BaseModel):
    date: str = Field(..., description="Date of the forecast day")
    weathercode: Optional[int] = Field(None, description="Open-Meteo weather condition code")
    temperature_max: Optional[float] = Field(None, description="Daily maximum temperature")
    temperature_min: Optional[float] = Field(None, description="Daily minimum temperature")
    precipitation_probability: Optional[float] = Field(
        None, description="Mean precipitation probability in percent"
    )


class WeatherUnits(BaseModel):
    temperature: str = Field(..., description="Unit for temperature values")
    windspeed: str = Field(..., description="Unit for wind speed values")
    precipitation_probability: str = Field(
        "%", description="Unit for precipitation probability"
    )


class WeatherResponse(BaseModel):
    latitude: float
    longitude: float
    location_label: str
    timezone: str
    fetched_at: str
    source: str
    current: WeatherCurrent
    daily: List[WeatherDay]
    units: WeatherUnits


@dataclass
class _WeatherRequest:
    latitude: float
    longitude: float
    days: int

    def cache_key(self) -> tuple[float, float, int]:
        # Reduce cache cardinality by rounding to two decimal places.
        return (round(self.latitude, 2), round(self.longitude, 2), self.days)


async def _fetch_open_meteo(payload: _WeatherRequest) -> Dict[str, Any]:
    params = {
        "latitude": f"{payload.latitude:.4f}",
        "longitude": f"{payload.longitude:.4f}",
        "current_weather": "true",
        "daily": [
            "weathercode",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_probability_mean",
        ],
        "timezone": "auto",
    }
    if payload.days:
        params["forecast_days"] = str(payload.days)

    query = parse.urlencode(params, doseq=True)
    url = f"https://api.open-meteo.com/v1/forecast?{query}"

    def _loader() -> Dict[str, Any]:
        req = request.Request(
            url,
            headers={
                "User-Agent": "photoframe-weather/1.0 (+https://github.com/)",
                "Accept": "application/json",
            },
        )
        with request.urlopen(req, timeout=15) as response:  # type: ignore[arg-type]
            if response.status != 200:
                raise HTTPException(
                    status_code=502,
                    detail="weather-service-error",
                )
            data = response.read()
        try:
            return json.loads(data.decode("utf-8"))
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
            raise HTTPException(status_code=502, detail="invalid-weather-response") from exc

    try:
        return await asyncio.to_thread(_loader)
    except HTTPException:
        raise
    except urlerror.URLError as exc:  # pragma: no cover - network errors
        raise HTTPException(status_code=502, detail="weather-service-unavailable") from exc


def _extract_index(sequence: Optional[List[Any]], index: int) -> Optional[Any]:
    if not sequence:
        return None
    try:
        return sequence[index]
    except (IndexError, TypeError):
        return None


def _normalise_response(payload: _WeatherRequest, data: Dict[str, Any]) -> Dict[str, Any]:
    current_raw = data.get("current_weather") or {}
    daily_raw = data.get("daily") or {}
    daily_units = data.get("daily_units") or {}
    current_units = data.get("current_weather_units") or {}

    times = daily_raw.get("time") or []
    forecast: List[Dict[str, Any]] = []
    for idx, date in enumerate(times):
        forecast.append(
            {
                "date": date,
                "weathercode": _extract_index(daily_raw.get("weathercode"), idx),
                "temperature_max": _extract_index(daily_raw.get("temperature_2m_max"), idx),
                "temperature_min": _extract_index(daily_raw.get("temperature_2m_min"), idx),
                "precipitation_probability": _extract_index(
                    daily_raw.get("precipitation_probability_mean"), idx
                ),
            }
        )

    now = datetime.now(timezone.utc).isoformat()

    return {
        "latitude": data.get("latitude", payload.latitude),
        "longitude": data.get("longitude", payload.longitude),
        "location_label": f"{payload.latitude:.2f}°, {payload.longitude:.2f}°",
        "timezone": data.get("timezone", "UTC"),
        "fetched_at": now,
        "source": "open-meteo.com",
        "current": {
            "time": current_raw.get("time", now),
            "temperature": current_raw.get("temperature"),
            "windspeed": current_raw.get("windspeed"),
            "winddirection": current_raw.get("winddirection"),
            "weathercode": current_raw.get("weathercode"),
        },
        "daily": forecast,
        "units": {
            "temperature": daily_units.get("temperature_2m_max")
            or current_units.get("temperature")
            or "°C",
            "windspeed": current_units.get("windspeed", "km/h"),
            "precipitation_probability": daily_units.get(
                "precipitation_probability_mean", "%"
            ),
        },
    }


async def _load_weather(
    request_payload: _WeatherRequest,
    loader: Callable[[
        _WeatherRequest,
    ], Awaitable[Dict[str, Any]]],
) -> Dict[str, Any]:
    raw = await loader(request_payload)
    return _normalise_response(request_payload, raw)


@router.get("/weather", response_model=WeatherResponse)
async def weather(
    latitude: float = Query(52.37, ge=-90.0, le=90.0),
    longitude: float = Query(4.89, ge=-180.0, le=180.0),
    days: int = Query(5, ge=1, le=14),
    state: AppState = Depends(get_app_state),
) -> WeatherResponse:
    payload = _WeatherRequest(latitude=latitude, longitude=longitude, days=days)

    async def _loader() -> Dict[str, Any]:
        return await _load_weather(payload, _fetch_open_meteo)

    try:
        cached = await state.cache.get_or_load(
            "weather",
            payload.cache_key(),
            _loader,
            ttl=600.0,
            stale_ttl=1800.0,
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=502, detail="weather-unavailable") from exc

    return WeatherResponse(**cached)
