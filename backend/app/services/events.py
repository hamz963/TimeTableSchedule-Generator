"""Event broker for real-time schedule events + notifications.

Two delivery layers:

* **In-process** — sync request handlers call :func:`EventBroker.publish`, which
  hands events to subscriber queues via ``loop.call_soon_threadsafe`` (works
  from the worker threads FastAPI uses for sync endpoints).
* **Cross-replica** — when Redis is reachable, each event is also published to
  a channel and every replica runs a background subscriber that fans arriving
  events out to its own SSE clients. Events carry an ``origin`` id so a replica
  never re-delivers its own broadcast.

Both layers degrade gracefully: with no Redis the broker is a correct
single-process bus.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from app.config import get_settings

log = logging.getLogger("timetable.events")

#: Event types emitted by the app.
SCHEDULE_CREATED = "schedule.created"
SCHEDULE_EDITED = "schedule.edited"
SCHEDULE_RESCHEDULED = "schedule.rescheduled"
RUN_REGISTERED = "run.registered"


class EventBroker:
    def __init__(self, history: int = 200) -> None:
        self._subscribers: List[asyncio.Queue] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._history: List[Dict[str, Any]] = []
        self._history_max = history
        self._lock = threading.Lock()
        self._seq = 0
        self.origin = uuid.uuid4().hex[:12]
        self._redis = None
        self._redis_ready = False

    # -- loop binding ---------------------------------------------------------
    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Remember the app's event loop so sync code can publish safely."""
        self._loop = loop

    # -- redis plumbing -------------------------------------------------------
    def _redis_client(self):
        if self._redis_ready:
            return self._redis
        self._redis_ready = True
        try:
            import redis  # noqa: PLC0415

            client = redis.Redis.from_url(
                get_settings().redis_url, socket_connect_timeout=2, decode_responses=True
            )
            client.ping()
            self._redis = client
            log.info("event broker: cross-replica fan-out via Redis enabled")
        except Exception:
            self._redis = None
            log.info("event broker: Redis unavailable, using in-process only")
        return self._redis

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "in-process"

    # -- publish --------------------------------------------------------------
    def _fanout_local(self, event: Dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                if self._loop is not None and self._loop.is_running():
                    self._loop.call_soon_threadsafe(queue.put_nowait, event)
                else:
                    queue.put_nowait(event)
            except Exception:
                pass

    def publish(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Broadcast an event locally and (if Redis is up) to other replicas."""
        with self._lock:
            self._seq += 1
            event = {**event, "seq": self._seq, "at": time.time(), "origin": self.origin}
            self._history.append(event)
            if len(self._history) > self._history_max:
                del self._history[: len(self._history) - self._history_max]
        self._fanout_local(event)
        client = self._redis_client()
        if client is not None:
            try:
                client.publish(get_settings().events_channel, json.dumps(event))
            except Exception:
                pass
        return event

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history[-limit:])

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    # -- subscribe ------------------------------------------------------------
    async def subscribe(self, replay: int = 0) -> AsyncIterator[Dict[str, Any]]:
        """Yield events: first `replay` recent ones, then live events."""
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers.append(queue)
        try:
            for event in (self.recent(replay) if replay else []):
                yield event
            while True:
                yield await queue.get()
        finally:
            with self._lock:
                if queue in self._subscribers:
                    self._subscribers.remove(queue)

    # -- cross-replica subscriber --------------------------------------------
    async def run_redis_subscriber(self) -> None:
        """Background task: relay events published by *other* replicas."""
        if self._redis_client() is None:
            return
        try:
            from redis import asyncio as aioredis  # noqa: PLC0415

            client = aioredis.from_url(
                get_settings().redis_url, socket_connect_timeout=2, decode_responses=True
            )
            await client.ping()
            pubsub = client.pubsub()
            await pubsub.subscribe(get_settings().events_channel)
            log.info("event broker: subscribed to %s", get_settings().events_channel)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    event = json.loads(message["data"])
                except Exception:
                    continue
                if event.get("origin") == self.origin:
                    continue  # already delivered locally on publish
                with self._lock:
                    self._history.append(event)
                    if len(self._history) > self._history_max:
                        del self._history[: len(self._history) - self._history_max]
                self._fanout_local(event)
        except asyncio.CancelledError:  # graceful shutdown
            raise
        except Exception as exc:  # pragma: no cover - environment dependent
            log.warning("event broker subscriber stopped (%s)", exc)


broker = EventBroker()


def reset() -> None:
    """Test isolation: drop history and subscribers."""
    with broker._lock:  # noqa: SLF001 - deliberate test hook
        broker._history.clear()
        broker._subscribers.clear()
