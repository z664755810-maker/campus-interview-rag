"""文档与检索相关接口（阶段1~2）。

这里直接用 Pydantic 模型定义请求体，FastAPI 会自动做「请求校验」——
字段缺失 / 类型错误会被 field_validator 拦截并返回 422，省去我们手写一堆 if。
这正好呼应你完成标准里的「真实性业务：输入校验」。
"""
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, UploadFile, File
from pydantic import BaseModel, field_validator
from typing import Literal

from app.services import ingestion
from app.services import parsers
from app.services.rag import ask as rag_ask
from app.services.vector_store import search, get_collection, COLLECTION_NAME

router = APIRouter()

# 单文件体积上限（字节）。10MB 对「简历/面经/题库」绰绰有余，
# 同时挡住误传视频/压缩包把内存打爆 —— PaaS 免费层内存通常只有 512MB。
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


class SearchRequest(BaseModel):
    query: str
    top_k: int | None = None

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("query 不能为空")
        return v

    @field_validator("top_k")
    @classmethod
    def top_k_in_range(cls, v):
        if v is not None and (v < 1 or v > 10):
            raise ValueError("top_k 需在 1~10 之间")
        return v


class AskRequest(BaseModel):
    query: str
    top_k: int | None = None
    mode: Literal["answer", "summary", "action_items", "risk_check"] = "answer"

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("query 不能为空")
        return v

    @field_validator("top_k")
    @classmethod
    def top_k_in_range(cls, v):
        if v is not None and (v < 1 or v > 10):
            raise ValueError("top_k 需在 1~10 之间")
        return v


@router.get("/documents/stats")
def stats():
    """返回当前题库状态：总片段数 + 各来源文件分布。

    为什么需要：PaaS 免费层重启会丢数据，启动时的 seed 会自动灌 70 条示例题。
    如果前端不主动拉一次，用户看到的「已索引 0 段」与真实情况不符，
    会误以为系统坏了。前端 onMounted 调它做一次真实状态同步。
    """
    try:
        col = get_collection(COLLECTION_NAME)
        total = col.count()
        sources: dict[str, int] = {}
        if total:
            # 只取元数据即可，不需要 embeddings/documents，省带宽
            res = col.get(include=["metadatas"])
            for meta in res.get("metadatas") or []:
                src = (meta or {}).get("source", "未知来源")
                sources[src] = sources.get(src, 0) + 1
        return {
            "count": total,
            "sources": [{"source": k, "chunks": v} for k, v in sources.items()],
        }
    except Exception as e:
        # 统计失败不影响主流程，返回 0 让前端不强依赖
        return {"count": 0, "sources": [], "warning": str(e)}


@router.get("/documents/formats")
def list_formats():
    """把「支持哪些格式」回给前端，前后端共用同一份白名单，避免两处维护不一致。"""
    return {
        "extensions": sorted(parsers.SUPPORTED_EXTENSIONS.keys()),
        "accept": parsers.ACCEPT_ATTR,
        "labels": parsers.EXT_LABEL,
        "unsupported_hints": parsers.UNSUPPORTED_HINTS,
        "max_upload_mb": MAX_UPLOAD_MB,
    }


@router.get("/documents/analytics")
def analytics():
    """返回能展示在简历/仪表盘中的业务指标：覆盖主题、文档格式、检索上下文规模等。"""
    try:
        col = get_collection(COLLECTION_NAME)
        total = col.count()
        subject_counts: dict[str, int] = {}
        source_counts: dict[str, int] = {}
        chunk_chars = 0
        if total:
            res = col.get(include=["metadatas", "documents"])
            documents = res.get("documents") or []
            for idx, meta in enumerate(res.get("metadatas") or []):
                m = meta or {}
                src = str(m.get("source", "未知来源"))
                subject = str(m.get("subject", "未分类")).strip() or "未分类"
                source_counts[src] = source_counts.get(src, 0) + 1
                if subject != "未分类":
                    subject_counts[subject] = subject_counts.get(subject, 0) + 1
                if idx < len(documents):
                    try:
                        chunk_chars += len(documents[idx] or "")
                    except Exception:
                        pass

        top_subjects = [
            {"name": name, "count": count}
            for name, count in sorted(subject_counts.items(), key=lambda x: (-x[1], x[0]))[:6]
        ]
        return {
            "total_chunks": total,
            "source_count": len(source_counts),
            "subject_count": len(subject_counts),
            "top_subjects": top_subjects,
            "avg_chunks_per_doc": round(total / max(len(source_counts), 1), 2),
            "avg_chars_per_chunk": round(chunk_chars / max(total, 1), 1),
            "top_k_default": 5,
            "business_modes": 4,
            "format_support": 14,
        }
    except Exception:
        return {
            "total_chunks": 0,
            "source_count": 0,
            "subject_count": 0,
            "top_subjects": [],
            "avg_chunks_per_doc": 0,
            "avg_chars_per_chunk": 0,
            "top_k_default": 5,
            "business_modes": 4,
            "format_support": 14,
        }


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """上传文档 -> 解析 -> 切分 -> 向量化 -> 入库。

    业务加固点（对应「真实业务场景」的考量）：
      1. 体积上限：先读字节再判大小，超限 413，防止大文件打爆免费层内存
      2. 类型白名单：按扩展名校验，不支持的格式给出「怎么转换」的可执行建议
      3. 解析失败 / 空内容：明确 400 + 人话提示，而不是让用户看到 500
    """
    filename = file.filename or ""
    if not filename.strip():
        raise HTTPException(status_code=400, detail="文件名为空，无法入库")

    raw = await file.read()

    if not raw:
        raise HTTPException(status_code=400, detail="文件内容为空，请确认文件本身有内容")
    if len(raw) > MAX_UPLOAD_BYTES:
        size_mb = len(raw) / 1024 / 1024
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{size_mb:.1f}MB），单个文件请控制在 {MAX_UPLOAD_MB}MB 以内",
        )

    try:
        text = parsers.extract_text(filename, raw)
    except parsers.UnsupportedFileError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except parsers.ParseError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        count = ingestion.ingest_text(text, source=filename)
    except Exception as e:
        # 向量化/写库失败多半是上游 API 问题，转成 502 而不是 500，便于前端区分提示
        raise HTTPException(status_code=502, detail=f"入库失败（向量服务异常）：{e}")

    if count == 0:
        raise HTTPException(status_code=400, detail="文档解析成功，但没有切出可入库的内容")

    return {"ingested": count, "source": filename, "chars": len(text)}


@router.post("/documents/load-sample")
def load_sample():
    """一键载入内置企业知识样例库。

    这份样例库覆盖内部政策、流程、风险与工作协同四类高频场景，
    能让用户在第一次打开界面时就直接体验“真实企业知识助手”的核心玩法。
    """
    sample_candidates = [
        Path(__file__).resolve().parent.parent.parent / "data" / "enterprise_knowledge.md",
        Path(__file__).resolve().parent.parent.parent / "data" / "sample_interview.md",
    ]
    sample_path = next((p for p in sample_candidates if p.exists()), None)
    if sample_path is None:
        raise HTTPException(status_code=404, detail="服务端未找到内置知识示例文件")
    try:
        text = sample_path.read_text(encoding="utf-8")
        count = ingestion.ingest_text(text, source=sample_path.name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"示例知识库入库失败：{e}")
    if count == 0:
        raise HTTPException(status_code=500, detail="示例知识库解析异常：切出 0 条")
    return {"ingested": count, "source": sample_path.name}


@router.post("/search")
def search_qa(req: SearchRequest):
    # query 非空与 top_k 范围已由 Pydantic field_validator 统一校验（空串会被 422 拦截）。
    # 这里只负责业务：检索并返回结果。
    results = search(req.query, top_k=req.top_k)
    return {"query": req.query, "results": results}


@router.post("/ask")
def ask_qa(req: AskRequest):
    """RAG 问答与企业知识抽取。

    - answer：回答问题
    - summary：提炼结论和关键事实
    - action_items：输出行动项与负责人建议
    - risk_check：检测合规 / 交付 / 运营风险
    """
    return rag_ask(req.query, top_k=req.top_k, mode=req.mode)


# ─────────────────────────── 题库管理接口（段 A 修 #2）───────────────────────────


@router.delete("/documents/by-source/{source:path}")
def delete_by_source(source: str):
    """按 source 删除该文档的所有片段。

    业务背景：之前只让加不让删，题库管理形同虚设。
    - 用 Chroma 的 where={"source": source} 一次性定位该文档的所有 id
    - 拿不到任何 id 时返回 404（前端能区分"库里有/没有这个文件"）
    - 路径用 {source:path}，允许 source 含中文/点号/空格
    """
    try:
        col = get_collection(COLLECTION_NAME)
        existing = col.get(where={"source": source}, include=["metadatas"])
        ids = existing.get("ids", [])
        if not ids:
            raise HTTPException(status_code=404, detail=f"未找到来源为「{source}」的文档")
        col.delete(ids=ids)
        return {"deleted_chunks": len(ids), "source": source}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败：{e}")


@router.post("/documents/clear")
def clear_library(payload: dict[str, Any] = Body(default_factory=dict)):
    """清空整个题库。需要 confirm=true 字段二次确认。

    业务背景：「删除」太危险，防止误操作，所以要求调用方显式传 confirm=true
    才执行。生产里通常还会要求「输入题库名」之类的人工确认，这里为简洁省略。
    """
    if not payload.get("confirm"):
        raise HTTPException(
            status_code=400,
            detail="需要 confirm=true 字段才能执行清空操作（防止误删）",
        )
    try:
        col = get_collection(COLLECTION_NAME)
        existing = col.get(include=[])
        ids = existing.get("ids", [])
        if ids:
            col.delete(ids=ids)
        return {"deleted_chunks": len(ids), "remaining": 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清空失败：{e}")


@router.get("/documents/by-subject")
def list_by_subject(difficulty: str | None = None, q_type: str | None = None):
    """按学科（subject）分组列出所有题目，用于「专题刷题」面板。

    返回结构：
    {
      "subjects": [
        {"name": "Java", "count": 12, "questions": [{"q_index": "Q1", "title": "...", "preview": "...", "question_only": "...", "difficulty": "基础", "q_type": "qa"}]},
        ...
      ],
      "total": 50
    }
    学科按题数倒序；preview 取题目正文前 80 字，避免响应体过大。

    可选筛选：
      difficulty=基础/进阶/困难  → 仅按难度过滤
      q_type=qa/multi_choice/judge/code_output → 按题型过滤
    """
    try:
        col = get_collection(COLLECTION_NAME)
        total = col.count()
        if total == 0:
            return {"subjects": [], "total": 0}
        # Chroma where 过滤：同时支持 difficulty 与 q_type
        where: dict = {}
        if difficulty and difficulty in {"基础", "进阶", "困难"}:
            where["difficulty"] = difficulty
        if q_type and q_type in {"qa", "multi_choice", "judge", "code_output"}:
            where["q_type"] = q_type
        # 一次拿全 metadata + document，省得 N+1
        res = col.get(
            where=where or None,
            include=["metadatas", "documents"],
        )
        groups: dict[str, list[dict]] = {}
        for doc, meta in zip(res["documents"], res["metadatas"]):
            meta = meta or {}
            subject = meta.get("subject") or "未分类"
            content = doc or ""
            groups.setdefault(subject, []).append(
                {
                    "q_index": meta.get("q_index"),
                    "title": meta.get("title", ""),
                    "preview": content[:80] + ("…" if len(content) > 80 else ""),
                    "question_only": meta.get("question_only", ""),
                    "difficulty": meta.get("difficulty", "基础"),
                    "q_type": meta.get("q_type", "qa"),
                }
            )
        # 按题数倒序：重点学科置顶
        subjects = [
            {"name": k, "count": len(v), "questions": v}
            for k, v in sorted(groups.items(), key=lambda x: -len(x[1]))
        ]
        return {"subjects": subjects, "total": total}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"按学科分组失败：{e}")


@router.get("/documents/random")
def random_questions(subject: str | None = None, n: int = 5, include_generic: bool = False):
    """随机抽 N 道题，用于「模拟面试」。

    参数：
      subject        ：可选，按学科过滤（None = 全题库，但默认排除通用文档）
      n              ：1~20（默认 5）
      include_generic：默认 False —— 通用文档不进模拟面试
                       （通用文档只是复习资料，不是「面试题」，避免出现
                       「一段 Word 正文当一题」的体验问题。设 True 可强制包含）

    业务降级：如果过滤后题数 < n 且 include_generic=False，自动 fallback 到
              「含通用文档的全量库」再抽，避免「库里明明有题却抽不到」的尴尬。
    """
    if n < 1 or n > 20:
        raise HTTPException(status_code=400, detail="n 需在 1~20 之间")
    try:
        col = get_collection(COLLECTION_NAME)
        total = col.count()
        if total == 0:
            return {"questions": [], "total": 0}

        def _pick(where: dict | None) -> list[dict]:
            res = col.get(where=where, include=["metadatas", "documents"])
            items = []
            for doc, meta in zip(res.get("documents") or [], res.get("metadatas") or []):
                meta = meta or {}
                content = doc or ""
                items.append(
                    {
                        "subject": meta.get("subject", "未分类"),
                        "q_index": meta.get("q_index"),
                        "title": meta.get("title", ""),
                        "question_only": meta.get("question_only", ""),
                        "difficulty": meta.get("difficulty", "基础"),
                        "q_type": meta.get("q_type", "qa"),
                        "content": content,
                        "source": meta.get("source", ""),
                    }
                )
            return items

        # 第一优先：尊重 subject + 过滤通用文档
        if subject:
            items = _pick({"subject": subject})
        else:
            items = _pick({"subject": {"$ne": "通用文档"}} if not include_generic else None)

        # 降级：过滤后为 0 时，回退到全量（保底）
        if not items and not include_generic and not subject:
            items = _pick(None)

        if not items:
            return {"questions": [], "total": total}

        import random as _r
        picked = _r.sample(items, min(n, len(items)))
        return {"questions": picked, "total": total}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"随机抽题失败：{e}")
