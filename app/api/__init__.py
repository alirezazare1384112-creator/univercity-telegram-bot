"""Mini App HTTP API (FastAPI) served next to the Telegram bot."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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


def create_api(application: Application | None = None) -> FastAPI:
    """Build the FastAPI app.

    ``application`` is the running PTB bot (used later for file uploads and
    notifications); ``None`` is fine for tests and ``--check`` style usage.
    """
    api = FastAPI(title="Student Assistant API", version="1.0.0")
    api.state.bot_application = application

    api.add_middleware(
        CORSMiddleware,
        allow_origins=list(_DEV_ORIGINS),
        allow_headers=[INIT_DATA_HEADER],
        allow_methods=["GET", "PUT", "POST", "DELETE", "OPTIONS"],
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

    # Production: serve the built Mini App from frontend/dist (SPA fallback).
    # In dev the Vite server answers on :5173, so a missing dist/ is fine.
    dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if dist.is_dir():
        assets = dist / "assets"
        if assets.is_dir():
            api.mount("/assets", StaticFiles(directory=assets), name="assets")

        @api.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404)
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_relative_to(dist) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return api
