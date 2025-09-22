from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import yaml
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from PIL import Image, ImageDraw, ImageFont

from .inky import display as inky_display

if TYPE_CHECKING:  # pragma: no cover - circular typing guard
    from .app import AppState


LOGGER = logging.getLogger("photoframe.scheduler")

DEFAULT_SCHEDULE_FILE = "schedule.yaml"
DEFAULT_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 15 * 60


@dataclass
class TickConfig:
    seconds: int = 0
    widget: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)
    full_refresh_every: Optional[int] = None

    @property
    def enabled(self) -> bool:
        return self.seconds > 0


@dataclass
class WidgetJobConfig:
    name: str
    widget: str
    cron: Optional[str] = None
    interval: Optional[Dict[str, Any]] = None
    config: Dict[str, Any] = field(default_factory=dict)
    full_refresh_every: Optional[int] = None

    @property
    def job_id(self) -> str:
        return f"widget:{self.name}"


@dataclass
class ScheduleConfig:
    tick: TickConfig = field(default_factory=TickConfig)
    jobs: List[WidgetJobConfig] = field(default_factory=list)


class PhotoFrameScheduler:
    """Scheduler that drives widget renders based on a YAML configuration."""

    def __init__(
        self,
        state: AppState,
        *,
        schedule_path: Optional[Path] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._state = state
        self._schedule_path = schedule_path or (state.image_dir / DEFAULT_SCHEDULE_FILE)
        self._logger = logger or LOGGER
        self._scheduler = AsyncIOScheduler()
        self._tick_config: TickConfig = TickConfig()
        self._jobs: Dict[str, WidgetJobConfig] = {}
        self._backoff_state: Dict[str, int] = {}
        self._run_counters: Dict[str, int] = {}
        self._job_lock: Optional[asyncio.Lock] = None
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    @property
    def schedule_path(self) -> Path:
        return self._schedule_path

    async def start(self) -> None:
        if self._started:
            return
        await self.reload()
        try:
            self._scheduler.start()
            self._started = True
            self._logger.info("Scheduler started with %d job(s)", len(self._jobs))
        except Exception:
            self._logger.exception("Unable to start scheduler")
            raise

    async def stop(self) -> None:
        if not self._started:
            return
        try:
            self._scheduler.shutdown(wait=False)
        finally:
            self._started = False
            self._logger.info("Scheduler stopped")

    async def reload(self) -> None:
        config = self._load_schedule()
        self._scheduler.remove_all_jobs()
        self._jobs = {}
        self._run_counters.clear()
        self._backoff_state.clear()
        self._tick_config = config.tick

        if config.tick.enabled:
            trigger = IntervalTrigger(seconds=config.tick.seconds)
            self._scheduler.add_job(
                self._run_tick,
                trigger=trigger,
                id="tick",
                name="tick",
                coalesce=True,
                max_instances=1,
            )
            self._logger.debug(
                "Configured tick job every %s seconds", config.tick.seconds
            )

        for job in config.jobs:
            trigger = self._create_trigger(job)
            if trigger is None:
                self._logger.warning(
                    "Skipping job %s due to missing trigger configuration", job.name
                )
                continue
            self._jobs[job.job_id] = job
            self._scheduler.add_job(
                self._run_widget_job,
                trigger=trigger,
                id=job.job_id,
                name=job.name,
                kwargs={"job_id": job.job_id},
                coalesce=True,
                max_instances=1,
            )
            self._logger.debug("Configured widget job %s", job.name)

    def status(self) -> Dict[str, Any]:
        jobs = []
        for job in self._scheduler.get_jobs():
            next_run = job.next_run_time.isoformat() if job.next_run_time else None
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": next_run,
                    "trigger": str(job.trigger),
                    "failures": self._backoff_state.get(job.id, 0),
                    "full_refresh_every": (
                        self._tick_config.full_refresh_every
                        if job.id == "tick"
                        else self._jobs.get(job.id).full_refresh_every
                        if job.id in self._jobs
                        else None
                    ),
                }
            )
        return {"running": self._started and self._scheduler.running, "jobs": jobs}

    async def _run_tick(self) -> None:
        widget_slug = self._tick_config.widget or self._state.runtime_config.default_widget
        if not widget_slug:
            self._logger.debug("Skipping tick run: no widget configured")
            return
        await self._run_job("tick", widget_slug, self._tick_config.config, self._tick_config.full_refresh_every)

    async def _run_widget_job(self, *, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            self._logger.warning("Received run for unknown job id %s", job_id)
            return
        await self._run_job(job_id, job.widget, job.config, job.full_refresh_every)

    async def _run_job(
        self,
        job_id: str,
        widget_slug: str,
        config: Dict[str, Any],
        full_refresh_every: Optional[int],
    ) -> None:
        if self._job_lock is None:
            self._job_lock = asyncio.Lock()
        async with self._job_lock:
            full_refresh = self._should_full_refresh(job_id, full_refresh_every)
            try:
                await asyncio.to_thread(
                    self._render_widget,
                    widget_slug,
                    config,
                    full_refresh,
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.exception("Job %s failed: %s", job_id, exc)
                await asyncio.to_thread(self._display_safe_screen, widget_slug, exc)
                self._schedule_retry(job_id)
            else:
                self._backoff_state.pop(job_id, None)
                retry_id = f"{job_id}:retry"
                try:
                    self._scheduler.remove_job(retry_id)
                except JobLookupError:
                    pass
                self._logger.info(
                    "Rendered widget %s (full_refresh=%s)", widget_slug, full_refresh
                )

    def _render_widget(self, widget_slug: str, config: Dict[str, Any], full_refresh: bool) -> None:
        widget = self._state.widget_registry.get(widget_slug)
        target_size = inky_display.target_size()
        image = widget.render(config or {}, target_size)
        if full_refresh:
            self._perform_full_refresh()
        inky_display.display_image(image)
        self._state.last_rendered = widget_slug

    def _perform_full_refresh(self) -> None:
        size = inky_display.target_size()
        blank = Image.new("RGB", size, color="white")
        try:
            inky_display.display_image(blank)
        except Exception:
            self._logger.exception("Failed to run full refresh blank frame")

    def _display_safe_screen(self, widget_slug: str, error: Exception) -> None:
        size = inky_display.target_size()
        image = Image.new("RGB", size, color="white")
        draw = ImageDraw.Draw(image)
        title = "Safe Screen"
        message = f"Widget '{widget_slug}' faalde"
        details = str(error)
        font = ImageFont.load_default()
        draw.text((20, 20), title, font=font, fill="black")
        draw.text((20, 60), message, font=font, fill="black")
        draw.text((20, 90), details[:200], font=font, fill="black")
        try:
            inky_display.display_image(image)
            self._state.last_rendered = "safe-screen"
        except Exception:
            self._logger.exception("Safe screen display failed")

    def _schedule_retry(self, job_id: str) -> None:
        attempts = self._backoff_state.get(job_id, 0) + 1
        self._backoff_state[job_id] = attempts
        delay = min(DEFAULT_BACKOFF_SECONDS * (2 ** (attempts - 1)), MAX_BACKOFF_SECONDS)
        run_time = datetime.now() + timedelta(seconds=delay)
        retry_id = f"{job_id}:retry"
        self._scheduler.add_job(
            self._run_retry_job,
            trigger=DateTrigger(run_date=run_time),
            id=retry_id,
            name=f"retry:{job_id}",
            kwargs={"job_id": job_id},
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._logger.warning(
            "Scheduled retry for %s in %s seconds (attempt %s)", job_id, delay, attempts
        )

    async def _run_retry_job(self, *, job_id: str) -> None:
        if job_id == "tick":
            await self._run_tick()
            return
        job = self._jobs.get(job_id)
        if not job:
            self._logger.warning("Retry job %s no longer exists", job_id)
            return
        await self._run_widget_job(job_id=job_id)

    def _should_full_refresh(self, job_id: str, frequency: Optional[int]) -> bool:
        if not frequency or frequency <= 0:
            return False
        count = self._run_counters.get(job_id, 0) + 1
        if count >= frequency:
            self._run_counters[job_id] = 0
            return True
        self._run_counters[job_id] = count
        return False

    def _load_schedule(self) -> ScheduleConfig:
        if not self._schedule_path.exists():
            self._logger.info(
                "Schedule file %s not found; running without scheduled jobs",
                self._schedule_path,
            )
            return ScheduleConfig()

        try:
            raw = yaml.safe_load(self._schedule_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            self._logger.error("Invalid schedule configuration: %s", exc)
            return ScheduleConfig()

        tick = self._parse_tick(raw.get("tick"))
        jobs = [self._parse_job(idx, item) for idx, item in enumerate(raw.get("widgets", []))]
        jobs = [job for job in jobs if job is not None]
        return ScheduleConfig(tick=tick, jobs=jobs)  # type: ignore[arg-type]

    def _parse_tick(self, raw: Any) -> TickConfig:
        if not isinstance(raw, dict):
            return TickConfig()
        seconds = int(raw.get("seconds", 0) or 0)
        widget = raw.get("widget")
        if widget is not None:
            widget = str(widget)
        cfg = raw.get("config")
        if not isinstance(cfg, dict):
            cfg = {}
        full_refresh = raw.get("full_refresh_every")
        try:
            full_refresh_int = int(full_refresh) if full_refresh is not None else None
        except (TypeError, ValueError):
            full_refresh_int = None
        return TickConfig(
            seconds=max(0, seconds),
            widget=widget,
            config=cfg,
            full_refresh_every=full_refresh_int,
        )

    def _parse_job(self, index: int, raw: Any) -> Optional[WidgetJobConfig]:
        if not isinstance(raw, dict):
            self._logger.warning("Ignoring job #%s: expected mapping", index)
            return None
        widget = raw.get("widget") or raw.get("slug")
        if not widget:
            self._logger.warning("Ignoring job #%s: missing widget slug", index)
            return None
        name = str(raw.get("name") or widget)
        cfg = raw.get("config")
        if not isinstance(cfg, dict):
            cfg = {}
        cron = raw.get("cron")
        interval = raw.get("interval")
        if interval is not None and not isinstance(interval, dict):
            interval = None
        frequency = raw.get("full_refresh_every")
        try:
            freq_int = int(frequency) if frequency is not None else None
        except (TypeError, ValueError):
            freq_int = None
        return WidgetJobConfig(
            name=name,
            widget=str(widget),
            cron=str(cron) if cron else None,
            interval=interval,
            config=cfg,
            full_refresh_every=freq_int,
        )

    def _create_trigger(self, job: WidgetJobConfig):
        if job.cron:
            try:
                return CronTrigger.from_crontab(job.cron)
            except ValueError as exc:
                self._logger.error("Invalid cron expression for %s: %s", job.name, exc)
                return None
        if job.interval:
            valid_keys = {
                "weeks",
                "days",
                "hours",
                "minutes",
                "seconds",
            }
            cleaned: Dict[str, int] = {}
            for key, value in job.interval.items():
                if key not in valid_keys:
                    continue
                try:
                    cleaned[key] = int(value)
                except (TypeError, ValueError):
                    self._logger.error(
                        "Invalid interval value for %s.%s: %r", job.name, key, value
                    )
            if cleaned:
                return IntervalTrigger(**cleaned)
        self._logger.warning("Job %s missing cron/interval configuration", job.name)
        return None


__all__ = ["PhotoFrameScheduler", "ScheduleConfig", "WidgetJobConfig", "TickConfig"]
