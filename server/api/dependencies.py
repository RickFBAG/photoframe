from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from ..app import AppState, RateLimiter, get_app_state


def _rate_limit(state: AppState, identifier: str) -> None:
    limiter: RateLimiter = state.rate_limiter
    try:
        limiter.check(identifier)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded") from exc


def admin_guard(
    request: Request,
    state: AppState = Depends(get_app_state),
) -> Optional[str]:
    expected = state.config.admin_token
    provided = request.headers.get("x-admin-token")
    if expected:
        if not provided or not secrets.compare_digest(provided, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")
    identifier = provided or (request.client.host if request.client else "anonymous")
    _rate_limit(state, identifier)
    return provided
