"""Security middleware tests: hardening headers and the body-size cap."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.api import _MAX_BODY_BYTES

_DIST_INDEX = Path(__file__).resolve().parent.parent / "frontend" / "dist" / "index.html"


async def test_hardening_headers_on_api_responses(api_client):
    response = await api_client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    # Telegram Web loads Mini Apps in an iframe: framing must stay allowed.
    assert "X-Frame-Options" not in response.headers


async def test_headers_are_present_on_json_errors(api_client):
    response = await api_client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.skipif(not _DIST_INDEX.is_file(), reason="frontend/dist not built")
async def test_headers_are_present_on_the_spa(api_client):
    response = await api_client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"


async def test_oversized_body_is_rejected_before_routing(api_client):
    body = b"x" * (_MAX_BODY_BYTES + 1024)
    response = await api_client.post(
        "/api/links",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "payload too large"}


async def test_normal_body_is_unaffected(api_client):
    response = await api_client.post(
        "/api/links",
        json={"title": "x", "url": "https://example.com"},
    )
    assert response.status_code == 401  # unauthenticated, not 413
