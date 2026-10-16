"""Rate limiting + real-time endpoint auth hardening."""
from app.config import get_settings
from app.middleware import limiter
from tests.shared import get_client

client = get_client()


def test_rate_limit_disabled_by_default_under_test_env():
    assert get_settings().rate_limit_per_minute == 0
    for _ in range(10):
        assert client.get("/auth/me").status_code == 200


def test_rate_limit_returns_429_when_exceeded(monkeypatch):
    limiter.reset()
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "60")
    monkeypatch.setenv("RATE_LIMIT_BURST", "3")
    get_settings.cache_clear()
    try:
        codes = [client.get("/auth/me").status_code for _ in range(12)]
        assert 429 in codes, codes
        blocked = next(c for c in codes if c == 429)
        assert blocked == 429
        # Health checks are exempt from throttling.
        assert client.get("/health").status_code == 200
    finally:
        get_settings.cache_clear()
        limiter.reset()


def test_sse_rejects_invalid_token():
    r = client.get("/events/stream", params={"token": "definitely-not-a-jwt"})
    assert r.status_code == 401
    assert "Invalid or expired token" in r.json()["detail"]


def test_sse_requires_auth_when_configured(monkeypatch):
    monkeypatch.setenv("EVENTS_REQUIRE_AUTH", "true")
    get_settings.cache_clear()
    try:
        assert client.get("/events/stream").status_code == 401
    finally:
        get_settings.cache_clear()
