"""Display driver abstraction for the Inky Impression."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PIL import Image

from ..config import DisplaySettings

_LOGGER = logging.getLogger(__name__)


class DisplayDriver:
    """Encapsulates access to the Inky Impression hardware."""

    def __init__(self, settings: DisplaySettings) -> None:
        self.settings = settings
        self._device = None
        self._fallback_path = Path(settings.fallback_image)
        self._initialise_device()

    def _initialise_device(self) -> None:
        if not self.settings.enable_hardware:
            _LOGGER.info("Hardware access disabled; using fallback output at %s", self._fallback_path)
            return
        try:
            from inky.auto import auto  # type: ignore

            self._device = auto()
            self._device.set_border(self.settings.border_colour)
            if self.settings.rotation:
                self._device.set_rotation(self.settings.rotation)
            _LOGGER.info("Detected Inky Impression: %s", type(self._device).__name__)
        except Exception as exc:  # pragma: no cover - depends on hardware
            _LOGGER.warning("Falling back to file output because the Inky device is unavailable: %s", exc)
            self._device = None

    def show(self, image: Image.Image) -> Path:
        """Render the image to the Inky panel or save it to disk."""

        if self._device is not None:  # pragma: no cover - hardware specific
            _LOGGER.debug("Updating Inky display")
            self._device.set_image(image)
            self._device.show()
            return self._fallback_path

        self._fallback_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(self._fallback_path)
        _LOGGER.info("Saved rendered frame to %s", self._fallback_path)
        return self._fallback_path

    @property
    def device(self) -> Optional[object]:  # pragma: no cover - trivial accessor
        return self._device


__all__ = ["DisplayDriver"]
