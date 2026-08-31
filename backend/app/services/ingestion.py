"""文档解析与入库管线（阶段1 的「入库流」）。

切分策略（面试场景关键）：不按固定字数切，而是「按题切分」——
一道题(含答案)作为一个 chunk，保住单题语义完整性，检索质量更好，
也正好对应你完成标准里的「引用溯源」（每条都能回到具体某题）。
"""
from app.core.config import settings
from app.services import embeddings
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


def split_generic(text: str, source: str, chunk_size: int = 500, overlap: int = 80) -> list[dict]:
    """通用兜底切分：给「不是 ### Q 题库排版」的文档（Word 正文 / PDF / 网页 / 表格）用。

    为什么必须要有兜底：
      parse_markdown 只认 `### Q1.` 结构。你传一份普通 Word 面经，
      里面根本没有 ### 标记，parse_markdown 会返回空 -> 入库 0 条 -> 提问永远答不上来。
      这就是「文件类型放开但功能没打通」的典型坑，兜底切分是必需品而非锦上添花。

    策略：按空行分段 -> 累积到 chunk_size 切一片 -> 保留 overlap 字做上下文衔接
          （overlap 能避免一句话被腰斩在两片里，检索命中率更高）。
    """
    # 统一换行，去掉多余空行
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0

    for para in paragraphs:
        # 单段就超过 chunk_size：先按句号再切一刀，避免生成一个超大 chunk
        if len(para) > chunk_size * 1.5:
            if buf:
                chunks.append("\n".join(buf))
                buf, buf_len = [], 0
            pieces = _hard_split(para, chunk_size)
            chunks.extend(pieces)
            continue

        buf.append(para)
        buf_len += len(para)
        if buf_len >= chunk_size:
            chunks.append("\n".join(buf))
            # overlap：把上一片尾部的一段内容带进下一片，保住跨片的语义连续性
            if overlap > 0 and buf:
                tail = buf[-1]
                buf = [tail[-overlap:]] if len(tail) > overlap else [tail]
                buf_len = len(buf[0])
            else:
                buf, buf_len = [], 0

    if buf:
        chunks.append("\n".join(buf))

    out = []
    for idx, c in enumerate(chunks, start=1):
        c = c.strip()
        if not c:
            continue
        out.append(
            {
                "id": f"{source}__g{idx}",
                "text": c,
                "metadata": {
                    "source": source,
                    "subject": "通用文档",
                    "q_index": idx,
                    "title": _short_title(c),
                },
            }
        )
    return out


def _hard_split(para: str, size: int) -> list[str]:
    """把超长段落按中文句号/分号硬切成若干片。"""
    import re

    # 中文句号、问号、感叹号、分号后断句，保留标点
    sentences = re.split(r"(?<=[。！？；!?;])", para)
    pieces, cur = [], ""
    for s in sentences:
        if len(cur) + len(s) > size and cur:
            pieces.append(cur.strip())
            cur = s
        else:
            cur += s
    if cur.strip():
        pieces.append(cur.strip())
    return [p for p in pieces if p]


def _short_title(chunk: str, limit: int = 24) -> str:
    """取 chunk 首行前 N 字作标题，方便引用溯源时一眼看出来源片段。"""
    first = chunk.strip().splitlines()[0] if chunk.strip() else ""
    first = first.lstrip("#").strip()
    return (first[:limit] + "…") if len(first) > limit else (first or "片段")


def ingest_text(text: str, source: str) -> int:
    """解析 -> 向量化 -> 写 Chroma，返回入库条数。

    双策略：先按题库结构（### Q）切，切不出来再走通用切分兜底。
    """
    parsed = parse_markdown(text, source)
    if not parsed:
        # 没有 ### Q 结构 —— 普通 Word/PDF/网页/表格文档，用通用切分
        parsed = split_generic(text, source)
    if not parsed:
        return 0
    # 批量向量化（入库与检索同一模型，坐标同源）
    texts = [p["text"] for p in parsed]
    vectors = embeddings.embed_texts(texts)
    for p, vec in zip(parsed, vectors):
        p["vector"] = vec
    add_chunks(parsed)
    return len(parsed)
