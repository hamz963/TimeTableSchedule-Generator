"""Real-time events router (Server-Sent Events).

    GET /events/stream           live SSE stream (schedule created/edited/...)
    GET /events/recent           recent events (polling fallback)
    GET /events/status           subscriber/diagnostic info
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.auth import decode_token, get_current_user
from app.config import get_settings
from app.services.events import broker

router = APIRouter(prefix="/events", tags=["events"])

_HEARTBEAT_SECONDS = 20.0


@router.get("/stream")
async def stream(
    request: Request,
    replay: int = Query(0, ge=0, le=100),
    token: Optional[str] = Query(
        None, description="JWT; browsers can't set headers on EventSource, so pass it here"
    ),
):
    """Server-Sent Events stream of schedule events.

    A ``token`` query param is optional by default (intranet/behind a proxy);
    when provided it must be valid, and ``EVENTS_REQUIRE_AUTH=true`` makes it
    mandatory.
    """
    settings = get_settings()
    if token:
        try:
            decode_token(token)
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
    elif settings.events_require_auth:
        raise HTTPException(status_code=401, detail="Authentication required for the event stream")
    async def generator():
        yield ": connected\n\n"
        agen = broker.subscribe(replay=replay)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(agen.__anext__(), timeout=_HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                except StopAsyncIteration:
                    break
                yield f"event: {event.get('type', 'message')}\n"
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            await agen.aclose()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )


@router.get("/recent", dependencies=[Depends(get_current_user)])
def recent(limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
    return {"events": broker.recent(limit)}


@router.get("/status", dependencies=[Depends(get_current_user)])
def status() -> Dict[str, Any]:
    return {"subscribers": broker.subscriber_count(), "recent": len(broker.recent(200))}
