from __future__ import annotations

from collections import deque
from typing import Deque, List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..app import AppState, get_app_state
from .dependencies import admin_guard

router = APIRouter(tags=["logs"])


class LogTailResponse(BaseModel):
    path: str
    lines: List[str]


@router.get("/logs/tail", response_model=LogTailResponse, dependencies=[Depends(admin_guard)])
async def tail_logs(
    limit: int = Query(100, ge=1, le=1000, description="Aantal logregels om op te halen"),
    state: AppState = Depends(get_app_state),
) -> LogTailResponse:
    path = state.log_file
    if not path.exists():
        return LogTailResponse(path=str(path), lines=[])

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        lines: Deque[str] = deque(maxlen=limit)
        for raw in handle:
            lines.append(raw.rstrip("\n"))

    return LogTailResponse(path=str(path), lines=list(lines))
