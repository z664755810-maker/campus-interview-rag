"""文档解析与入库管线（阶段1 的「入库流」）。

切分策略（面试场景关键）：不按固定字数切，而是「按题切分」——
一道题(题面+答案)作为一个 chunk，保住单题语义完整性，检索质量更好，
也正好对应你完成标准里的「引用溯源」（每条都能回到具体某题）。

题面 vs 答案建模（段 A 修 #1 + 段 B 修 #1 的根因）：
  每条 chunk 同时携带：
    - text          ：chunk 全文（题面+答案），入库实际存进 Chroma 的内容
    - question_only ：剥离题号/难度标签后的「纯题干」，供 UI 默认只显示题干
    - content       ：text 别名（前端沿用字段名），揭晓答案时整段显示
    - metadata      ：difficulty 难度、subject 学科、q_index 题号、title 原标题、source 来源
  讲师讲解：之前 content 把题面和答案整块塞一个字段，前端一渲染就泄露答案；
  现在把两者显式拆开，是「数据建模跟着业务走」的标准操作。
"""
import re

from app.core.config import settings
from app.services import embeddings
from app.services.vector_store import add_chunks


# 标题识别："Q1. [基础] HashMap 的底层原理是什么？"
# 三组捕获：题号 / 难度(可缺省) / 纯题干
_TITLE_PATTERN = re.compile(r"^(Q\d+)\.\s*(?:\[([^\]]+)\])?\s*(.+?)\s*$")
# 通用难度白名单（不在此列表则视为"基础"，避免脏数据污染筛选）
_DIFFICULTY_WHITELIST = {"基础", "进阶", "困难"}
# 题型识别：在题干里出现特定模式就标 multi_choice/judge/code_output/qa
_QUESTION_TYPE_PATTERNS = [
    ("multi_choice", re.compile(r"（\s*[Aa]?[ \.]?(?:[Bb]|[Cc]|[Dd])\s*[）)]|下列[哪何]项|以下[哪何]项|选择")),
    ("judge", re.compile(r"对吗|对不对|是否正确|判断")),
    ("code_output", re.compile(r"输出什么|输出结果|打印什么|运行结果|console\.log|执行后|请问输出")),
]


def _split_question_title(raw_title: str) -> tuple[str, str, str]:
    """从 "Q1. [基础] HashMap 的底层原理是什么？" 解出 (题号, 难度, 纯题干)。

    解析失败的兜底：题号按 'Q?'、难度为 ''、题干为原串，让入库链路仍能跑。
    """
    m = _TITLE_PATTERN.match(raw_title)
    if not m:
        return ("Q?", "", raw_title)
    q_index, difficulty, plain = m.group(1), (m.group(2) or "").strip(), m.group(3).strip()
    if difficulty not in _DIFFICULTY_WHITELIST:
        # 难度标签缺失或不在白名单：当作"基础"，保证筛选 UI 不会因乱数据全空
        difficulty = "基础"
    return (q_index, difficulty, plain or raw_title)


def _detect_question_type(question_only: str, body: str) -> str:
    """从题干/正文识别题型，给前端按题型筛选用。

    识别顺序：multi_choice > judge > code_output > qa。
    """
    haystack = (question_only or "") + "\n" + (body or "")
    for tag, pat in _QUESTION_TYPE_PATTERNS:
        if pat.search(haystack):
            return tag
    return "qa"


def parse_markdown(text: str, source: str) -> list[dict]:
    """把面试题 markdown 解析成若干 chunk。

    约定格式：
      ## 科目名
      ### Q1. [难度] 问题标题
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
        q_index, difficulty, question_only = _split_question_title(buf_title)
        q_type = _detect_question_type(question_only, body)
        # 入库正文保留：纯题干 + 答案（用于检索能命中题干，揭晓答案显示全段）
        chunks.append(
            {
                "subject": subject,
                "title": buf_title,
                "q_index": q_index,
                "difficulty": difficulty,
                "question_only": question_only,
                "q_type": q_type,
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

    # 组装入库结构：带元数据（科目/题号/难度/题型/来源），便于引用溯源 + 难度筛选
    out = []
    for idx, c in enumerate(chunks, start=1):
        out.append(
            {
                # 注意：id 用全局自增序号，不能用 q_index——
                # 样例题库每个学科都从 Q1 重新编号，直接拿 q_index 当 id 会跨科撞车
                # （DuplicateIDError）。q_index 仅作为 metadata 供前端展示题号。
                "id": f"{source}__{idx}",
                "text": c["content"],
                "question_only": c["question_only"],
                "q_type": c["q_type"],
                "metadata": {
                    "source": source,
                    "subject": c["subject"],
                    "q_index": c["q_index"],
                    "title": c["title"],
                    "difficulty": c["difficulty"],
                    "q_type": c["q_type"],
                    # 摘要放 metadata：Chroma 的 document 仍是整段（含答案），
                    # 但前端 /random、/by-subject 不用解析 document 就能拿到题干
                    "question_only": c["question_only"],
                },
            }
        )
    # 兜底：万一 metadata 拼写错了要炸，立刻抛出可读异常
    for o in out:
        assert "difficulty" in o["metadata"], f"metadata 缺 difficulty：{o}"
        assert "q_type" in o["metadata"], f"metadata 缺 q_type：{o}"
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
        title_for_chunk = _short_title(c)
        first_line = c.splitlines()[0] if c.splitlines() else ""
        _, _, plain_q = _split_question_title(first_line)
        plain_q = plain_q if plain_q else first_line[:60]
        out.append(
            {
                "id": f"{source}__g{idx}",
                "text": c,
                "question_only": plain_q[:80] + ("…" if len(plain_q) > 80 else ""),
                "q_type": "qa",
                "metadata": {
                    "source": source,
                    "subject": "通用文档",
                    "q_index": idx,
                    "title": title_for_chunk,
                    "difficulty": "通用",
                    "q_type": "qa",
                    "question_only": plain_q[:80] + ("…" if len(plain_q) > 80 else ""),
                },
            }
        )
    for o in out:
        assert "difficulty" in o["metadata"], f"metadata 缺 difficulty：{o}"
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
