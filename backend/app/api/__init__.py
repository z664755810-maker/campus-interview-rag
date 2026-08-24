"""API 路由聚合。

阶段0 仅放一个 hello 探活接口，验证「请求 → 路由 → 响应」链路通畅。
阶段1 会在这里加入 /upload（文档入库），阶段2 加入 /ask（问答检索）。
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/hello")
def hello(name: str = "同学"):
    # 最小闭环：能收到查询参数、能返回 JSON，说明 FastAPI 路由是正常的。
    return {"message": f"你好，{name}！RAG 后端骨架已启动。"}
