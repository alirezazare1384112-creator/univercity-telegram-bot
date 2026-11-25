from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import current_user
from app.api.schemas import WeeklyActivityIn, WeeklyActivityOut
from app.database.database import get_session
from app.database.models import User
from app.database.repositories.activity_repository import WeeklyActivityRepository

router = APIRouter(prefix="/api", tags=["activities"])


def _activity_out(activity) -> WeeklyActivityOut:
    return WeeklyActivityOut(
        id=activity.id,
        title=activity.title,
        description=activity.description,
        day_of_week=activity.day_of_week,
        start_time=activity.start_time.strftime("%H:%M"),
        duration_hours=activity.duration_hours,
        category=activity.category,
        is_active=activity.is_active,
    )


@router.get("/activities", response_model=list[WeeklyActivityOut])
async def list_activities(
    user: Annotated[User, Depends(current_user)],
) -> list[WeeklyActivityOut]:
    async with get_session() as session:
        activities = await WeeklyActivityRepository(session).list_by_user(user.id)
    return [_activity_out(a) for a in activities]


@router.post("/activities", response_model=WeeklyActivityOut)
async def create_activity(
    payload: WeeklyActivityIn,
    user: Annotated[User, Depends(current_user)],
) -> WeeklyActivityOut:
    async with get_session() as session:
        activity = await WeeklyActivityRepository(session).create(
            user_id=user.id,
            title=payload.title,
            day_of_week=payload.day_of_week,
            start_time=payload.start_time,
            duration_hours=payload.duration_hours,
            description=payload.description,
            category=payload.category,
            is_active=payload.is_active,
        )
    return _activity_out(activity)


@router.put("/activities/{activity_id}", response_model=WeeklyActivityOut)
async def update_activity(
    activity_id: int,
    payload: WeeklyActivityIn,
    user: Annotated[User, Depends(current_user)],
) -> WeeklyActivityOut:
    async with get_session() as session:
        repository = WeeklyActivityRepository(session)
        activity = await repository.get(activity_id, user.id)
        if activity is None:
            raise HTTPException(status_code=404, detail="activity not found")
        activity = await repository.update(
            activity,
            title=payload.title,
            day_of_week=payload.day_of_week,
            start_time=payload.start_time,
            duration_hours=payload.duration_hours,
            description=payload.description,
            category=payload.category,
            is_active=payload.is_active,
        )
    return _activity_out(activity)


@router.delete("/activities/{activity_id}")
async def delete_activity(
    activity_id: int,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, bool]:
    async with get_session() as session:
        repository = WeeklyActivityRepository(session)
        activity = await repository.get(activity_id, user.id)
        if activity is None:
            raise HTTPException(status_code=404, detail="activity not found")
        await repository.delete(activity)
    return {"deleted": True}
