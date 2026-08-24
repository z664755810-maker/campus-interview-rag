"""阶段4 业务加固：鉴权 + 限流中间件。

两个中间件都是 Starlette 的 BaseHTTPMiddleware，挂在 FastAPI 应用上。
核心掌握点：
- 中间件是「洋葱模型」：请求从外到内穿过各层，响应从内到外返回。
- add_middleware 后注册的中间件处于最外层、最先处理请求。
- 所以我们让 APIKeyMiddleware 后注册（最外层，先鉴权），
  RateLimitMiddleware 先注册（内层，仅对通过鉴权的请求计数限流）。

注意：探活 /health 与文档 /docs、/openapi.json、/redoc 都「放行」，
避免开发期把自己挡在门外、也避免文档页加载被限流。
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

# 不鉴权、不限流的公开路径（探活与 API 文档）
PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/api/hello"}


def _extract_bearer(request: Request) -> str | None:
    """从 Authorization: Bearer <key> 头里取出 key（兼容标准鉴权写法）。"""
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


class APIKeyMiddleware(BaseHTTPMiddleware):
    """API Key 鉴权：请求头需带 X-API-Key 或 Authorization: Bearer <key>。

    - 公开路径直接放行；
    - 未配置 key（开发模式）时退化为不鉴权；
    - 否则 key 不在白名单 → 401。
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # 开发便利：没配任何 key 就不强制鉴权（生产务必配置 API_KEYS）
        if not settings.api_keys:
            return await call_next(request)

        provided = request.headers.get("X-API-Key") or _extract_bearer(request)
        if provided not in settings.api_keys:
            return JSONResponse(
                status_code=401,
                content={"detail": "未授权：缺少或提供了无效的 API Key"},
            )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """按客户端 IP 的固定窗口限流。

    每个 IP 维护一个「时间戳列表」，每次请求清理 60s 之前的记录；
    若窗口内请求数 >= 阈值，返回 429 + Retry-After。
    这是内存实现，足够单机/演示；生产会用 Redis 做分布式限流。
    """

    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, list[float]] = {}

    @staticmethod
    def _client_ip(request: Request) -> str:
        # 经过反向代理时以 X-Forwarded-For 为准，否则取直连 IP
        fwd = request.headers.get("X-Forwarded-For")
        if fwd:
            return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        ip = self._client_ip(request)
        now = __import__("time").time()
        window = self._hits.setdefault(ip, [])

        # 丢弃 60 秒之前的记录（滑不动的固定窗口）
        while window and now - window[0] > 60:
            window.pop(0)

        if len(window) >= settings.rate_limit_per_minute:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": "60"},
                content={"detail": "请求过于频繁，请稍后再试（限流）"},
            )

        window.append(now)
        return await call_next(request)
