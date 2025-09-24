"""Main application loop for the Smart Display."""
from __future__ import annotations

import logging
import signal
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from dateutil import tz

from .config import AppConfig, ConfigManager
from .display.driver import DisplayDriver
from .display.layout import LayoutManager
from .widgets.base import WidgetContext
from .widgets.factory import build_widgets
from .web.server import launch_config_server

_LOGGER = logging.getLogger(__name__)


class SmartDisplayApp:
    """Orchestrates configuration, data fetching, and rendering."""

    def __init__(self, config_path: Path | str = Path("config/config.json")) -> None:
        self.config_manager = ConfigManager(config_path)
        self._refresh_event = threading.Event()
        self._stop_event = threading.Event()
        self._web_thread: Optional[threading.Thread] = None
        self._display: Optional[DisplayDriver] = None

    def run(self) -> None:
        """Enter the refresh loop until interrupted."""

        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        signal.signal(signal.SIGTERM, lambda *_: self.stop())
        signal.signal(signal.SIGINT, lambda *_: self.stop())

        while not self._stop_event.is_set():
            config = self.config_manager.load()
            self._ensure_display(config)
            self._ensure_web_server(config)
            self._render_once(config)
            self._wait_for_next_cycle(config)

        _LOGGER.info("SmartDisplayApp stopped")

    def request_refresh(self) -> None:
        """Trigger an immediate refresh."""

        self._refresh_event.set()

    def stop(self) -> None:
        """Signal the application to stop."""

        self._stop_event.set()
        self._refresh_event.set()

    def _ensure_display(self, config: AppConfig) -> None:
        if self._display is None or self._display.settings != config.display:
            self._display = DisplayDriver(config.display)

    def _ensure_web_server(self, config: AppConfig) -> None:
        if not config.web.enabled or self._web_thread is not None:
            return
        self._web_thread = launch_config_server(
            config.web,
            self.config_manager,
            refresh_callback=self.request_refresh,
        )

    def _render_once(self, config: AppConfig) -> None:
        assert self._display is not None
        layout = LayoutManager(config.display)
        canvas = layout.canvas()
        now = datetime.now(tz=tz.tzlocal())
        widgets = build_widgets(config)
        for widget_id, widget in widgets.items():
            area = layout.area(widget_id)
            context = WidgetContext(area=area, palette=layout.palette, now=now)
            widget.render(canvas, context)
        self._display.show(canvas)

    def _wait_for_next_cycle(self, config: AppConfig) -> None:
        wait_seconds = max(config.refresh_minutes, 1) * 60
        self._refresh_event.wait(wait_seconds)
        self._refresh_event.clear()


def main() -> None:  # pragma: no cover - CLI entrypoint
    app = SmartDisplayApp()
    app.run()


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    main()
