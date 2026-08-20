"""FastAPI 依赖：从请求中提取并验证当前用户。"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select

from app.auth.jwt import decode_access_token
from app.auth.models import User
from app.storage.session import get_session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """从 Bearer 令牌中解析并返回当前用户。未认证则 401。"""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exc
    try:
        payload = decode_access_token(token)
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exc
    except Exception:
        raise credentials_exc

    async with get_session() as session:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user is None:
            raise credentials_exc
        return user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """要求当前用户是管理员或站长，否则 403。"""
    if current_user.role not in ("admin", "owner"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


async def get_current_owner(current_user: User = Depends(get_current_user)) -> User:
    """要求当前用户是站长，否则 403。"""
    if current_user.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要站长权限",
        )
    return current_user


CurrentUser = User


async def get_current_user_optional(token: str | None = Depends(oauth2_scheme)) -> User | None:
    """可选鉴权：有令牌则验证，无则返回 None（开发模式友好）。"""
    if token is None:
        return None
    return await get_current_user(token)
