from __future__ import annotations

import asyncio
import datetime as dt
import threading
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

import httpx
from PIL import Image, ImageDraw, ImageFont

from .base import WidgetDefinition, WidgetError, WidgetField

try:  # pragma: no cover - Python < 3.9 fallback
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - fallback when zoneinfo is unavailable
    ZoneInfo = None  # type: ignore[assignment]

LOCAL_TZ = dt.datetime.now().astimezone().tzinfo or dt.timezone.utc
DEFAULT_TTL = 600
DEFAULT_MAX_ITEMS = 5
DEFAULT_SOON_MINUTES = 30
BACKOFF_BASE = 1.0
BACKOFF_MAX_ATTEMPTS = 3
MAX_FEED_EVENTS = 256
FETCH_BUFFER = 8
HTTP_TIMEOUT = 12.0

WEEKDAY_NAMES = ["ma", "di", "wo", "do", "vr", "za", "zo"]
WEEKDAY_LONG = [
    "maandag",
    "dinsdag",
    "woensdag",
    "donderdag",
    "vrijdag",
    "zaterdag",
    "zondag",
]
MONTH_NAMES = [
    "jan",
    "feb",
    "mrt",
    "apr",
    "mei",
    "jun",
    "jul",
    "aug",
    "sep",
    "okt",
    "nov",
    "dec",
]
MONTH_NAMES_LONG = [
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
]


@dataclass(frozen=True)
class NormalizedEvent:
    """Representation of an event normalized to the local timezone."""

    title: str
    start: dt.datetime
    end: dt.datetime
    all_day: bool
    location: str | None = None
    description: str | None = None

    def end_inclusive_date(self) -> dt.date:
        """Return the inclusive end date for all-day events."""

        if self.all_day:
            end = self.end
            if end.time() == dt.time.min:
                end = end - dt.timedelta(days=1)
            return end.date()
        return self.end.date()

    def is_multi_day(self) -> bool:
        return self.start.date() != self.end_inclusive_date()

    def occurs_on(self, day: dt.date) -> bool:
        start = self.start.date()
        end = self.end_inclusive_date()
        return start <= day <= end

    def is_ongoing(self, moment: dt.datetime) -> bool:
        if self.all_day:
            return self.occurs_on(moment.date())
        return self.start <= moment < self.end

    def starts_within(self, moment: dt.datetime, threshold: dt.timedelta) -> bool:
        if self.all_day:
            if self.occurs_on(moment.date()) and moment.time() < dt.time(8, 0):
                # highlight all-day events early in the morning
                return True
            return False
        return moment <= self.start <= moment + threshold


@dataclass
class CacheEntry:
    events: List[NormalizedEvent]
    fetched_at: dt.datetime


@dataclass
class FeedResult:
    events: List[NormalizedEvent]
    fetched_at: dt.datetime
    from_cache: bool
    offline: bool


@dataclass
class CalendarFetchResult:
    events: List[NormalizedEvent]
    total_available: int
    used_cache: bool
    offline: bool
    stale: bool
    fetched_at: Optional[dt.datetime]


class CalendarFetchError(WidgetError):
    pass


_CACHE: Dict[str, CacheEntry] = {}
_CACHE_LOCK = threading.RLock()


def _font_candidates(weight: str) -> Iterable[str]:
    if weight == "bold":
        return (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        )
    return (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    )


def _load_font(size: int, weight: str = "regular") -> ImageFont.ImageFont:
    for path in _font_candidates(weight):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


@dataclass(frozen=True)
class Badge:
    text: str
    fill: str
    text_color: str


@dataclass(frozen=True)
class DisplayEvent:
    title: str
    subtitle: str
    detail_lines: List[str]
    badge: Optional[Badge]
    accent: str


class Surface:
    def __init__(self, size: tuple[int, int], background: str = "white", padding: int = 40) -> None:
        self.width, self.height = size
        self.image = Image.new("RGB", size, background)
        self.draw = ImageDraw.Draw(self.image)
        self.padding = padding
        self.cursor_y = padding
        self.font_title = _load_font(48, "bold")
        self.font_subtitle = _load_font(26)
        self.font_meta = _load_font(24)
        self.font_meta_small = _load_font(22)
        self.font_event = _load_font(32, "bold")
        self.font_badge = _load_font(22, "bold")
        self.font_empty = _load_font(28)
        self.line_spacing = 6

    def _text_size(self, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
        bbox = self.draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def draw_header(self, title: str, subtitle: Optional[str], badges: List[Badge]) -> None:
        x = self.padding
        y = self.cursor_y
        self.draw.text((x, y), title, fill="black", font=self.font_title)
        title_height = self._text_size(title, self.font_title)[1]
        block_height = title_height
        if subtitle:
            sub_y = y + title_height + 8
            self.draw.text((x, sub_y), subtitle, fill="#333333", font=self.font_subtitle)
            block_height = sub_y + self._text_size(subtitle, self.font_subtitle)[1] - y
        badge_x = self.width - self.padding
        for badge in reversed(badges):
            text_w, text_h = self._text_size(badge.text, self.font_badge)
            bw = text_w + 18
            bh = text_h + 10
            badge_x -= bw
            self.draw.rounded_rectangle(
                [badge_x, y, badge_x + bw, y + bh], radius=10, fill=badge.fill
            )
            self.draw.text(
                (badge_x + 9, y + (bh - text_h) // 2), badge.text, fill=badge.text_color, font=self.font_badge
            )
            badge_x -= 10
            block_height = max(block_height, bh)
        self.cursor_y += block_height + 24

    def draw_event(self, item: DisplayEvent) -> bool:
        max_height = self.height - self.padding
        text_lines: List[tuple[str, ImageFont.ImageFont, str]] = []
        text_lines.append((item.title, self.font_event, "black"))
        text_lines.append((item.subtitle, self.font_meta, "#111111"))
        for detail in item.detail_lines:
            text_lines.append((detail, self.font_meta_small, "#333333"))

        heights = [self._text_size(text, font)[1] for text, font, _ in text_lines]
        block_height = sum(heights)
        if text_lines:
            block_height += self.line_spacing * (len(text_lines) - 1)
        block_height = block_height + 18

        if self.cursor_y + block_height > max_height:
            return False

        accent_width = 8
        self.draw.rectangle(
            [self.padding, self.cursor_y, self.padding + accent_width, self.cursor_y + block_height],
            fill=item.accent,
        )
        text_x = self.padding + accent_width + 14
        text_y = self.cursor_y + 8
        for (text, font, color), height in zip(text_lines, heights):
            self.draw.text((text_x, text_y), text, fill=color, font=font)
            text_y += height + self.line_spacing

        if item.badge:
            text_w, text_h = self._text_size(item.badge.text, self.font_badge)
            bw = text_w + 18
            bh = text_h + 8
            badge_x = self.width - self.padding - bw
            badge_y = self.cursor_y + 8
            self.draw.rounded_rectangle(
                [badge_x, badge_y, badge_x + bw, badge_y + bh], radius=8, fill=item.badge.fill
            )
            self.draw.text(
                (badge_x + 9, badge_y + (bh - text_h) // 2),
                item.badge.text,
                fill=item.badge.text_color,
                font=self.font_badge,
            )

        self.cursor_y += block_height + 16
        return True

    def draw_empty(self, text: str) -> None:
        text_w, text_h = self._text_size(text, self.font_empty)
        x = (self.width - text_w) // 2
        y = (self.height - text_h) // 2
        self.draw.text((x, y), text, fill="#333333", font=self.font_empty)

    def draw_more(self, remaining: int) -> None:
        text = f"+{remaining} extra"
        text_w, text_h = self._text_size(text, self.font_meta_small)
        x = self.width - self.padding - text_w
        y = self.height - self.padding - text_h
        self.draw.text((x, y), text, fill="#333333", font=self.font_meta_small)


async def fetch(
    feed_urls: Sequence[str], *, ttl: int = DEFAULT_TTL, max_events: int = DEFAULT_MAX_ITEMS
) -> CalendarFetchResult:
    if not feed_urls:
        raise CalendarFetchError("Geen kalenderfeed opgegeven.")

    async with httpx.AsyncClient(follow_redirects=True, timeout=HTTP_TIMEOUT) as client:
        tasks = [_fetch_single(client, url, ttl) for url in feed_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    feed_results: List[FeedResult] = []
    errors: List[str] = []
    for result in results:
        if isinstance(result, FeedResult):
            feed_results.append(result)
        elif isinstance(result, CalendarFetchError):
            errors.append(str(result))
        elif isinstance(result, Exception):
            errors.append(str(result))

    if not feed_results:
        raise CalendarFetchError(errors[0] if errors else "Kon de kalender niet laden.")

    combined_events: List[NormalizedEvent] = []
    used_cache = False
    offline = False
    stale = False
    fetched_at = None
    for result in feed_results:
        combined_events.extend(result.events)
        used_cache = used_cache or result.from_cache
        offline = offline or result.offline
        stale = stale or result.offline
        if fetched_at is None or result.fetched_at > fetched_at:
            fetched_at = result.fetched_at

    if errors:
        offline = True
        stale = True

    now = dt.datetime.now(LOCAL_TZ)
    filtered: List[NormalizedEvent] = []
    seen = set()
    for event in sorted(combined_events, key=lambda item: (item.start, item.end)):
        key = (event.title, event.start, event.end)
        if key in seen:
            continue
        seen.add(key)
        if _should_include(event, now):
            filtered.append(event)
        if len(filtered) >= max_events + FETCH_BUFFER:
            break

    total_available = len(filtered)
    limited = filtered[:max_events]

    return CalendarFetchResult(
        events=limited,
        total_available=total_available,
        used_cache=used_cache,
        offline=offline,
        stale=stale,
        fetched_at=fetched_at,
    )


async def _fetch_single(client: httpx.AsyncClient, url: str, ttl: int) -> FeedResult:
    now = dt.datetime.now(dt.timezone.utc)
    with _CACHE_LOCK:
        cached = _CACHE.get(url)
        if cached and (now - cached.fetched_at).total_seconds() < ttl:
            return FeedResult(list(cached.events), cached.fetched_at, from_cache=True, offline=False)

    last_error: Exception | None = None
    for attempt in range(BACKOFF_MAX_ATTEMPTS):
        try:
            response = await client.get(url, headers={"Accept": "text/calendar"})
            response.raise_for_status()
            events = _parse_ics(response.text)
            normalized = _normalize_events(events)
            fetched_at = dt.datetime.now(dt.timezone.utc)
            with _CACHE_LOCK:
                _CACHE[url] = CacheEntry(events=normalized, fetched_at=fetched_at)
            return FeedResult(normalized, fetched_at, from_cache=False, offline=False)
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt < BACKOFF_MAX_ATTEMPTS - 1:
                await asyncio.sleep(BACKOFF_BASE * (2**attempt))
        except Exception as exc:  # pragma: no cover - unexpected parsing failure
            last_error = exc
            break

    if cached:
        return FeedResult(list(cached.events), cached.fetched_at, from_cache=True, offline=True)

    raise CalendarFetchError(f"Kan feed niet laden: {url} ({last_error})")


def _should_include(event: NormalizedEvent, now: dt.datetime) -> bool:
    if event.is_ongoing(now):
        return True
    if event.all_day:
        return event.start.date() >= now.date()
    return event.start >= now


def _parse_ics(data: str) -> List[dict[str, tuple[str, dict[str, str]]]]:
    lines = _unfold_lines(data)
    events: List[dict[str, tuple[str, dict[str, str]]]] = []
    current: dict[str, tuple[str, dict[str, str]]] | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
        elif current is not None:
            name, params, value = _split_property(line)
            current[name] = (value, params)
    return events[:MAX_FEED_EVENTS]


def _unfold_lines(data: str) -> List[str]:
    lines: List[str] = []
    for raw in data.splitlines():
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw.strip())
    return lines


def _split_property(line: str) -> tuple[str, dict[str, str], str]:
    if ":" not in line:
        return line.upper(), {}, ""
    prop, value = line.split(":", 1)
    name, _, param_str = prop.partition(";")
    params: dict[str, str] = {}
    if param_str:
        for part in param_str.split(";"):
            if "=" in part:
                key, val = part.split("=", 1)
                params[key.upper()] = val
    return name.upper(), params, value


def _normalize_events(
    raw_events: Iterable[dict[str, tuple[str, dict[str, str]]]]
) -> List[NormalizedEvent]:
    normalized: List[NormalizedEvent] = []
    for item in raw_events:
        try:
            normalized_event = _normalize_event(item)
        except Exception:
            continue
        if normalized_event:
            normalized.append(normalized_event)
    return normalized


def _normalize_event(item: dict[str, tuple[str, dict[str, str]]]) -> Optional[NormalizedEvent]:
    start_data = item.get("DTSTART")
    if not start_data:
        return None
    start_value, start_params = start_data
    start, all_day = _parse_datetime(start_value, start_params)

    end_data = item.get("DTEND")
    if end_data:
        end_value, end_params = end_data
        end, _ = _parse_datetime(end_value, end_params)
    else:
        end = start + (dt.timedelta(days=1) if all_day else dt.timedelta(hours=1))

    if end <= start:
        end = start + (dt.timedelta(days=1) if all_day else dt.timedelta(hours=1))

    title = _clean_text(item.get("SUMMARY", ("(zonder titel)", {}))[0]) or "(zonder titel)"
    location_raw = item.get("LOCATION", ("", {}))[0]
    description_raw = item.get("DESCRIPTION", ("", {}))[0]
    location = _clean_text(location_raw) or None
    description = _clean_text(description_raw) or None
    return NormalizedEvent(title=title, start=start, end=end, all_day=all_day, location=location, description=description)


def _parse_datetime(value: str, params: Optional[Mapping[str, str]] = None) -> tuple[dt.datetime, bool]:
    params = {k.upper(): v for k, v in (params or {}).items()}
    if params.get("VALUE", "").upper() == "DATE" or len(value) == 8:
        date = dt.datetime.strptime(value[:8], "%Y%m%d").date()
        start = dt.datetime.combine(date, dt.time.min, tzinfo=LOCAL_TZ)
        return start, True

    tzinfo = LOCAL_TZ
    tzid = params.get("TZID")
    if tzid and ZoneInfo is not None:
        try:
            tzinfo = ZoneInfo(tzid)
        except Exception:
            tzinfo = LOCAL_TZ

    if value.endswith("Z"):
        dt_value = _parse_datetime_value(value[:-1])
        if dt_value.tzinfo is None:
            dt_value = dt_value.replace(tzinfo=dt.timezone.utc)
        local = dt_value.astimezone(LOCAL_TZ)
        return local, False

    dt_value = _parse_datetime_value(value)
    if dt_value.tzinfo is not None:
        local = dt_value.astimezone(LOCAL_TZ)
    else:
        local = dt_value.replace(tzinfo=tzinfo).astimezone(LOCAL_TZ)
    return local, False


def _parse_datetime_value(value: str) -> dt.datetime:
    for fmt in ("%Y%m%dT%H%M%S%z", "%Y%m%dT%H%M%z", "%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            return dt.datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return dt.datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return dt.datetime.fromisoformat(value)


def _clean_text(value: str) -> str:
    if not value:
        return ""
    return (
        value.replace("\\n", " ")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .strip()
    )


def fetch_sync(feed_urls: Sequence[str], *, ttl: int, max_events: int) -> CalendarFetchResult:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(fetch(feed_urls, ttl=ttl, max_events=max_events))

    result_container: list[CalendarFetchResult] = []
    error_container: list[BaseException] = []

    def runner() -> None:
        try:
            outcome = asyncio.run(fetch(feed_urls, ttl=ttl, max_events=max_events))
            result_container.append(outcome)
        except BaseException as exc:  # pragma: no cover - thread propagation
            error_container.append(exc)

    thread = threading.Thread(target=runner, name="calendar-fetch", daemon=True)
    thread.start()
    thread.join()
    if error_container:
        exc = error_container[0]
        if isinstance(exc, WidgetError):
            raise exc
        raise CalendarFetchError(str(exc)) from exc
    if not result_container:
        raise CalendarFetchError("Onbekende fout bij kalenderophaal")
    return result_container[0]


def _format_header_date(moment: dt.datetime) -> str:
    weekday = WEEKDAY_LONG[moment.weekday()]
    month = MONTH_NAMES_LONG[moment.month - 1]
    return f"{weekday} {moment.day} {month} {moment.year}"


def _format_day(moment: dt.datetime, *, reference: Optional[dt.datetime] = None) -> str:
    ref = reference or dt.datetime.now(LOCAL_TZ)
    weekday = WEEKDAY_NAMES[moment.weekday()]
    month = MONTH_NAMES[moment.month - 1]
    suffix = f" {moment.year}" if moment.year != ref.year else ""
    return f"{weekday} {moment.day} {month}{suffix}"


def _format_time(moment: dt.datetime) -> str:
    return moment.strftime("%H:%M")


def _build_display_event(
    event: NormalizedEvent, now: dt.datetime, *, soon_threshold: dt.timedelta
) -> DisplayEvent:
    subtitle = _format_day(event.start, reference=now)
    detail_lines: List[str] = []
    badge: Badge | None = None
    accent = "#222222"

    if event.all_day:
        accent = "#555555"
        if event.is_multi_day():
            end = event.end_inclusive_date()
            end_date = dt.datetime.combine(end, dt.time.min, tzinfo=LOCAL_TZ)
            detail_lines.append(f"Hele dag t/m {_format_day(end_date, reference=now)}")
        else:
            detail_lines.append("Hele dag")
        if event.occurs_on(now.date()):
            badge = Badge(text="Vandaag", fill="#333333", text_color="#ffffff")
            accent = "#333333"
        else:
            badge = Badge(text="Hele dag", fill="#bbbbbb", text_color="#000000")
    else:
        start_time = _format_time(event.start)
        end_time = _format_time(event.end)
        if event.start.date() == event.end.date():
            detail_lines.append(f"{start_time} – {end_time}")
        else:
            detail_lines.append(f"{start_time} – {end_time} ({_format_day(event.end, reference=now)})")

        if event.is_ongoing(now):
            badge = Badge(text="Nu", fill="#000000", text_color="#ffffff")
            accent = "#000000"
        elif event.starts_within(now, soon_threshold):
            badge = Badge(text="Bijna", fill="#111111", text_color="#ffffff")
            accent = "#111111"

    if event.location:
        detail_lines.append(event.location)

    return DisplayEvent(title=event.title, subtitle=subtitle, detail_lines=detail_lines, badge=badge, accent=accent)


class CalendarWidget(WidgetDefinition):
    def __init__(self) -> None:
        super().__init__(
            slug="calendar",
            name="Agenda",
            description="Toont komende afspraken uit een of meerdere iCal feeds.",
            fields=[
                WidgetField(
                    name="feeds",
                    label="iCal URL(s)",
                    field_type="text",
                    required=True,
                    description="Meerdere URL's scheiden met komma of nieuwe regel.",
                ),
                WidgetField(
                    name="title",
                    label="Titel",
                    field_type="string",
                    default="Agenda",
                ),
                WidgetField(
                    name="max_items",
                    label="Maximale items",
                    field_type="number",
                    default=DEFAULT_MAX_ITEMS,
                ),
                WidgetField(
                    name="ttl",
                    label="Cache (seconden)",
                    field_type="number",
                    default=DEFAULT_TTL,
                ),
                WidgetField(
                    name="soon_minutes",
                    label="Bijna-drempel (minuten)",
                    field_type="number",
                    default=DEFAULT_SOON_MINUTES,
                ),
            ],
        )

    def render(self, config: Mapping[str, object], size: tuple[int, int]) -> Image.Image:
        feeds_value = config.get("feeds") or config.get("feed")
        feed_urls = _parse_feed_urls(feeds_value)
        if not feed_urls:
            raise WidgetError("Geef minstens één iCal-feed op.")

        title = str(config.get("title") or "Agenda")
        max_items = _coerce_positive_int(config.get("max_items"), DEFAULT_MAX_ITEMS, minimum=1, maximum=15)
        ttl = _coerce_positive_int(config.get("ttl"), DEFAULT_TTL, minimum=60, maximum=86400)
        soon_minutes = _coerce_positive_int(
            config.get("soon_minutes"), DEFAULT_SOON_MINUTES, minimum=5, maximum=240
        )

        try:
            result = fetch_sync(feed_urls, ttl=ttl, max_events=max_items + FETCH_BUFFER)
        except WidgetError as exc:
            surface = Surface(size)
            surface.draw_header(title, None, [])
            surface.draw_empty(str(exc))
            return surface.image

        now = dt.datetime.now(LOCAL_TZ)
        subtitle = _format_header_date(now)
        if result.fetched_at is not None:
            updated_local = result.fetched_at.astimezone(LOCAL_TZ)
            subtitle = f"{subtitle} · update {_format_time(updated_local)}"

        badges: List[Badge] = []
        if result.offline:
            badges.append(Badge(text="Offline", fill="#000000", text_color="#ffffff"))
        if result.used_cache:
            cache_text = "Cache (stale)" if (result.offline or result.stale) else "Cache"
            badges.append(Badge(text=cache_text, fill="#666666", text_color="#ffffff"))

        surface = Surface(size)
        surface.draw_header(title, subtitle, badges)

        soon_threshold = dt.timedelta(minutes=soon_minutes)
        display_events = [
            _build_display_event(event, now, soon_threshold=soon_threshold)
            for event in result.events[:max_items]
        ]

        drawn = 0
        for event_item in display_events:
            if surface.draw_event(event_item):
                drawn += 1
            else:
                break

        if drawn == 0:
            surface.draw_empty("Geen komende afspraken")
        else:
            remaining = max(result.total_available - drawn, 0)
            if remaining > 0:
                surface.draw_more(remaining)

        return surface.image


def _parse_feed_urls(value: object) -> List[str]:
    urls: List[str] = []
    if isinstance(value, str):
        for part in value.replace(";", "\n").replace(",", "\n").splitlines():
            part = part.strip()
            if part:
                urls.append(part)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            if item:
                urls.append(str(item).strip())
    return [url for url in urls if url]


def _coerce_positive_int(value: object, default: int, *, minimum: int, maximum: int) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except Exception:
        return default
    number = max(minimum, number)
    number = min(maximum, number)
    return number
