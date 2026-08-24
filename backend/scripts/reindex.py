"""重新索引脚本：清空旧 collection -> 重新灌入扩充后的样例语料。

用途：当我们扩充了 data/sample_interview.md（科目/题目数量变化）后，
旧的全局序号会错位，直接 upsert 会留下孤儿数据。本脚本先 delete_collection
再重灌，保证线上 KB 与源文件完全一致。

用法（在 backend 目录下、3.12 venv 内）：
    .venv/Scripts/python.exe scripts/reindex.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb

from app.core.config import settings
from app.services import ingestion
from app.services.vector_store import COLLECTION_NAME, get_client, search

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(BASE, "data", "sample_interview.md")


def reset_collection():
    client = get_client()
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"[清库] 已删除旧 collection: {COLLECTION_NAME}")
    except Exception as e:
        # 不存在时忽略
        print(f"[清库] 无需删除（{e}）")


def main():
    reset_collection()
    with open(SAMPLE, "r", encoding="utf-8") as f:
        text = f.read()
    n = ingestion.ingest_text(text, source="sample_interview.md")
    print(f"[入库] 成功写入 {n} 条面试题片段（来自 sample_interview.md）")

    print("\n=== 抽样检索验证 ===")
    for q in [
        "HashMap 为什么线程不安全",
        "TCP 三次握手的作用",
        "Redis 缓存穿透怎么解决",
        "Vue 的响应式原理",
        "事务的隔离级别有哪些",
    ]:
        print(f"\n--- 查询: {q} ---")
        for r in search(q, top_k=2):
            meta = r["metadata"]
            print(
                f"  距离={r['distance']:.4f} | "
                f"[{meta.get('subject')}] {meta.get('title')}"
            )


if __name__ == "__main__":
    main()
