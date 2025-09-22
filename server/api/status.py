from __future__ import annotations

from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..app import AppState, get_app_state
from ..inky import display as inky_display
from ..storage.files import describe_image, list_images_sorted

router = APIRouter(tags=["status"])


class HealthResponse(BaseModel):
    ok: bool
    display_ready: bool
    target_size: Tuple[int, int]
    image_count: int
    scheduler: "SchedulerStatus"


class SchedulerJob(BaseModel):
    id: str
    name: str
    next_run: Optional[str]
    trigger: Optional[str]
    failures: int = 0
    full_refresh_every: Optional[int] = None


class SchedulerStatus(BaseModel):
    running: bool
    jobs: List[SchedulerJob]


try:  # pragma: no cover - compatibility shim for Pydantic v1/v2
    HealthResponse.model_rebuild()
except AttributeError:  # pragma: no cover - fallback for Pydantic v1
    HealthResponse.update_forward_refs()


class PreviewResponse(BaseModel):
    available: bool
    file: Optional[str] = None
    url: Optional[str] = None
    size: Optional[int] = None
    created_at: Optional[str] = None


@router.get("/health", response_model=HealthResponse)
async def health(state: AppState = Depends(get_app_state)) -> HealthResponse:
    files = list(list_images_sorted(state.image_dir))
    scheduler_state = _scheduler_status(state)
    return HealthResponse(
        ok=True,
        display_ready=inky_display.is_ready(),
        target_size=inky_display.target_size(),
        image_count=len(files),
        scheduler=scheduler_state,
    )


@router.get("/preview", response_model=PreviewResponse)
async def preview(state: AppState = Depends(get_app_state)) -> PreviewResponse:
    files = list(list_images_sorted(state.image_dir))
    if not files:
        return PreviewResponse(available=False)
    latest = files[-1]
    description = describe_image(latest)
    return PreviewResponse(
        available=True,
        file=description["name"],
        url=description["url"],
        size=description["size"],
        created_at=description["created_at"],
    )


def _scheduler_status(state: AppState) -> SchedulerStatus:
    scheduler = state.scheduler
    if scheduler is None:
        return SchedulerStatus(running=False, jobs=[])
    info = scheduler.status()
    jobs: List[SchedulerJob] = []
    for job in info.get("jobs", []):
        jobs.append(
            SchedulerJob(
                id=str(job.get("id")),
                name=str(job.get("name") or job.get("id")),
                next_run=job.get("next_run"),
                trigger=job.get("trigger"),
                failures=int(job.get("failures") or 0),
                full_refresh_every=job.get("full_refresh_every"),
            )
        )
    return SchedulerStatus(running=bool(info.get("running")), jobs=jobs)
