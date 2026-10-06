"""/api/courses - list, create, edit and delete the student's courses."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import current_user
from app.api.schemas import CourseIn, CourseOut
from app.database.database import get_session
from app.database.models import Course, User
from app.database.repositories.course_repository import CourseRepository

router = APIRouter(prefix="/api", tags=["courses"])


async def _own_course(session, course_id: int, user: User) -> Course:
    course = await CourseRepository(session).get(course_id, user.id)
    if course is None:
        raise HTTPException(status_code=404, detail="course not found")
    return course


@router.get("/courses", response_model=list[CourseOut])
async def list_courses(user: Annotated[User, Depends(current_user)]) -> list[CourseOut]:
    async with get_session() as session:
        courses = await CourseRepository(session).list_by_user(user.id)
    return [CourseOut.model_validate(course) for course in courses]


@router.post("/courses", response_model=CourseOut)
async def create_course(
    payload: CourseIn,
    user: Annotated[User, Depends(current_user)],
) -> CourseOut:
    async with get_session() as session:
        course = await CourseRepository(session).create(
            user_id=user.id,
            name=payload.name,
            units=payload.units,
            teacher_name=payload.teacher_name,
            semester=payload.semester,
            academic_year=payload.academic_year,
        )
    return CourseOut.model_validate(course)


@router.put("/courses/{course_id}", response_model=CourseOut)
async def update_course(
    course_id: int,
    payload: CourseIn,
    user: Annotated[User, Depends(current_user)],
) -> CourseOut:
    async with get_session() as session:
        course = await _own_course(session, course_id, user)
        updated = await CourseRepository(session).update(
            course,
            name=payload.name,
            units=payload.units,
            teacher_name=payload.teacher_name,
            semester=payload.semester,
            academic_year=payload.academic_year,
        )
    return CourseOut.model_validate(updated)


@router.delete("/courses/{course_id}")
async def delete_course(
    course_id: int,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, bool]:
    async with get_session() as session:
        course = await _own_course(session, course_id, user)
        await CourseRepository(session).delete(course)
    return {"deleted": True}
