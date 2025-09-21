from __future__ import annotations

from typing import Dict

from ..app import JsonResponse, Request, ServerContext


def register(router, context: ServerContext) -> None:
    _ = context
    router.get("/calendar")(calendar_placeholder)


def calendar_placeholder(request: Request, params: Dict[str, str]) -> JsonResponse:
    return JsonResponse({"ok": False, "error": "Calendar endpoint not implemented"}, status=501)
