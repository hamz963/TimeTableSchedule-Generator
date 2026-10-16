"""Pure-ASGI rate-limiting middleware (token bucket per client IP).

Implemented as raw ASGI rather than ``BaseHTTPMiddleware`` on purpose:
``BaseHTTPMiddleware`` buffers responses and breaks Server-Sent Events
(``/events/stream``). This middleware never touches the response body except to
reject — it just forwards ``send``/``receive``.

Limits come from settings at request time, so operators (and tests) can change
them without rebuilding the app. ``RATE_LIMIT_PER_MINUTE=0`` disables it.
Health/docs endpoints are exempt.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Dict, Optional, Tuple

from app.config import get_settings

_EXEMPT_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico")


class RateLimiter:
    """Thread-safe token bucket keyed by (client ip, per-minute limit)."""

    def __init__(self) -> None:
        self._buckets: Dict[Tuple[str, int], Tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, per_minute: int, burst: int) -> Tuple[bool, float]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        rate = per_minute / 60.0  # tokens per second
        capacity = float(max(burst, 1))
        bucket_key = (key, per_minute)
        with self._lock:
            tokens, last = self._buckets.get(bucket_key, (capacity, now))
            tokens = min(capacity, tokens + (now - last) * rate)
            if tokens >= 1.0:
                self._buckets[bucket_key] = (tokens - 1.0, now)
                return True, 0.0
            need = 1.0 - tokens
            retry = need / rate if rate > 0 else 60.0
            self._buckets[bucket_key] = (tokens, now)
            return False, max(0.1, retry)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


limiter = RateLimiter()


def _client_ip(scope) -> str:
    headers = dict(scope.get("headers") or [])
    forwarded = headers.get(b"x-forwarded-for")
    if forwarded:
        return forwarded.decode().split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


class RateLimitMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        settings = get_settings()
        per_minute = int(getattr(settings, "rate_limit_per_minute", 0))

        if per_minute <= 0 or path.startswith(_EXEMPT_PREFIXES):
            return await self.app(scope, receive, send)

        allowed, retry_after = limiter.allow(
            _client_ip(scope), per_minute, int(getattr(settings, "rate_limit_burst", 1))
        )
        if allowed:
            return await self.app(scope, receive, send)

        body = json.dumps({
            "detail": "Rate limit exceeded; slow down.",
            "retry_after": round(retry_after, 2),
        }).encode()
        headers = [
            (b"content-type", b"application/json"),
            (b"retry-after", str(int(retry_after) + 1).encode()),
        ]
        await send({"type": "http.response.start", "status": 429, "headers": headers})
        await send({"type": "http.response.body", "body": body})
