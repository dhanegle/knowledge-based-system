"""JWT 令牌创建与验证。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings


def create_access_token(data: dict) -> str:
    """生成 JWT 令牌。data 中应包含 'sub'（用户名）。"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """解码并验证 JWT 令牌，返回 payload。"""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return payload
