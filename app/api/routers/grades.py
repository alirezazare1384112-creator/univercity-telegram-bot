"""/api/.../grades - grade items of one course plus the aggregated score."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import current_user
from app.api.routers.courses import _own_course
from app.api.schemas import (
    CourseGradesOut,
    CourseGradeSummary,
    CourseOut,
    GradeItemIn,
    GradeItemOut,
    GradesSummaryOut,
    GradeTotals,
)
from app.database.database import get_session
from app.database.models import User
from app.database.repositories.course_repository import CourseRepository
from app.database.repositories.grade_repository import GradeItemRepository

router = APIRouter(prefix="/api", tags=["grades"])


async def _own_item(session, course_id: int, item_id: int, user: User):
    await _own_course(session, course_id, user)
    item = await GradeItemRepository(session).get(item_id, course_id)
    if item is None:
        raise HTTPException(status_code=404, detail="grade not found")
    return item


def _totals_view(total: float, maximum: float) -> GradeTotals:
    percent = round(total / maximum * 100, 1) if maximum else 0.0
    return GradeTotals(total=total, maximum=maximum, percent=percent)


@router.get("/grades", response_model=GradesSummaryOut)
async def read_grades_summary(
    user: Annotated[User, Depends(current_user)],
) -> GradesSummaryOut:
    """All courses of the user with per-course totals plus the grand total."""
    async with get_session() as session:
        courses = await CourseRepository(session).list_by_user(user.id)
        summary = await GradeItemRepository(session).summary_by_user(user.id)

    rows: list[CourseGradeSummary] = []
    grand_total = grand_maximum = 0.0
    grand_items = 0
    for course in courses:
        count, total, maximum = summary.get(course.id, (0, 0.0, 0.0))
        grand_total += total
        grand_maximum += maximum
        grand_items += count
        rows.append(
            CourseGradeSummary(
                course_id=course.id,
                name=course.name,
                item_count=count,
                totals=_totals_view(total, maximum),
            )
        )
    return GradesSummaryOut(
        courses=rows,
        totals=_totals_view(grand_total, grand_maximum),
        item_count=grand_items,
    )


@router.get("/courses/{course_id}/grades", response_model=CourseGradesOut)
async def read_grades(
    course_id: int,
    user: Annotated[User, Depends(current_user)],
) -> CourseGradesOut:
    async with get_session() as session:
        course = await _own_course(session, course_id, user)
        items = await GradeItemRepository(session).list_by_course(course_id)
        total, maximum = await GradeItemRepository(session).totals(course_id)
    return CourseGradesOut(
        course=CourseOut.model_validate(course),
        items=[GradeItemOut.model_validate(item) for item in items],
        totals=_totals_view(total, maximum),
    )


@router.post("/courses/{course_id}/grades", response_model=GradeItemOut)
async def create_grade(
    course_id: int,
    payload: GradeItemIn,
    user: Annotated[User, Depends(current_user)],
) -> GradeItemOut:
    async with get_session() as session:
        await _own_course(session, course_id, user)
        item = await GradeItemRepository(session).create(
            course_id=course_id,
            title=payload.title,
            score=payload.score,
            max_score=payload.max_score,
            description=payload.description,
            kind=payload.kind,
        )
    return GradeItemOut.model_validate(item)


@router.put("/courses/{course_id}/grades/{item_id}", response_model=GradeItemOut)
async def update_grade(
    course_id: int,
    item_id: int,
    payload: GradeItemIn,
    user: Annotated[User, Depends(current_user)],
) -> GradeItemOut:
    async with get_session() as session:
        item = await _own_item(session, course_id, item_id, user)
        updated = await GradeItemRepository(session).update(
            item,
            title=payload.title,
            score=payload.score,
            max_score=payload.max_score,
            description=payload.description,
            kind=payload.kind,
        )
    return GradeItemOut.model_validate(updated)


@router.delete("/courses/{course_id}/grades/{item_id}")
async def delete_grade(
    course_id: int,
    item_id: int,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, bool]:
    async with get_session() as session:
        item = await _own_item(session, course_id, item_id, user)
        await GradeItemRepository(session).delete(item)
    return {"deleted": True}
