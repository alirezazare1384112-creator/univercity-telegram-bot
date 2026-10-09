"""Mini App HTTP API (FastAPI) served next to the Telegram bot."""

from __future__ import annotations

import json
import logging
import math
import time
from collections import deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from telegram.ext import Application

from app.api.auth import INIT_DATA_HEADER
from app.api.routers import (
    admin,
    announcements,
    calendar,
    courses,
    dashboard,
    grades,
    links,
    me,
    notes,
    reminders,
    schedule,
)

# Vite dev servers; production is same-origin so no CORS is needed there.
_DEV_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
)

# Uploads are capped at 20 MB per file; anything far above that never reaches
# the route handlers (multipart bodies are buffered in memory before parsing).
_MAX_BODY_BYTES = 25 * 1024 * 1024

# Sliding-window cap per client on /api/* (static SPA files are not counted).
_RATE_LIMIT_PER_MINUTE = 300
_RATE_WINDOW_SECONDS = 60.0
_RATE_LIMIT_MAX_KEYS = 10_000


# Paths exempt from the per-IP budget: Telegram webhook bursts come from a
# handful of Telegram IPs shared by every user, and the cron/setup routes are
# machine-to-machine. Counting them would lock out real users.
_RATE_LIMIT_EXEMPT = {
    "/api/telegram-webhook",
    "/api/index/telegram-webhook",
    "/api/cron/tick",
    "/api/index/cron/tick",
    "/api/setup",
    "/api/index/setup",
}


def _install_rate_limit(api: FastAPI) -> None:
    """Return 429 (with Retry-After) when a client exceeds the window.

    Clients are keyed by the first X-Forwarded-For entry when present
    (behind cloudflared the direct peer is always localhost), falling
    back to the socket address. State lives on ``api.state`` so tests
    can shrink the limit or the window.
    """

    hits: dict[str, deque[float]] = {}

    @api.middleware("http")
    async def rate_limit(request: Request, call_next) -> object:
        if (
            request.method != "OPTIONS"
            and request.url.path.startswith("/api/")
            and request.url.path not in _RATE_LIMIT_EXEMPT
        ):
            forwarded = request.headers.get("x-forwarded-for", "")
            if forwarded:
                key = forwarded.split(",")[0].strip()
            elif request.client:
                key = request.client.host
            else:
                key = ""
            window = float(api.state.rate_window)
            limit = int(api.state.rate_limit)
            now = time.monotonic()
            bucket = hits.setdefault(key, deque())
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, math.ceil(window - (now - bucket[0])))
                return JSONResponse(
                    {
                        "detail": (
                            "تعداد درخواست‌ها بیش از حد مجاز است؛ "
                            "کمی بعد دوباره تلاش کنید"
                        )
                    },
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)
            if len(hits) > _RATE_LIMIT_MAX_KEYS:
                hits.clear()
        return await call_next(request)


def _install_security(api: FastAPI) -> None:
    """Body-size cap plus hardening headers for every response.

    No X-Frame-Options: Telegram Web opens Mini Apps inside an iframe on
    web.telegram.org, so framing must stay allowed.
    """

    @api.middleware("http")
    async def security(request: Request, call_next) -> object:
        if request.method in ("POST", "PUT", "PATCH"):
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > _MAX_BODY_BYTES:
                return JSONResponse({"detail": "payload too large"}, status_code=413)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


class _ImmutableStaticFiles(StaticFiles):
    """StaticFiles that let browsers cache hashed bundles for a year.

    Every file under /assets carries a content hash in its name (Vite), so a
    new build changes the URL and the old copy may be cached forever; the
    SPA shell (index.html) is served by the route below with ``no-store``.
    """

    def file_response(
        self, full_path, stat_result, scope, status_code: int = 200
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _resolve_spa_dist() -> Path | None:
    """Locate the built Mini App (Vercel ``public/`` or local ``frontend/dist``)."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    for candidate in (repo_root / "public", repo_root / "frontend" / "dist"):
        if (candidate / "index.html").is_file():
            return candidate
    return None


def create_api(
    application: Application | None = None, *, mount_spa: bool = True
) -> FastAPI:
    """Build the FastAPI app.

    ``application`` is the running PTB bot (used later for file uploads and
    notifications); ``None`` is fine for tests and ``--check`` style usage.
    ``mount_spa=False`` skips the static/SPA catch-all (serverless hosts
    such as Vercel serve the built frontend themselves - and a GET
    catch-all would shadow later-registered GET routes like /api/setup).
    """
    api = FastAPI(title="Student Assistant API", version="1.0.0")
    api.state.bot_application = application
    api.state.rate_limit = _RATE_LIMIT_PER_MINUTE
    api.state.rate_window = _RATE_WINDOW_SECONDS

    api.add_middleware(
        CORSMiddleware,
        allow_origins=list(_DEV_ORIGINS),
        allow_headers=[INIT_DATA_HEADER],
        allow_methods=["GET", "PUT", "POST", "DELETE", "OPTIONS"],
    )
    # Installed first so the security middleware stays outermost and its
    # headers also land on rate-limited (429) responses.
    _install_rate_limit(api)
    _install_security(api)
    # Outermost of all: gzips the JS/CSS bundles (337 KB -> ~97 KB on the
    # wire) plus API JSON. Bodies >= 128 KB are compressed off the event
    # loop (starlette's thread_minimum_size). PDFs/zips are already
    # compressed, so gzip there would only burn CPU.
    api.add_middleware(
        GZipMiddleware,
        compresslevel=6,
        exclude_content_types=(
            "application/gzip",
            "application/x-gzip",
            "application/zip",
            "audio/*",
            "font/woff",
            "font/woff2",
            "image/avif",
            "image/gif",
            "image/jpeg",
            "image/png",
            "image/webp",
            "text/event-stream",
            "video/*",
            "application/pdf",
        ),
    )

    api.include_router(me.router)
    api.include_router(dashboard.router)
    api.include_router(schedule.router)
    api.include_router(courses.router)
    api.include_router(grades.router)
    api.include_router(notes.router)
    api.include_router(calendar.router)
    api.include_router(reminders.router)
    api.include_router(announcements.router)
    api.include_router(links.router)
    api.include_router(admin.router)

    @api.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.post("/api/boot-report")
    async def boot_report(request: Request) -> dict[str, str]:
        """Public diagnostics beacon: what the Mini App client sees.

        The frontend fires this on boot (even without initData) so a blank
        screen in a user's Telegram can be diagnosed from server logs.
        """
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - malformed beacon is not an error
            body = {}
        logging.getLogger(__name__).info(
            "boot-report ua=%s body=%s",
            request.headers.get("user-agent", "?"),
            json.dumps(body, ensure_ascii=False)[:600],
        )
        return {"ok": "1"}

    # Local/host production: serve the built Mini App from frontend/dist.
    # Vercel copies the build into ``public/`` and serves it from the CDN;
    # that deployment therefore uses ``mount_spa=False`` so this catch-all
    # cannot shadow later GET routes such as ``/api/setup``.
    # In dev the Vite server answers on :5173, so a missing dist/ is fine.
    dist = _resolve_spa_dist()
    if mount_spa and dist is not None and dist.is_dir():
        assets = dist / "assets"
        if assets.is_dir():
            api.mount("/assets", _ImmutableStaticFiles(directory=assets), name="assets")

        @api.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404)
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_relative_to(dist) and candidate.is_file():
                return FileResponse(candidate)
            # no-store: Telegram webviews must revalidate the shell, otherwise
            # a stale index.html keeps pointing at the previous script bundle.
            return FileResponse(
                dist / "index.html", headers={"Cache-Control": "no-store"}
            )

    return api
