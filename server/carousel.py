"""Utilities to track the carousel rendering state.

This module mirrors the lightweight bookkeeping that existed in the
legacy Flask implementation.  The FastAPI server keeps an instance of
``CarouselState`` on the application state object so request handlers can
inspect or update the most recent carousel activity without having to
recreate the logic in multiple places.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import threading


@dataclass
class CarouselSnapshot:
    """Serialisable view of the carousel state."""

    running: bool
    minutes: int
    current_index: int
    current_file: Optional[str]
    next_switch_at: Optional[str]


class CarouselState:
    """Thread-safe container for carousel metadata.

    The class keeps track of whether the carousel is running, which file
    is currently displayed and when the next automatic switch is
    scheduled.  The numerical index is maintained primarily for
    compatibility with the legacy dashboard which displayed the position
    of the current image in the gallery.
    """

    def __init__(self, minutes: int = 5) -> None:
        self._lock = threading.RLock()
        self._running = False
        self._minutes = max(1, int(minutes))
        self._current_index = -1
        self._current_file: Optional[str] = None
        self._next_switch_at: Optional[datetime] = None

    def set_minutes(self, minutes: int) -> None:
        """Persist the configured carousel interval."""

        with self._lock:
            self._minutes = max(1, int(minutes))

    def set_running(
        self,
        running: bool,
        *,
        minutes: Optional[int] = None,
        next_switch_at: Optional[datetime] = None,
    ) -> None:
        """Update the running state and optional scheduling metadata."""

        with self._lock:
            self._running = running
            if minutes is not None:
                self._minutes = max(1, int(minutes))
            self._next_switch_at = next_switch_at if running else None

    def set_current(self, filename: Optional[str], index: int = -1) -> None:
        """Record which file is currently displayed."""

        with self._lock:
            if filename is None:
                self._current_file = None
                self._current_index = -1
            else:
                self._current_file = filename
                self._current_index = int(index)

    def snapshot(
        self,
        files: Iterable[Path],
        *,
        last_rendered: Optional[str] = None,
        default_minutes: Optional[int] = None,
    ) -> CarouselSnapshot:
        """Return a consistent snapshot of the carousel state.

        The snapshot validates that the stored ``current_file`` still
        exists in ``files`` and falls back to ``last_rendered`` when the
        carousel has not yet been initialised for the FastAPI runtime.
        """

        file_list = list(files)
        file_names = [path.name for path in file_list]

        with self._lock:
            minutes = self._minutes
            running = self._running
            current_index = self._current_index
            current_file = self._current_file

            # Synchronise the current index with the actual gallery
            # contents.  When the state stems from a legacy render the
            # ``last_rendered`` value helps to prime the state so the
            # dashboard shows the correct image name straight away.
            if current_file and current_file in file_names:
                if not (0 <= current_index < len(file_names)) or file_names[current_index] != current_file:
                    current_index = file_names.index(current_file)
                    self._current_index = current_index
            elif last_rendered and last_rendered in file_names:
                current_file = last_rendered
                current_index = file_names.index(last_rendered)
                self._current_file = current_file
                self._current_index = current_index
            else:
                current_file = None
                current_index = -1
                self._current_file = None
                self._current_index = -1

            if default_minutes is not None and not running:
                minutes = max(1, int(default_minutes))
                self._minutes = minutes

            next_switch = (
                self._next_switch_at.isoformat(timespec="seconds")
                if self._next_switch_at
                else None
            )

        return CarouselSnapshot(
            running=running,
            minutes=minutes,
            current_index=current_index,
            current_file=current_file,
            next_switch_at=next_switch,
        )


__all__ = ["CarouselState", "CarouselSnapshot"]

