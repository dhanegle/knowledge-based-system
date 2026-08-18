"""鉴权 API：注册 / 登录 / 刷新令牌。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import create_access_token
from app.auth.models import User
from app.auth.password import hash_password, verify_password
from app.storage.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, session: AsyncSession = Depends(get_session)):
    # 检查用户名是否已存在
    existing = await session.execute(select(User).where(User.username == req.username))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="用户名已存在")
    # 检查邮箱
    existing_email = await session.execute(select(User).where(User.email == req.email))
    if existing_email.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="邮箱已注册")

    user = User(
        id=str(uuid.uuid4()),
        username=req.username,
        email=req.email,
        hashed_password=hash_password(req.password),
    )
    session.add(user)
    await session.commit()

    token = create_access_token({"sub": user.username})
    return TokenResponse(access_token=token, username=user.username)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token({"sub": user.username})
    return TokenResponse(access_token=token, username=user.username)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(current_user: User = Depends(get_current_user)):
    token = create_access_token({"sub": current_user.username})
    return TokenResponse(access_token=token, username=current_user.username)


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "created_at": current_user.created_at.isoformat(),
    }
