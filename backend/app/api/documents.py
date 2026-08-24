"""文档与检索相关接口（阶段1~2）。

这里直接用 Pydantic 模型定义请求体，FastAPI 会自动做「请求校验」——
字段缺失 / 类型错误会被 field_validator 拦截并返回 422，省去我们手写一堆 if。
这正好呼应你完成标准里的「真实性业务：输入校验」。
"""
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, field_validator

from app.services import ingestion
from app.services.rag import ask as rag_ask
from app.services.vector_store import search

router = APIRouter()


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


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    # 生产环境你还会做：大小限制、落盘到隔离目录、病毒扫描、异步任务队列
    if not file.filename.endswith((".md", ".txt")):
        raise HTTPException(status_code=400, detail="仅支持 .md / .txt 面试题文档")
    content = (await file.read()).decode("utf-8")
    count = ingestion.ingest_text(content, source=file.filename)
    return {"ingested": count, "source": file.filename}


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
