"""Chat conversation storage.

Backed by Redis when reachable (so any replica can serve any conversation),
with a transparent in-process fallback for single-replica / offline runs. The
conversation dict contains sets (``views``/``formats``) that are encoded as
sorted lists for JSON transport and restored on read.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Dict, Optional

from app.config import get_settings

_PREFIX = "timetable:chat:"


def _encode(convo: Dict[str, Any]) -> str:
    out = dict(convo)
    out["views"] = sorted(convo.get("views") or [])
    out["formats"] = sorted(convo.get("formats") or [])
    return json.dumps(out)


def _decode(raw: str) -> Dict[str, Any]:
    data = json.loads(raw)
    data["views"] = set(data.get("views") or [])
    data["formats"] = set(data.get("formats") or [])
    data.setdefault("pending_edit", None)
    data.setdefault("history", [])
    data.setdefault("time_pref", None)
    data.setdefault("asked_time", False)
    data.setdefault("schedule_run_id", None)
    return data


def _create_redis():
    """Live Redis client, or None when unavailable (never raises)."""
    try:
        import redis  # noqa: PLC0415

        client = redis.Redis.from_url(
            get_settings().redis_url, socket_connect_timeout=2, decode_responses=True
        )
        client.ping()
        return client
    except Exception:
        return None


class ChatStore:
    """Redis-backed conversation store with an in-memory fallback."""

    def __init__(self, client=None, ttl_seconds: Optional[int] = None) -> None:
        self._client = client
        self._ttl = ttl_seconds if ttl_seconds is not None else get_settings().chat_ttl_seconds
        self._memory: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    @property
    def backend(self) -> str:
        return "redis" if self._client is not None else "memory"

    @staticmethod
    def _key(cid: str) -> str:
        return f"{_PREFIX}{cid}"

    def get(self, cid: str) -> Optional[Dict[str, Any]]:
        if self._client is not None:
            try:
                raw = self._client.get(self._key(cid))
                return _decode(raw) if raw else None
            except Exception:
                pass  # fall through to memory (and keep serving)
        with self._lock:
            convo = self._memory.get(cid)
            return dict(convo) if convo is not None else None

    def set(self, cid: str, convo: Dict[str, Any]) -> None:
        if self._client is not None:
            try:
                self._client.setex(self._key(cid), self._ttl, _encode(convo))
                return
            except Exception:
                pass
        with self._lock:
            self._memory[cid] = dict(convo)

    def delete(self, cid: str) -> None:
        if self._client is not None:
            try:
                self._client.delete(self._key(cid))
            except Exception:
                pass
        with self._lock:
            self._memory.pop(cid, None)

    def clear(self) -> None:
        with self._lock:
            self._memory.clear()
        if self._client is not None:
            try:
                for key in self._client.scan_iter(match=f"{_PREFIX}*"):
                    self._client.delete(key)
            except Exception:
                pass


_store: Optional[ChatStore] = None


def get_chat_store() -> ChatStore:
    global _store
    if _store is None:
        _store = ChatStore(_create_redis())
    return _store


def set_chat_store(store: Optional[ChatStore]) -> None:
    """Test hook: inject a store (or reset to auto-detect on next use)."""
    global _store
    _store = store
