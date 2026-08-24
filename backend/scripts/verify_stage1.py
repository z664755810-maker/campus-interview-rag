"""阶段1 验证脚本：入库样例 + 检索若干问题，确认 top-k 命中相关题。

直接调用 service 层（不依赖 HTTP），便于在终端快速验证「向量化→Chroma→检索」整条链路。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import ingestion
from app.services.vector_store import search

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(BASE, "data", "sample_interview.md")

with open(SAMPLE, "r", encoding="utf-8") as f:
    text = f.read()

n = ingestion.ingest_text(text, source="sample_interview.md")
print(f"[入库] 成功写入 {n} 条面试题片段")

for q in [
    "HashMap 为什么线程不安全",
    "进程和线程的区别",
    "TCP 三次握手",
    "数据库索引为什么快",
]:
    print(f"\n=== 查询: {q} ===")
    for r in search(q, top_k=2):
        print(
            f"  距离={r['distance']:.4f} | "
            f"({r['metadata']['subject']}) {r['metadata']['title']}"
        )
