"""重命名文档：同步更新 Postgres 与 Qdrant 两侧的 filename。

文档的展示名存在两处，必须一起改，否则会出现「列表里叫 A、引用来源显示 B」：
- Postgres ``documents.filename`` —— 文档管理页展示
- Qdrant 每个向量的 payload ``filename`` —— 问答的「引用来源」展示

只改一处的后果：引用卡片会显示旧名，用户对不上号。

用法：
    uv run python scripts/rename_document.py --list
    uv run python scripts/rename_document.py <doc_id 或唯一前缀> "<新文件名>"

示例：
    uv run python scripts/rename_document.py 4404eeb9 "培正教〔2024〕17号-通知.pdf"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings

# 必须在建引擎前改掉，否则 debug=true 会 echo 全部 SQL
settings.debug = False

from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import select, update

from app.storage.postgres import Document
from app.storage.qdrant import get_qdrant_store
from app.storage.session import get_session


async def _list_documents() -> int:
    async with get_session() as session:
        result = await session.execute(select(Document).order_by(Document.created_at))
        docs = result.scalars().all()

    if not docs:
        print("库中暂无文档。")
        return 0

    print(f"{'doc_id':<38} {'分块':>4}  文件名")
    for d in docs:
        print(f"{d.id:<38} {d.chunk_count:>4}  {d.filename}")
    return 0


async def _resolve_doc_id(prefix: str) -> str | None:
    """支持完整 id 或唯一前缀。返回 None 表示有歧义或未找到。"""
    async with get_session() as session:
        result = await session.execute(select(Document.id))
        ids = [row[0] for row in result.all()]

    if prefix in ids:
        return prefix
    matches = [i for i in ids if i.startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"前缀「{prefix}」匹配到多个文档，请给更长的前缀：")
        for m in matches:
            print(f"  - {m}")
    else:
        print(f"未找到文档：{prefix}")
    return None


async def _rename(doc_id: str, new_name: str) -> int:
    new_name = new_name.strip()
    if not new_name:
        print("新文件名不能为空。")
        return 1

    async with get_session() as session:
        result = await session.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if doc is None:
            print(f"未找到文档：{doc_id}")
            return 1
        old_name = doc.filename
        await session.execute(
            update(Document).where(Document.id == doc_id).values(filename=new_name)
        )
        await session.commit()

    # 同步 Qdrant payload；用 doc_id 过滤，一次覆盖该文档全部向量
    store = get_qdrant_store()
    await store._client.set_payload(
        collection_name=store._collection,
        payload={"filename": new_name},
        points=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]),
    )

    # 回读校验，确认两侧确实一致
    agg, offset = {}, None
    while True:
        pts, offset = await store._client.scroll(
            collection_name=store._collection,
            limit=512,
            offset=offset,
            scroll_filter=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
            with_payload=["filename"],
            with_vectors=False,
        )
        for p in pts:
            name = (p.payload or {}).get("filename")
            agg[name] = agg.get(name, 0) + 1
        if offset is None:
            break

    print(f"doc_id: {doc_id}")
    print(f"  旧名: {old_name}")
    print(f"  新名: {new_name}")
    print(f"  Qdrant: {sum(agg.values())} 个向量已更新，payload 中的 filename 取值 = {list(agg)}")

    if list(agg) != [new_name]:
        print("  !! 两侧不一致，请复查。")
        return 1
    print("  Postgres 与 Qdrant 已一致。")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description="重命名文档（同步 Postgres 与 Qdrant）")
    parser.add_argument("doc_id", nargs="?", help="文档 id 或其唯一前缀")
    parser.add_argument("new_name", nargs="?", help="新文件名")
    parser.add_argument("--list", action="store_true", help="列出全部文档")
    args = parser.parse_args()

    if args.list or not args.doc_id:
        return await _list_documents()

    if not args.new_name:
        print("请提供新文件名。用法：rename_document.py <doc_id|前缀> \"<新文件名>\"")
        return 1

    doc_id = await _resolve_doc_id(args.doc_id)
    if doc_id is None:
        return 1
    return await _rename(doc_id, args.new_name)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
