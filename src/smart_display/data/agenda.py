"""Data provider for agenda events."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

import requests
from dateutil import tz
from ics import Calendar

from ..config import AgendaSettings, CalendarSource


@dataclass(frozen=True)
class AgendaEvent:
    """An individual agenda entry."""

    start: datetime
    end: datetime
    title: str
    location: str | None = None


class AgendaDataProvider:
    """Fetch agenda entries from configured calendars."""

    def __init__(self, settings: AgendaSettings) -> None:
        self.settings = settings

    def fetch(self) -> List[AgendaEvent]:
        now = datetime.now(tz.tzlocal())
        cutoff = now + timedelta(days=self.settings.lookahead_days)
        events: List[AgendaEvent] = []
        for source in self.settings.calendars:
            if not source.url:
                continue
            events.extend(self._fetch_calendar(source, now, cutoff))
        events.sort(key=lambda item: item.start)
        return events[: self.settings.max_events]

    def _fetch_calendar(
        self,
        source: CalendarSource,
        now: datetime,
        cutoff: datetime,
    ) -> List[AgendaEvent]:
        try:
            response = requests.get(source.url, timeout=15)
            response.raise_for_status()
        except requests.RequestException:
            return []

        try:
            calendar = Calendar(response.text)
        except Exception:
            return []

        items: List[AgendaEvent] = []
        for event in calendar.events:
            start = self._coerce_datetime(event.begin, default_tz=tz.tzlocal())
            if start is None or start < now or start > cutoff:
                continue
            end_dt = self._coerce_datetime(event.end, default_tz=tz.tzlocal()) or start
            items.append(
                AgendaEvent(
                    start=start,
                    end=end_dt,
                    title=(event.name or "Untitled"),
                    location=(event.location or None),
                )
            )
        return items

    @staticmethod
    def _coerce_datetime(value, default_tz):
        if value is None:
            return None
        if hasattr(value, "to"):
            value = value.to(default_tz)
            return value.datetime
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=default_tz)
            return value
        return None


__all__ = ["AgendaDataProvider", "AgendaEvent"]
