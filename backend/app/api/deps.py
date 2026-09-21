"""Shared FastAPI dependencies: operator Basic auth and a per-request session.

Deliberately NO `WWW-Authenticate: Basic` header on the 401s below. Chrome
treats that challenge as an invitation to raise its own native credentials
dialog and withholds the response from `fetch()` while the dialog is up, so
the SPA's auth probe never settled and the app rendered a permanently blank
page instead of its own sign-in form. Omitting the challenge keeps the 401 a
plain, readable API response. Anything re-adding it must solve that first.
See docs/26, 2026-09-21.
"""
from __future__ import annotations

import secrets
from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session_factory

_basic = HTTPBasic(auto_error=False)


def require_operator(credentials: HTTPBasicCredentials | None = Depends(_basic), settings: Settings = Depends(get_settings)) -> str:
    if not settings.operator_auth_enabled:
        return settings.operator_username
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="operator credentials required",
        )
    valid_user = secrets.compare_digest(credentials.username, settings.operator_username)
    valid_pass = secrets.compare_digest(credentials.password, settings.operator_password)
    if not (valid_user and valid_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid operator credentials",
        )
    return credentials.username


async def get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
