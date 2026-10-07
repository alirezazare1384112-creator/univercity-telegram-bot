"""Rate limiting: sliding-window 429 per client on /api/* paths."""

from __future__ import annotations

import asyncio

import httpx

from app.api import create_api


def _make_app(**overrides: object):
    app = create_api(None)
    for key, value in overrides.items():
        setattr(app.state, key, value)
    return app


async def _get(app, path: str, headers: dict[str, str] | None = None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers or {})


async def test_over_limit_returns_429_with_retry_after():
    app = _make_app(rate_limit=3)
    for _ in range(3):
        response = await _get(app, "/api/health")
        assert response.status_code == 200
    response = await _get(app, "/api/health")
    assert response.status_code == 429
    assert "بیش از حد مجاز" in response.json()["detail"]
    assert int(response.headers["Retry-After"]) >= 1
    # the security middleware is outermost, so hardening headers land here too
    assert response.headers["X-Content-Type-Options"] == "nosniff"


async def test_window_resets_and_allows_again():
    app = _make_app(rate_limit=1, rate_window=0.25)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/health")).status_code == 200
        assert (await client.get("/api/health")).status_code == 429
        await asyncio.sleep(0.35)
        assert (await client.get("/api/health")).status_code == 200


async def test_forwarded_ips_get_separate_buckets():
    app = _make_app(rate_limit=1)
    first = await _get(app, "/api/health", headers={"X-Forwarded-For": "1.1.1.1"})
    second = await _get(app, "/api/health", headers={"X-Forwarded-For": "1.1.1.1"})
    third = await _get(app, "/api/health", headers={"X-Forwarded-For": "2.2.2.2"})
    assert first.status_code == 200
    assert second.status_code == 429
    assert third.status_code == 200


async def test_non_api_paths_are_not_counted():
    app = _make_app(rate_limit=1)
    assert (await _get(app, "/api/health")).status_code == 200
    static = await _get(app, "/definitely-not-a-page")
    assert static.status_code != 429
    assert (await _get(app, "/api/health")).status_code == 429
