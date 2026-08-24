"""文档解析与入库管线（阶段1 的「入库流」）。

切分策略（面试场景关键）：不按固定字数切，而是「按题切分」——
一道题(含答案)作为一个 chunk，保住单题语义完整性，检索质量更好，
也正好对应你完成标准里的「引用溯源」（每条都能回到具体某题）。
"""
from app.core.config import settings
from app.services import zhipu
from app.services.vector_store import add_chunks


def parse_markdown(text: str, source: str) -> list[dict]:
    """把面试题 markdown 解析成若干 chunk。

    约定格式：
      ## 科目名
      ### Q1. 问题标题
      答案内容...
    每个 ### Q 块 = 一个 chunk。
    """
    lines = text.splitlines()
    chunks = []
    subject = "未分类"
    buf_title = None
    buf_body = []

    def flush():
        if buf_title is None:
            return
        body = "\n".join(buf_body).strip()
        if not body:
            return
        chunks.append(
            {
                "subject": subject,
                "title": buf_title,
                "content": f"{buf_title}\n{body}",
            }
        )

    for line in lines:
        if line.startswith("## ") and not line.startswith("### "):
            flush()
            buf_title = None
            buf_body = []
            subject = line[3:].strip()
        elif line.startswith("### "):
            flush()
            buf_title = line[4:].strip()
            buf_body = []
        else:
            if buf_title is not None:
                buf_body.append(line)
    flush()

    # 组装入库结构：带元数据（科目/题号/来源），便于引用溯源
    out = []
    for idx, c in enumerate(chunks, start=1):
        out.append(
            {
                "id": f"{source}__{idx}",
                "text": c["content"],
                "metadata": {
                    "source": source,
                    "subject": c["subject"],
                    "q_index": idx,
                    "title": c["title"],
                },
            }
        )
    return out


def ingest_text(text: str, source: str) -> int:
    """解析 -> 向量化 -> 写 Chroma，返回入库条数。"""
    parsed = parse_markdown(text, source)
    if not parsed:
        return 0
    # 批量向量化（入库与检索同一模型，坐标同源）
    texts = [p["text"] for p in parsed]
    vectors = zhipu.embed_texts(texts)
    for p, vec in zip(parsed, vectors):
        p["vector"] = vec
    add_chunks(parsed)
    return len(parsed)
