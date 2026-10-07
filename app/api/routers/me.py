"""/api/me - the authenticated Telegram user's profile."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth import current_user
from app.api.schemas import MeOut, ProfileIn
from app.database.database import get_session
from app.database.models import User
from app.database.repositories.user_repository import UserRepository

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=MeOut)
async def read_me(user: Annotated[User, Depends(current_user)]) -> User:
    return user


@router.put("/me", response_model=MeOut)
async def update_me(
    payload: ProfileIn,
    user: Annotated[User, Depends(current_user)],
) -> User:
    async with get_session() as session:
        repository = UserRepository(session)
        fresh = await repository.get_by_id(user.id)
        if fresh is None:  # pragma: no cover - user was authenticated moments ago
            return user
        return await repository.update_profile(
            fresh,
            student_number=payload.student_number,
            field_of_study=payload.field_of_study,
            university=payload.university,
            semester=payload.semester,
            bio=payload.bio,
        )
