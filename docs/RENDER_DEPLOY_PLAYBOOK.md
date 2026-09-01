# Render 部署剧本（通用版，可复用于任何同构项目）

> 来源：校招面试题库 RAG 项目（project-2）已跑通的 Render Free 部署流程。
> 适用：任何「前端（Vue3/Vite）+ 后端（FastAPI/Python）+ 需要 LLM API」的同构项目，
>       例如 CareerFlow 智能求职助手。把里面的仓库名 / 服务名 / Key 换成目标项目的即可。
> 核心原则：**零改代码迁移**——部署相关逻辑全部用 Dockerfile / start.py / 环境变量承载。

---

## 一、整体架构（为什么这么部署）

```
GitHub 仓库 ──(push)──> Render 自动拉取 ──> Docker 多阶段构建
                                        ├─ 阶段1: node 构建前端 dist/
                                        └─ 阶段2: python 跑后端 + 把 dist 拷入 /app/static
                                                  │
                                  浏览器访问根路径 /  → 前端 UI（同源）
                                            /api/*  → 后端接口（同源，免 CORS）
```

- **同源托管**：前端 build 产物由后端 FastAPI 直接 `StaticFiles` 托管，根路径即 UI，`/api` 仍归后端。好处：免 CORS 配置、一次部署两个服务。
- **临时文件系统**：Render Free 容器重启会清空非挂载磁盘（含 `chroma_db/` 这类向量库），所以必须有「自动 seed」兜底。

---

## 二、必备文件（复制到目标项目根目录）

### 1. `Dockerfile`（多阶段）

```dockerfile
# 阶段1：构建前端
FROM node:20-slim AS frontend-build
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

# 阶段2：后端
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=frontend-build /fe/dist ./static
ENV PORT=8000
EXPOSE 8000
CMD ["python", "start.py"]
```

> 锁 `python:3.12`：chroma-hnswlib 没有 cp313 的 wheel，3.13 装不上 Chroma。
> 锁 `node:20`：vite 5 在 18+ 兼容，20 为 LTS。

### 2. `start.py`（读 $PORT 启动）

```python
import os
import uvicorn
from app.main import app   # 复用已构造好的 FastAPI 实例（含 lifespan/路由/中间件）

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
```

> 用 Python 直接读 `os.getenv('PORT')`，**绕开 shell 展开**与 Railway `cd` 包装器坑。

### 3. 后端 `main.py` 必须有的部署相关片段

- **CORS**：从环境变量 `ALLOWED_ORIGINS` 读取（默认 `*` 开发态），生产收敛到具体域名。
- **自动 seed（关键）**：`lifespan` 里用 `asyncio.create_task(asyncio.to_thread(_auto_seed))` 在后台线程灌库，
  **绝不阻塞 uvicorn 启动**（否则超过 PaaS healthcheck 窗口被判 unhealthy 重启，永远起不来）。
  seed 逻辑：检测向量库为空 → 从内置样例数据灌入；非空则跳过（不覆盖真实数据）。
- **静态托管**：`/_STATIC_DIR = .../static`，根路径 `/` 返回 `index.html`，并 `app.mount("/assets", StaticFiles(...))`。

### 4. `.dockerignore`（避免把本地大文件打进镜像）

```
backend/.venv
backend/chroma_db
backend/__pycache__
backend/.env
frontend/node_modules
frontend/dist
.git
```

---

## 三、Render 控制台操作步骤

1. 打开 https://dashboard.render.com/ → **New** → **Web Service** → 选 GitHub 仓库。
2. 配置：
   - **Runtime**：Docker（Detected via Dockerfile）
   - **Branch**：main / master
   - **Region**：离用户近的（如 Singapore）
   - **Plan**：Free（注意 Free 实例 15 分钟无流量会休眠，首次访问冷启动约 30-60s）
3. 左侧 **Environment** → 添加环境变量（见下一节）。
4. 点 **Create Web Service** → Render 自动构建并部署（首次约 4-8 分钟）。
5. 部署完成后访问分配的 `https://<service-name>.onrender.com`。

---

## 四、必须配置的环境变量

| KEY | VALUE | 说明 |
|---|---|---|
| `PORT` | （不用设，Render 自动注入） | start.py 读取 |
| `ZHIPU_API_KEY` | 智谱 Key | GLM 问答生成（如有用到） |
| `DASHSCOPE_API_KEY` | 阿里百炼 Key | embedding 向量化（若用 DashScope 兜底 429） |
| `EMBEDDING_PROVIDER` | `dashscope` 或 `zhipu` | 切 embedding provider，**不设默认 zhipu 可能 429** |
| `API_KEYS` | `dev-xxx-2026`（可选） | 客户端鉴权中间件 |
| `RATE_LIMIT_PER_MINUTE` | `30` | 单 IP 限流阈值 |
| `CHROMA_PERSIST_DIR` | `./chroma_db` | 向量库路径 |
| `TOP_K` | `5` | 检索返回片段数 |
| `ALLOWED_ORIGINS` | `*` 或前端域名 | CORS 收敛 |

> **安全红线**：真实 Key 只配在 Render 控制台 Environment，**绝不要写进仓库文件**（含 docs）。
> 本地 `.env` 必须 gitignore。一旦在聊天/提交里暴露过，去对应平台「重新生成」新 Key 让旧的失效。

---

## 五、自动 seed 应对临时文件系统（必须做）

Render Free 重启会清空 `chroma_db/`，导致「库空了、首页显示 0 题」。解决：

```python
def _auto_seed():
    col = get_collection()
    if col.count() > 0:
        return  # 已有数据，跳过
    # 从 backend/data/<样例文件>.md 解析并灌入
    ingest_text(read_sample(), source="sample.md")

@asynccontextmanager
async def lifespan(app):
    asyncio.create_task(asyncio.to_thread(_auto_seed))  # 后台线程，不阻塞启动
    yield
```

验证：部署后首次访问，应能看到自动灌入的样例数据（如本项目的 70 道样例题）。

---

## 六、本地验证 → 推送 → 上线 闭环

```bash
# 1. 本地构建前端，确认无误
cd frontend && npm install && npm run build

# 2. 本地起后端（Python 3.12 venv），确认接口通
cd ../backend && pip install -r requirements.txt
python scripts/reindex.py        # 灌样例
python -m uvicorn app.main:app --port 8000

# 3. 提交 + 推送（用 GitHub Desktop 或 git）
git add -A && git commit -m "feat: 部署相关文件就绪" && git push

# 4. Render 会自动检测 push 触发重建；重建完浏览器实测
```

---

## 七、10 个踩坑清单（部署前逐项核对）

1. **Python 版本**：必须 3.12，禁用 3.13（Chroma wheel 缺失）。
2. **chromadb 锁 1.5.9**：0.6.3 会强依赖需要 MSVC 编译的 hnswlib，Windows 装不上。
3. **start.py 读 $PORT**：别用 `uvicorn app.main:app --port $PORT` 的 shell 展开写法，某些 PaaS 会炸。
4. **自动 seed 必须后台线程**：阻塞启动 → 超 healthcheck → 无限重启。
5. **embedding provider 必须显式设**：默认 zhipu 在免费档会账户级 429，显式 `dashscope` 才稳。
6. **密钥不进仓库**：`.env` gitignore；docs 里也别写真实 Key；暴露过就轮换。
7. **CORS 生产收敛**：`ALLOWED_ORIGINS` 别一直 `*`，上线后填真实域名。
8. **Free 实例休眠**：冷启动慢，首次访问超时属正常，等 30-60s 再试。
9. **静态资源路径**：确保 `dist/` 被正确 COPY 到 `/app/static`，否则根路径只看到 Swagger。
10. **重建后实测**：别只看「build succeeded」，要浏览器真实走一遍「载入样例→提问→带引用」。

---

## 八、套用到 CareerFlow 的对照

| RAG 项目 | CareerFlow 对应 |
|---|---|
| 校招面试题库 RAG | CareerFlow 智能求职助手（简历/JD/面试/申请追踪） |
| 样例：70 道面试题 | 样例：内置简历解析结果 / 模拟面试题库 / JD 模板 |
| 智谱 GLM + DashScope embedding | 同构：根据 CareerFlow 实际用的 LLM 配对应 Key |
| `campus-interview-rag` 服务名 | 换成 CareerFlow 的 Render 服务名 |
| 同源托管 + 自动 seed | 直接复用，无需改架构 |

**一句话给 CareerFlow 对话**：「按 RAG 项目的 Render 部署流程来部署——Docker 多阶段同源托管前后端、start.py 读 $PORT、Environment 配 LLM Key 与 EMBEDDING_PROVIDER、用自动 seed 应对临时文件系统。流程细节见 `docs/RENDER_DEPLOY_PLAYBOOK.md`。」
