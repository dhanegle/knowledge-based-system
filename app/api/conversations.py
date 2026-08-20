"""对话历史 API：创建 / 列表 / 详情 / 删除 / 更新标题。"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, delete as sa_delete, update

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.errors import DocumentNotFoundError
from app.storage.conversation import Conversation, Message
from app.storage.session import get_session

router = APIRouter(prefix="/conversations", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    title: str | None = Field(None, max_length=255)


class UpdateConversationRequest(BaseModel):
    title: str = Field(..., max_length=255)


@router.get("")
async def list_conversations(current_user: User = Depends(get_current_user)):
    """列出当前用户的所有对话（按更新时间降序）。"""
    async with get_session() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.user_id == current_user.id)
            .order_by(Conversation.updated_at.desc())
        )
        convs = result.scalars().all()
        return [
            {
                "id": c.id,
                "title": c.title,
                "created_at": c.created_at.isoformat(),
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in convs
        ]


@router.post("", status_code=201)
async def create_conversation(
    req: CreateConversationRequest,
    current_user: User = Depends(get_current_user),
):
    """创建新对话。"""
    conv = Conversation(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        title=req.title or "新对话",
    )
    async with get_session() as session:
        session.add(conv)
        await session.commit()
        return {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at.isoformat(),
        }


@router.get("/{conv_id}")
async def get_conversation(
    conv_id: str,
    current_user: User = Depends(get_current_user),
):
    """获取对话详情 + 所有消息。"""
    async with get_session() as session:
        result = await session.execute(
            select(Conversation).where(
                Conversation.id == conv_id,
                Conversation.user_id == current_user.id,
            )
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            raise DocumentNotFoundError("对话不存在")

        msg_result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at.asc())
        )
        messages = msg_result.scalars().all()

        return {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "sources": json.loads(m.sources) if m.sources else [],
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
        }


@router.delete("/{conv_id}")
async def delete_conversation(
    conv_id: str,
    current_user: User = Depends(get_current_user),
):
    """删除对话及其所有消息。"""
    async with get_session() as session:
        result = await session.execute(
            select(Conversation).where(
                Conversation.id == conv_id,
                Conversation.user_id == current_user.id,
            )
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            raise DocumentNotFoundError("对话不存在")

        await session.execute(
            sa_delete(Message).where(Message.conversation_id == conv_id)
        )
        await session.delete(conv)
        await session.commit()
        return {"deleted": True, "id": conv_id}


@router.patch("/{conv_id}")
async def update_conversation(
    conv_id: str,
    req: UpdateConversationRequest,
    current_user: User = Depends(get_current_user),
):
    """更新对话标题。"""
    async with get_session() as session:
        result = await session.execute(
            update(Conversation)
            .where(
                Conversation.id == conv_id,
                Conversation.user_id == current_user.id,
            )
            .values(title=req.title)
            .returning(Conversation.id)
        )
        if result.scalar_one_or_none() is None:
            raise DocumentNotFoundError("对话不存在")
        await session.commit()
        return {"id": conv_id, "title": req.title}
