"""Data provider for news headlines."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List
import time

import feedparser
from dateutil import tz

from ..config import NewsSettings


@dataclass(frozen=True)
class NewsHeadline:
    title: str
    source: str | None
    published: datetime | None
    url: str | None


class NewsDataProvider:
    """Fetch concise news headlines."""

    def __init__(self, settings: NewsSettings) -> None:
        self.settings = settings

    def fetch(self) -> List[NewsHeadline]:
        try:
            feed = feedparser.parse(self.settings.feed_url)
        except Exception:
            return []
        items: List[NewsHeadline] = []
        for entry in feed.entries[: self.settings.max_items]:
            published = None
            if getattr(entry, "published_parsed", None):
                published = datetime.fromtimestamp(
                    time.mktime(entry.published_parsed), tz=tz.tzlocal()
                )
            items.append(
                NewsHeadline(
                    title=getattr(entry, "title", "Untitled"),
                    source=getattr(entry, "source", None) or getattr(entry, "publisher", None),
                    published=published,
                    url=getattr(entry, "link", None),
                )
            )
        return items


__all__ = ["NewsDataProvider", "NewsHeadline"]
