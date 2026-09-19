"""Shared FastAPI dependencies: operator Basic auth and a per-request session."""
from __future__ import annotations

import secrets
from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session_factory

_basic = HTTPBasic()


def require_operator(credentials: HTTPBasicCredentials = Depends(_basic), settings: Settings = Depends(get_settings)) -> str:
    valid_user = secrets.compare_digest(credentials.username, settings.operator_username)
    valid_pass = secrets.compare_digest(credentials.password, settings.operator_password)
    if not (valid_user and valid_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid operator credentials",
            headers={"WWW-Authenticate": "Basic"},
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
