from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import current_user
from app.api.schemas import LinkIn, LinkOut
from app.database.database import get_session
from app.database.models import User
from app.database.repositories.link_repository import LinkRepository

router = APIRouter(prefix="/api", tags=["links"])


@router.get("/links", response_model=list[LinkOut])
async def list_links(
    user: Annotated[User, Depends(current_user)],
) -> list[LinkOut]:
    async with get_session() as session:
        links = await LinkRepository(session).list_by_user(user.id)
    return [LinkOut.model_validate(link) for link in links]


@router.post("/links", response_model=LinkOut)
async def create_link(
    payload: LinkIn,
    user: Annotated[User, Depends(current_user)],
) -> LinkOut:
    async with get_session() as session:
        link = await LinkRepository(session).create(
            user_id=user.id,
            title=payload.title,
            url=payload.url,
            description=payload.description,
        )
    return LinkOut.model_validate(link)


@router.put("/links/{link_id}", response_model=LinkOut)
async def update_link(
    link_id: int,
    payload: LinkIn,
    user: Annotated[User, Depends(current_user)],
) -> LinkOut:
    async with get_session() as session:
        repository = LinkRepository(session)
        link = await repository.get(link_id, user.id)
        if link is None:
            raise HTTPException(status_code=404, detail="link not found")
        link = await repository.update(
            link, title=payload.title, url=payload.url, description=payload.description
        )
    return LinkOut.model_validate(link)


@router.delete("/links/{link_id}")
async def delete_link(
    link_id: int,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, bool]:
    async with get_session() as session:
        repository = LinkRepository(session)
        link = await repository.get(link_id, user.id)
        if link is None:
            raise HTTPException(status_code=404, detail="link not found")
        await repository.delete(link)
    return {"deleted": True}
