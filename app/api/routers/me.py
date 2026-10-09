"""/api/me - the authenticated Telegram user's profile."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth import current_user
from app.api.schemas import MeOut, ProfileIn
from app.config import get_settings
from app.database.database import get_session
from app.database.models import User
from app.database.repositories.admin_repository import AdminRepository
from app.database.repositories.user_repository import UserRepository

router = APIRouter(prefix="/api", tags=["me"])


async def _me_out(user: User) -> MeOut:
    out = MeOut.model_validate(user)
    async with get_session() as session:
        out.is_admin = await AdminRepository(session).is_admin(user.telegram_id)
    out.credentials_enabled = get_settings().credentials_enabled
    return out


@router.get("/me", response_model=MeOut)
async def read_me(user: Annotated[User, Depends(current_user)]) -> MeOut:
    return await _me_out(user)


@router.put("/me", response_model=MeOut)
async def update_me(
    payload: ProfileIn,
    user: Annotated[User, Depends(current_user)],
) -> MeOut:
    async with get_session() as session:
        repository = UserRepository(session)
        fresh = await repository.get_by_id(user.id)
        if fresh is not None:
            user = await repository.update_profile(
                fresh,
                student_number=payload.student_number,
                field_of_study=payload.field_of_study,
                university=payload.university,
                semester=payload.semester,
                bio=payload.bio,
            )
    return await _me_out(user)
