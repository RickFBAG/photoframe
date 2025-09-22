from __future__ import annotations

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import urllib.request

from ..app import JsonResponse, Request, ServerContext

try:  # Python 3.9+
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - fallback for environments without zoneinfo database
    ZoneInfo = None  # type: ignore[assignment]


_CONTEXT: ServerContext | None = None
_DEFAULT_FILENAMES = ("calendar.ics", "calendar.ical", "calendar")
_USER_AGENT = "PhotoframeCalendar/1.0"
_MAX_EVENTS = 50


def register(router, context: ServerContext) -> None:
    global _CONTEXT
    _CONTEXT = context
    router.get("/calendar")(calendar_endpoint)


def calendar_endpoint(request: Request, params: Dict[str, str]) -> JsonResponse:
    limit = _parse_limit(params.get("limit"))
    override_source = params.get("source")
    sources = list(_resolve_sources(override_source))

    if not sources:
        payload = {
            "ok": True,
            "events": [],
            "updated_at": _now_iso(),
            "warnings": ["Geen kalenderbron geconfigureerd."],
        }
        return JsonResponse(payload)

    errors: List[Dict[str, str]] = []
    aggregated: List[dict] = []
    successful_sources = 0

    for source in sources:
        try:
            raw_ics = _load_calendar_source(source)
        except Exception as exc:  # pragma: no cover - depends on external systems
            errors.append({"source": str(source), "error": str(exc)})
            continue

        events = _parse_ics_events(raw_ics)
        successful_sources += 1
        for event in events:
            event["source"] = str(source)
            aggregated.append(event)

    aggregated.sort(key=lambda item: item["start_sort"])
    upcoming = [event for event in aggregated if event["is_upcoming"]]

    if limit is not None:
        upcoming = upcoming[:limit]

    events_payload = [
        {
            "title": event["title"],
            "start": event["start"],
            "end": event["end"],
            "all_day": event["all_day"],
            "location": event["location"],
            "description": event["description"],
            "source": event["source"],
        }
        for event in upcoming
    ]

    payload: Dict[str, object] = {
        "ok": True,
        "events": events_payload,
        "updated_at": _now_iso(),
        "source_count": successful_sources,
    }

    status_code = 200

    if errors:
        payload["warnings"] = errors
        if successful_sources == 0 and not events_payload:
            payload["ok"] = False
            payload["error"] = "Kalender synchronisatie mislukt"
            status_code = 503

    return JsonResponse(payload, status=status_code)


def _parse_limit(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return None
    if limit <= 0:
        return None
    return min(limit, _MAX_EVENTS)


def _resolve_sources(override: str | None) -> Iterable[object]:
    if override:
        override = override.strip()
        if override:
            yield override
            return

    context = _CONTEXT
    if context is not None:
        for attr in ("calendar_sources", "calendar_urls", "calendar_url", "calendar"):
            value = getattr(context, attr, None)
            if not value:
                continue
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    if item:
                        yield item
            else:
                yield value

    env_value = os.getenv("PHOTOFRAEME_CALENDAR_URL")
    if env_value:
        for item in env_value.split(","):
            item = item.strip()
            if item:
                yield item

    if context is not None and hasattr(context, "image_dir"):
        base = Path(getattr(context, "image_dir"))
        for filename in _DEFAULT_FILENAMES:
            candidate = base / filename
            if candidate.exists():
                yield candidate
                break


def _load_calendar_source(source: object) -> str:
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8")
    if isinstance(source, str):
        source = source.strip()
        if source.startswith("http://") or source.startswith("https://"):
            request = urllib.request.Request(source, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(request, timeout=15) as response:  # pragma: no cover - requires network
                charset = response.headers.get_content_charset() or "utf-8"
                data = response.read()
            return data.decode(charset, errors="replace")
        path = Path(source)
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Calendar source not available: {source!r}")


def _parse_ics_events(raw_ics: str) -> List[dict]:
    lines = _unfold_ics_lines(raw_ics)
    events: List[dict] = []
    current: dict | None = None

    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current:
                normalised = _normalise_event(current)
                if normalised is not None:
                    events.append(normalised)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        key_part, value = line.split(":", 1)
        key, params = _split_ics_key(key_part)
        key = key.upper()
        if key in {"SUMMARY", "DESCRIPTION", "LOCATION"}:
            current[key] = _unescape_ics_text(value)
        elif key in {"DTSTART", "DTEND"}:
            current[key] = (value.strip(), params)
        elif key == "UID":
            current[key] = value.strip()

    return events


def _unfold_ics_lines(raw_ics: str) -> List[str]:
    raw_ics = raw_ics.replace("\r\n", "\n").replace("\r", "\n")
    unfolded: List[str] = []
    for line in raw_ics.split("\n"):
        if not line:
            continue
        if line.startswith(" ") or line.startswith("\t"):
            if unfolded:
                unfolded[-1] += line[1:]
        else:
            unfolded.append(line.strip())
    return unfolded


def _split_ics_key(blob: str) -> Tuple[str, Dict[str, str]]:
    parts = blob.split(";")
    key = parts[0]
    params: Dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        param_key, param_value = part.split("=", 1)
        params[param_key.upper()] = param_value
    return key, params


def _normalise_event(data: dict) -> dict | None:
    start_info = data.get("DTSTART")
    if not start_info:
        return None

    start_dt, start_all_day = _parse_ics_datetime(*start_info)
    if start_dt is None:
        return None

    end_dt = None
    end_all_day = start_all_day
    end_info = data.get("DTEND")
    if end_info:
        end_dt, end_all_day = _parse_ics_datetime(*end_info)

    if end_dt is None:
        if start_all_day:
            end_dt = start_dt + timedelta(days=1)
            end_all_day = True
        else:
            end_dt = start_dt

    display_end = _compute_display_end(start_dt, end_dt, start_all_day, end_all_day)

    start_sort = _to_timestamp(start_dt)
    end_sort = _to_timestamp(end_dt)
    now_ts = _to_timestamp(datetime.now(timezone.utc))
    is_upcoming = end_sort >= now_ts

    event = {
        "title": data.get("SUMMARY") or "Onbekende afspraak",
        "description": _clean_optional_text(data.get("DESCRIPTION")),
        "location": _clean_optional_text(data.get("LOCATION")),
        "start": _format_datetime(start_dt, start_all_day),
        "end": _format_datetime(display_end, start_all_day) if display_end is not None else None,
        "all_day": start_all_day,
        "start_sort": start_sort,
        "end_sort": end_sort,
        "is_upcoming": is_upcoming,
    }
    return event


def _parse_ics_datetime(value: str, params: Dict[str, str]) -> Tuple[datetime | None, bool]:
    value = value.strip()
    tzid = params.get("TZID")
    value_type = params.get("VALUE", "").upper()

    if value_type == "DATE" or (len(value) == 8 and value.isdigit()):
        try:
            date_value = datetime.strptime(value, "%Y%m%d")
        except ValueError:
            return None, True
        return date_value.replace(tzinfo=timezone.utc), True

    if value.endswith("Z"):
        try:
            dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ")
        except ValueError:
            return None, False
        return dt.replace(tzinfo=timezone.utc), False

    if len(value) >= 19 and value[-5] in {"+", "-"}:
        base_value = value[:-5]
        offset_sign = 1 if value[-5] == "+" else -1
        try:
            dt = datetime.strptime(base_value, "%Y%m%dT%H%M%S")
            offset_hours = int(value[-4:-2])
            offset_minutes = int(value[-2:])
            delta = timedelta(hours=offset_hours, minutes=offset_minutes)
            if offset_sign < 0:
                delta = -delta
            return dt.replace(tzinfo=timezone(delta)), False
        except ValueError:
            return None, False

    try:
        dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
    except ValueError:
        return None, False

    if tzid and ZoneInfo is not None:
        try:
            tz = ZoneInfo(tzid)
            return dt.replace(tzinfo=tz), False
        except Exception:  # pragma: no cover - depends on system tz database
            pass

    return dt, False


def _compute_display_end(
    start: datetime,
    end: datetime | None,
    start_all_day: bool,
    end_all_day: bool,
) -> datetime | None:
    if end is None:
        return None
    if start_all_day:
        adjusted = end - timedelta(days=1)
        if adjusted.date() > start.date():
            return adjusted
        return None
    if end_all_day:
        return end
    if end > start:
        return end
    return None


def _format_datetime(value: datetime | None, all_day: bool) -> str:
    if value is None:
        return ""
    if all_day:
        return value.date().isoformat()
    return value.isoformat()


def _clean_optional_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    return cleaned or None


def _unescape_ics_text(value: str) -> str:
    value = value.replace("\\n", "\n")
    value = value.replace("\\,", ",")
    value = value.replace("\\;", ";")
    value = value.replace("\\\\", "\\")
    return value.strip()


def _to_timestamp(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.timestamp()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
