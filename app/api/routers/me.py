"""/api/me - the authenticated Telegram user's profile."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth import current_user
from app.api.schemas import MeOut
from app.database.models import User

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=MeOut)
async def read_me(user: Annotated[User, Depends(current_user)]) -> User:
    return user
