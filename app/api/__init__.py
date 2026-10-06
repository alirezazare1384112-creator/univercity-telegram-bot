"""Mini App HTTP API (FastAPI) served next to the Telegram bot."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from telegram.ext import Application

from app.api.auth import INIT_DATA_HEADER
from app.api.routers import dashboard, me, schedule

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

    @api.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return api
