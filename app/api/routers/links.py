from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import current_user
from app.api.schemas import LinkIn, LinkOut
from app.config import get_settings
from app.database.database import get_session
from app.database.models import User
from app.database.repositories.link_repository import LinkRepository
from app.utils.credentials import (
    CredentialKeyError,
    decrypt_credential,
    encrypt_credential,
    from_storage,
    to_storage,
)

router = APIRouter(prefix="/api", tags=["links"])


def _ensure_credentials_enabled() -> None:
    """Reject credential writes when the master key is not configured.

    The Mini App also hides the "save login" toggle when the feature is
    off, but the server is the source of truth: never accept credentials
    we cannot later decrypt.
    """
    if not get_settings().credentials_enabled:
        raise HTTPException(
            status_code=503,
            detail="ذخیره رمز غیرفعال است؛ مدیر باید CREDENTIALS_MASTER_KEY را تنظیم کند",
        )


def _encrypt_or_clear(payload: LinkIn) -> tuple[str | None, str | None]:
    """Return ``(ciphertext_b64, wrapped_key_b64)`` for the payload.

    When the payload has no credentials, returns ``(None, None)`` so the
    caller can clear any previously stored value on update.
    """
    if payload.username is None or payload.password is None:
        return None, None
    _ensure_credentials_enabled()
    try:
        ciphertext, wrapped_key = encrypt_credential(
            {"username": payload.username, "password": payload.password}
        )
    except CredentialKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    storage = to_storage(ciphertext, wrapped_key)
    return storage["ciphertext_b64"], storage["wrapped_key_b64"]


@router.get("/links", response_model=list[LinkOut])
async def list_links(
    user: Annotated[User, Depends(current_user)],
) -> list[LinkOut]:
    async with get_session() as session:
        links = await LinkRepository(session).list_by_user(user.id)
    return [
        LinkOut(
            id=link.id,
            title=link.title,
            url=link.url,
            description=link.description,
            has_credentials=link.has_credentials,
        )
        for link in links
    ]


@router.post("/links", response_model=LinkOut)
async def create_link(
    payload: LinkIn,
    user: Annotated[User, Depends(current_user)],
) -> LinkOut:
    ciphertext_b64, wrapped_key_b64 = _encrypt_or_clear(payload)
    async with get_session() as session:
        link = await LinkRepository(session).create(
            user_id=user.id,
            title=payload.title,
            url=payload.url,
            description=payload.description,
            ciphertext_b64=ciphertext_b64,
            wrapped_key_b64=wrapped_key_b64,
        )
    return LinkOut(
        id=link.id,
        title=link.title,
        url=link.url,
        description=link.description,
        has_credentials=link.has_credentials,
    )


@router.put("/links/{link_id}", response_model=LinkOut)
async def update_link(
    link_id: int,
    payload: LinkIn,
    user: Annotated[User, Depends(current_user)],
) -> LinkOut:
    ciphertext_b64, wrapped_key_b64 = _encrypt_or_clear(payload)
    async with get_session() as session:
        repository = LinkRepository(session)
        link = await repository.get(link_id, user.id)
        if link is None:
            raise HTTPException(status_code=404, detail="link not found")
        link = await repository.update(
            link,
            title=payload.title,
            url=payload.url,
            description=payload.description,
            ciphertext_b64=ciphertext_b64,
            wrapped_key_b64=wrapped_key_b64,
        )
    return LinkOut(
        id=link.id,
        title=link.title,
        url=link.url,
        description=link.description,
        has_credentials=link.has_credentials,
    )


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


@router.get("/links/{link_id}/credentials")
async def get_link_credentials(
    link_id: int,
    user: Annotated[User, Depends(current_user)],
) -> dict:
    """Decrypt and return the stored credentials for one link.

    Called by the Mini App right before opening the target site so the
    frontend can copy the password to the clipboard and (when the site
    supports it) build a ``https://user:pass@host`` auto-login URL.

    The endpoint returns ``has_credentials: false`` when no credential
    is stored, so the caller can fall back to a plain link open.
    """
    if not get_settings().credentials_enabled:
        raise HTTPException(status_code=503, detail="credential feature is disabled")
    async with get_session() as session:
        link = await LinkRepository(session).get(link_id, user.id)
    if link is None:
        raise HTTPException(status_code=404, detail="link not found")
    if not link.has_credentials:
        return {"has_credentials": False}
    try:
        ciphertext, wrapped_key = from_storage(
            link.ciphertext_b64 or "", link.wrapped_key_b64 or ""
        )
        payload = decrypt_credential(ciphertext, wrapped_key)
    except CredentialKeyError as exc:
        raise HTTPException(status_code=500, detail="credential cannot be decrypted") from exc
    return {
        "has_credentials": True,
        "username": payload.get("username", ""),
        "password": payload.get("password", ""),
        "url": link.url,
    }


@router.get("/links/{link_id}/bookmarklet")
async def get_link_bookmarklet(
    link_id: int,
    user: Annotated[User, Depends(current_user)],
) -> dict:
    """Return a ``javascript:`` bookmarklet URL that auto-fills the login form.

    The bookmarklet is a small piece of JavaScript that, when saved as a
    browser bookmark and tapped on the target site's login page, finds the
    username and password fields, fills them, and submits the form. This is
    the only way to achieve true auto-login on sites that use form-based
    authentication (which is virtually all modern sites).

    The credentials are embedded in the bookmarklet as plaintext JavaScript
    string literals. This is acceptable because:

    - The bookmarklet lives in the user's own browser bookmarks.
    - The user explicitly generated it for their own use.
    - There is no way to auto-fill a form without the plaintext being
      present in the JavaScript that runs on the page.

    The script tries multiple common selector strategies for username and
    password fields, then submits the first form it finds. It works on
    most Iranian university portals (Golestan, food systems, LMS).
    """
    if not get_settings().credentials_enabled:
        raise HTTPException(status_code=503, detail="credential feature is disabled")
    async with get_session() as session:
        link = await LinkRepository(session).get(link_id, user.id)
    if link is None:
        raise HTTPException(status_code=404, detail="link not found")
    if not link.has_credentials:
        return {"has_bookmarklet": False}
    try:
        ciphertext, wrapped_key = from_storage(
            link.ciphertext_b64 or "", link.wrapped_key_b64 or ""
        )
        payload = decrypt_credential(ciphertext, wrapped_key)
    except CredentialKeyError as exc:
        raise HTTPException(status_code=500, detail="credential cannot be decrypted") from exc

    # Build the bookmarklet. The JS tries several common input selectors,
    # fills the first match, and submits the enclosing form. Escaped for
    # use in a javascript: URL.
    import json as _json
    import urllib.parse

    username = payload.get("username", "")
    password = payload.get("password", "")

    js_code = f"""(function(){{
var u={_json.dumps(username)},p={_json.dumps(password)};
function setVal(el,v){{
  try{{
    var proto=Object.getPrototypeOf(el);
    var setter=Object.getOwnPropertyDescriptor(proto,'value')||{{}};
    if(setter&&setter.set){{setter.set.call(el,v);}}
    else{{el.value=v;}}
    el.dispatchEvent(new Event('input',{{bubbles:true}}));
    el.dispatchEvent(new Event('change',{{bubbles:true}}));
  }}catch(e){{el.value=v;}}
}}
var uf,pf;
var selectors=['input[name="username"]','input[name="user"]','input[name="login"]','input[name="UserID"]','input[name="uid"]','input[name="student_number"]','input[name="stid"]','input[name="national_id"]','input[name="code"]','input[type="text"]','input[type="email"]','input:not([type])'];
for(var i=0;i<selectors.length;i++){{var els=document.querySelectorAll(selectors[i]);for(var j=0;j<els.length;j++){{if(els[j].offsetParent!==null){{uf=els[j];break;}}}}if(uf)break;}}
var pfs=document.querySelectorAll('input[type="password"]');
for(var k=0;k<pfs.length;k++){{if(pfs[k].offsetParent!==null){{pf=pfs[k];break;}}}}
if(uf){{setVal(uf,u);}}
if(pf){{setVal(pf,p);}}
if(uf||pf){{var form=(pf||uf).closest('form');if(form){{form.submit();}}else{{alert('فرم پیدا نشد. مقادیر پر شدند؛ دکمه ورود را دستی بزنید.');}}}}
else{{alert('فیلد ورودی پیدا نشد. شاید در صفحه اشتباهی هستید.');}}
}})()"""

    bookmarklet_url = "javascript:" + urllib.parse.quote(js_code, safe="")
    return {
        "has_bookmarklet": True,
        "bookmarklet": bookmarklet_url,
        "title": link.title,
        "url": link.url,
    }
