"""清理 Qdrant 中的孤儿向量。

**孤儿向量** = Qdrant 里存在某个 doc_id 的向量，但 Postgres 已无对应文档行。

危害：向量检索不过滤文档是否存在，所以这些块仍会被命中并作为「引用来源」
返回，用户会看到一个在文档列表中根本不存在、也无法管理的文档。

**默认只检查、不删除。** 必须显式加 ``--apply`` 才会真正删除。

用法：
    uv run python scripts/cleanup_orphan_vectors.py            # 仅检查（安全）
    uv run python scripts/cleanup_orphan_vectors.py --apply    # 实际删除

退出码：0 表示无孤儿；1 表示存在孤儿（便于接入 CI / 巡检）。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings

# settings.debug 为 true 时 create_async_engine(echo=True) 会打印每条 SQL，
# 淹没有效输出。echo 在建引擎时读取此值，故必须在任何 DB 访问之前改掉。
# 仅影响本进程；本脚本只读，不改变调试语义。
settings.debug = False

from app.storage.qdrant import get_qdrant_store
from app.storage.session import get_session


async def _collect_qdrant_docs() -> dict[str, dict]:
    """扫描整个集合，按 doc_id 聚合点数与文件名。"""
    store = get_qdrant_store()
    client = store._client  # 复用已配置的连接，避免第二个客户端
    collection = store._collection

    agg: dict[str, dict] = defaultdict(lambda: {"points": 0, "filenames": set()})
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=collection,
            limit=512,
            offset=offset,
            with_payload=["doc_id", "filename"],
            with_vectors=False,
        )
        for p in points:
            payload = p.payload or {}
            doc_id = payload.get("doc_id") or "<missing>"
            agg[doc_id]["points"] += 1
            if payload.get("filename"):
                agg[doc_id]["filenames"].add(payload["filename"])
        if offset is None:
            break
    return agg


async def _collect_postgres_docs() -> dict[str, dict]:
    """读取 Postgres 中的文档行。"""
    from sqlalchemy import select

    from app.storage.postgres import Document

    async with get_session() as session:
        result = await session.execute(select(Document))
        return {
            d.id: {"filename": d.filename, "chunk_count": d.chunk_count}
            for d in result.scalars().all()
        }


async def main() -> int:
    parser = argparse.ArgumentParser(description="清理 Qdrant 孤儿向量")
    parser.add_argument("--apply", action="store_true", help="真正删除孤儿向量（默认仅检查）")
    args = parser.parse_args()

    qdrant_docs = await _collect_qdrant_docs()
    pg_docs = await _collect_postgres_docs()

    total_points = sum(v["points"] for v in qdrant_docs.values())
    orphan_ids = [d for d in qdrant_docs if d not in pg_docs]
    # 反向问题：文档存在但向量缺失，检索永远命中不到，同样值得暴露
    missing_ids = [d for d in pg_docs if d not in qdrant_docs]

    print(f"Qdrant: {len(qdrant_docs)} 个 doc_id / {total_points} 个向量")
    print(f"Postgres: {len(pg_docs)} 个文档")
    print()

    if not orphan_ids and not missing_ids:
        print("未发现不一致，无需处理。")
        return 0

    if orphan_ids:
        orphan_points = sum(qdrant_docs[d]["points"] for d in orphan_ids)
        pct = (orphan_points / total_points * 100) if total_points else 0
        print(f"孤儿向量：{len(orphan_ids)} 个 doc_id / {orphan_points} 个向量"
              f"（占 {pct:.1f}%）")
        for d in sorted(orphan_ids, key=lambda x: -qdrant_docs[x]["points"]):
            info = qdrant_docs[d]
            names = "、".join(sorted(info["filenames"])) or "<无文件名>"
            print(f"  - {d}  {info['points']:>4} 向量  {names}")
        print()

    if missing_ids:
        print(f"向量缺失：{len(missing_ids)} 个文档在 Qdrant 中无任何向量")
        for d in missing_ids:
            print(f"  - {d}  {pg_docs[d]['filename']}  (chunk_count={pg_docs[d]['chunk_count']})")
        print()

    if not args.apply:
        print("以上为检查结果，未做任何修改。加 --apply 执行删除。")
        return 1 if orphan_ids else 0

    if orphan_ids:
        store = get_qdrant_store()
        deleted = 0
        for d in orphan_ids:
            if d == "<missing>":
                print("跳过 doc_id 缺失的点，请手工核对。")
                continue
            await store.delete_by_doc_id(d)
            deleted += 1
        print(f"已删除 {deleted} 个孤儿 doc_id 的全部向量。")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
