"""文档与检索相关接口（阶段1~2）。

这里直接用 Pydantic 模型定义请求体，FastAPI 会自动做「请求校验」——
字段缺失 / 类型错误会被 field_validator 拦截并返回 422，省去我们手写一堆 if。
这正好呼应你完成标准里的「真实性业务：输入校验」。
"""
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, field_validator

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

    为什么需要：PaaS 免费层重启会丢数据，启动时的 seed 会自动灌 50 条示例题。
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
    """一键载入内置示例题库。

    为什么要有这个接口：很多同学（包括第一次用的人）手边根本没有现成的 .md/.docx
    题库文件，对着空空的上传框无从下手。点一下就能灌入 50 道示例题，
    立刻可以体验「提问 -> 带出处回答」的完整链路。
    幂等：重复调用会 upsert 覆盖，不会灌出重复数据。
    """
    sample_path = Path(__file__).resolve().parent.parent.parent / "data" / "sample_interview.md"
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="服务端未找到内置示例题库文件")
    try:
        text = sample_path.read_text(encoding="utf-8")
        count = ingestion.ingest_text(text, source="sample_interview.md")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"示例题库入库失败：{e}")
    if count == 0:
        raise HTTPException(status_code=500, detail="示例题库解析异常：切出 0 条")
    return {"ingested": count, "source": "sample_interview.md"}


@router.post("/search")
def search_qa(req: SearchRequest):
    # query 非空与 top_k 范围已由 Pydantic field_validator 统一校验（空串会被 422 拦截）。
    # 这里只负责业务：检索并返回结果。
    results = search(req.query, top_k=req.top_k)
    return {"query": req.query, "results": results}


@router.post("/ask")
def ask_qa(req: AskRequest):
    # 阶段2 核心：RAG 问答。rag_ask 内部完成「检索 -> 拼 Prompt -> GLM 生成 -> 引用溯源」。
    return rag_ask(req.query, top_k=req.top_k)
