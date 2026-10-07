"""/api/admin - admin-only stats and user list (mirrors the bot panel)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.auth import current_admin
from app.api.schemas import AdminStatsOut, AdminUserOut, AdminUsersOut
from app.database.database import get_session
from app.database.models import User
from app.database.repositories.stats_repository import StatsRepository
from app.database.repositories.user_repository import UserRepository

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStatsOut)
async def admin_stats(_admin: Annotated[User, Depends(current_admin)]) -> AdminStatsOut:
    async with get_session() as session:
        totals = await StatsRepository(session).totals()
    return AdminStatsOut(**totals)


@router.get("/users", response_model=AdminUsersOut)
async def admin_users(
    _admin: Annotated[User, Depends(current_admin)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AdminUsersOut:
    async with get_session() as session:
        repository = UserRepository(session)
        total = await repository.count()
        active = await repository.count(active_only=True)
        users = await repository.list_users(limit=limit)
    return AdminUsersOut(
        total=total,
        active=active,
        users=[AdminUserOut.model_validate(user) for user in users],
    )
