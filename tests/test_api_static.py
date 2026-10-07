"""""""SPA static serving: / serves frontend/dist, /api/* keeps returning JSON 404s."""

from __future__ import annotations

from pathlib import Path

import pytest

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
HAS_BUILD = (DIST / "index.html").is_file()


async def test_unknown_api_path_is_json_404(api_client):
    response = await api_client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Not Found"}


@pytest.mark.skipif(not HAS_BUILD, reason="frontend/dist not built")
async def test_root_serves_the_spa_shell(api_client):
    response = await api_client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<div id=\"root\">" in response.text


@pytest.mark.skipif(not HAS_BUILD, reason="frontend/dist not built")
async def test_unknown_page_falls_back_to_index_html(api_client):
    response = await api_client.get("/some/deep/link")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<div id=\"root\">" in response.text


async def test_path_traversal_cannot_read_python_sources(api_client):
    response = await api_client.get("/%2e%2e/app/api/auth.py")
    assert "INIT_DATA_HEADER" not in response.text
    assert "verify_init_data" not in response.text


def _first_asset(suffix: str) -> Path | None:
    assets = DIST / "assets"
    if not assets.is_dir():
        return None
    return next(assets.glob(f"*{suffix}"), None)


@pytest.mark.skipif(not HAS_BUILD, reason="frontend/dist not built")
async def test_index_is_never_cached(api_client):
    """Telegram webviews must revalidate the shell to see new bundles."""
    response = await api_client.get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.skipif(not HAS_BUILD, reason="frontend/dist not built")
async def test_hashed_assets_are_immutable(api_client):
    js = _first_asset(".js")
    if js is None:
        pytest.skip("no built js asset")
    response = await api_client.get(f"/assets/{js.name}")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


@pytest.mark.skipif(not HAS_BUILD, reason="frontend/dist not built")
async def test_assets_are_gzipped_when_accepted(api_client):
    js = _first_asset(".js")
    if js is None:
        pytest.skip("no built js asset")
    response = await api_client.get(
        f"/assets/{js.name}", headers={"Accept-Encoding": "gzip"}
    )
    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    # httpx transparently inflates the body for assertions.
    assert len(response.content) > 500
