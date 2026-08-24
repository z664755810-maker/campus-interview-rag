"""FastAPI 应用入口。

阶段0 目标：跑通一个最小可运行服务，验证后端骨架与目录结构正确。
后续阶段会在这里挂上 /upload（入库）与 /ask（问答）两条核心管线。
部署改造：lifespan 启动 hook + CORS 环境变量，让后端可零改造上 PaaS。
"""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.api.documents import router as documents_router
from app.core.config import settings
from app.core.security import APIKeyMiddleware, RateLimitMiddleware


def _auto_seed() -> None:
    """启动时检查 Chroma；若为空，从内置 sample_interview.md 灌一份基础题库。

    为什么需要这个：PaaS（Railway / Render）容器是临时文件系统，
    重启 chroma_db/ 会被清空。这个 hook 让演示环境开箱即用，
    已经被 ingest 过的真实数据不会被覆盖。
    """
    try:
        from app.services.vector_store import get_client, COLLECTION_NAME

        client = get_client()
        try:
            col = client.get_collection(name=COLLECTION_NAME)
            if col.count() > 0:
                print(f"[seed] Chroma 已有 {col.count()} 条数据，跳过自动入库")
                return
        except Exception:
            # collection 不存在时 get_collection 会抛异常，属正常情况
            pass

        from app.services import ingestion

        sample_path = Path(__file__).resolve().parent.parent / "data" / "sample_interview.md"
        if not sample_path.exists():
            print("[seed] 未找到样例题库文件，请通过 /api/documents/upload 上传")
            return
        text = sample_path.read_text(encoding="utf-8")
        n = ingestion.ingest_text(text, source="sample_interview.md")
        print(f"[seed] 已自动从样例题库灌入 {n} 条（来源 sample_interview.md）")
    except Exception as e:
        # seed 失败不能影响服务启动
        print(f"[seed] 自动入库失败（不影响启动）：{e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 关键：seed 放到后台线程异步执行，绝不能阻塞 uvicorn 启动。
    # 原因：lifespan 阶段是同步阻塞的，seed 完成前 uvicorn 不会 listen 端口；
    # 一旦 seed 耗时超过 PaaS healthcheck 窗口（Railway 默认 30s），
    # 容器会被判 unhealthy 而重启，造成"永远起不来"。
    # 用 asyncio.to_thread 把同步的 _auto_seed 跑到独立线程，
    # uvicorn 立刻 yield → 端口开始 listen → /health 立即可访问。
    asyncio.create_task(asyncio.to_thread(_auto_seed))
    yield


app = FastAPI(
    title="校招面试题库 RAG 系统",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS：开发期默认放开；生产通过环境变量 ALLOWED_ORIGINS 收敛到具体前端域名。
# 例：ALLOWED_ORIGINS=https://campus-interview-rag.vercel.app,https://yourdomain.com
_allowed = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed or ["*"],
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
    return {
        "status": "ok",
        "api_key_set": bool(settings.zhipu_api_key),
    }
