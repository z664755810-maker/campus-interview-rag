"""Railway / PaaS 部署专用启动脚本。

为什么需要这个脚本（不直接用 Dockerfile 的 'CMD uvicorn ... --port $PORT'）：

1. Railway Docker 模式下，容器启动时 Railway 会在我们的 CMD 之前先尝试
   'cd' 到 WORKDIR。如果它的实现是直接 exec 'cd' 而不是通过 sh -c，
   就会报错：'The executable cd could not be found'，容器创建失败。
2. 即使用 'sh -c' 包裹，shell 展开环境变量在某些 PaaS 环境下也可能因为
   时序 / PATH / 入口点处理等原因出现奇怪问题。

最稳妥的工业级方案：**让 Python 直接读 os.getenv('PORT')**，
完全绕开 shell 展开这一步。这是 12-Factor App 推荐做法。

本地开发仍用 'uvicorn app.main:app --reload' 即可，本文件仅用于生产部署。
"""
import os

import uvicorn

# 直接 import 复用 main.py 里已构造好的 FastAPI 实例（含 lifespan / 路由 / 中间件）
from app.main import app


if __name__ == "__main__":
    # Railway 一定会注入 PORT 环境变量（默认 8080），本地兜底 8000
    port = int(os.getenv("PORT", "8000"))

    # log_level=info 让 Railway 能看到我们的启动 / 访问日志
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
