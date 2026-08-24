"""FastAPI 应用入口。

阶段0 目标：跑通一个最小可运行服务，验证后端骨架与目录结构正确。
后续阶段会在这里挂上 /upload（入库）与 /ask（问答）两条核心管线。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.api.documents import router as documents_router
from app.core.config import settings
from app.core.security import APIKeyMiddleware, RateLimitMiddleware

app = FastAPI(title="校招面试题库 RAG 系统", version="0.1.0")

# 开发期放开跨域，方便前端（5173）直接调用。
# 生产环境里你会把 allow_origins 收敛到前端域名白名单，避免被任意站点套用接口。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 业务加固（阶段4）：鉴权 + 限流中间件。
# 注册顺序：后注册的 APIKeyMiddleware 处于最外层、最先执行（先鉴权，
# 无效 key 直接 401，不消耗限流配额）；RateLimitMiddleware 在内层，
# 仅对通过鉴权的请求做计数限流。
app.add_middleware(RateLimitMiddleware)
app.add_middleware(APIKeyMiddleware)

# 业务接口统一挂在 /api 前缀下，便于后续做版本管理与鉴权中间件拦截。
app.include_router(api_router, prefix="/api")
app.include_router(documents_router, prefix="/api")


@app.get("/health")
def health():
    # 探活接口顺手暴露配置就绪状态，方便排查。
    # 注意：这里只回显「是否配置」，绝不回显密钥明文。
    return {"status": "ok", "api_key_set": bool(settings.zhipu_api_key)}
