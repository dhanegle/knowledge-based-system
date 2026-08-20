"""管理员用户管理 API：列表 / 详情 / 删除 / 改角色 / 重置密码。

权限层级：
- 站长(owner)：可管理所有人（管理员 + 普通用户），唯一能修改角色的角色
- 管理员(admin)：只能管理普通用户，不能操作其他管理员或站长，不能改角色
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete, select

from app.auth.dependencies import get_current_admin
from app.auth.models import User
from app.auth.password import hash_password
from app.storage.conversation import Conversation, Message
from app.storage.session import get_session

router = APIRouter(prefix="/admin", tags=["admin"])

PRIVILEGED_ROLES = {"admin", "owner"}


class UpdateRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(admin|user)$")


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=128)


def _check_target_permission(target: User, current_user: User) -> None:
    """管理员不能操作其他管理员或站长；只有站长可以。"""
    if target.role in PRIVILEGED_ROLES and current_user.role != "owner":
        raise HTTPException(status_code=403, detail="无权操作其他管理员")


@router.get("/users")
async def list_users(current_user: User = Depends(get_current_admin)):
    """列出所有用户。"""
    async with get_session() as session:
        result = await session.execute(select(User).order_by(User.created_at.asc()))
        users = result.scalars().all()
        return [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ]


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    current_user: User = Depends(get_current_admin),
):
    """查询单个用户详情。"""
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "created_at": user.created_at.isoformat(),
        }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_admin),
):
    """删除用户及其所有对话。不能删除自己。管理员不能删除其他管理员/站长。"""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己")

    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")

        _check_target_permission(user, current_user)

        # 先删该用户的对话和消息
        conv_ids_result = await session.execute(
            select(Conversation.id).where(Conversation.user_id == user_id)
        )
        conv_ids = [row[0] for row in conv_ids_result.all()]
        if conv_ids:
            await session.execute(
                sa_delete(Message).where(Message.conversation_id.in_(conv_ids))
            )
            await session.execute(
                sa_delete(Conversation).where(Conversation.id.in_(conv_ids))
            )

        await session.delete(user)
        await session.commit()
        return {"deleted": True, "id": user_id}


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    req: UpdateRoleRequest,
    current_user: User = Depends(get_current_admin),
):
    """修改用户角色。仅站长可操作。不能修改自己的角色。"""
    if current_user.role != "owner":
        raise HTTPException(status_code=403, detail="仅站长可修改用户角色")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")

    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        # 不能修改站长的角色
        if user.role == "owner":
            raise HTTPException(status_code=400, detail="不能修改站长的角色")

        user.role = req.role
        await session.commit()
        return {"id": user_id, "role": req.role}


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    req: ResetPasswordRequest,
    current_user: User = Depends(get_current_admin),
):
    """重置用户密码。管理员只能重置普通用户密码，站长可重置所有人（除自己）。"""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能重置自己的密码")

    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")

        _check_target_permission(user, current_user)

        user.hashed_password = hash_password(req.new_password)
        await session.commit()
        return {"id": user_id, "password_reset": True}
