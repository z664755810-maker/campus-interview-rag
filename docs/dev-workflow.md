# 校招 RAG 项目开发流程速查表

> 讲师带你从本地改代码到 Render 上线验证的标准节奏。所有项目共用这套流程；
> 只有"环境变量名"按各自项目调整。

---

## 0. 一次配置（每台机器一次）

### 后端 Python venv
```bash
cd backend
python -m venv .venv       # 已存在可跳过
source .venv/Scripts/activate   # Git Bash
pip install -r requirements.txt
cp .env.example .env       # 没 .env 时
# 编辑 .env：填 LLM key（智谱/百炼）、embedding provider
```

### 前端 Node + Vite
```bash
cd frontend
npm install
```

### 凭据/账号
- GitHub Personal Access Token：本地 Git 推送用（Fine-grained 也行）
- Render：GitHub 登录 + 已绑卡（Vintage Free 层强制）
- LLM 服务：智谱 GLM / 阿里百炼 DashScope API Key
- **API Key 绝不入库** — 走 Render Environment，不进 `backend/.env` 提交

---

## 1. 一日开发的标准节奏（按顺序执行）

### ① 拉取最新代码
```bash
git pull --rebase
```
> PaaS 上别人 / 上次会话推过的代码，需要先拉本地再改。

### ② 写代码 / 改 prompt
记住两条习惯：
- **写一段就跑一下**，不要攒 10 段一起跑——中间出错你得回头翻 10 处
- **改 README/前端前先想清楚建模**：UI 字段缺失先回到数据库/接口补，别在前端现造假数据

### ③ 本地启服务（双终端）
**终端 A — 后端**：
```bash
cd backend && source .venv/Scripts/activate
# MOCK_EMBED=true 可以不开 LLM 也能跑端到端，特别适合改前端
MOCK_EMBED=true uvicorn app.main:app --reload --port 8000
```

**终端 B — 前端（如果要改 UI）**：
```bash
cd frontend && npm run dev   # 默认 http://localhost:5173
# Vite 把 /api/* 反代到 8000
```

> 没改前端只改后端时，前端不需要启；前端 vite build 产出的 dist/ 是 Render 同源部署用的。

### ④ 本地最小验证（3 件事）
```bash
# 健康
curl http://localhost:8000/health | jq

# 灌一份示例题库
curl -X POST http://localhost:8000/api/documents/load-sample | jq

# 问一道题验证 RAG 链路
curl -X POST http://localhost:8000/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"HashMap 原理"}' | jq
```
看见 answer + sources 字段非空 = 链路通了。

### ⑤ 真实链路验证（不上前端也能跑）
不用前端，curl 直接打接口：
- `/api/documents/upload` 上传一个真实 .docx，确认入库非 0
- `/api/documents/by-subject` 看返回结构里是否有新字段
- `/api/documents/random?n=5&include_generic=true` 强制含通用文档，验证降级逻辑

### ⑥ 提交 + 推送
```bash
git add -A
git commit -m "feat: 加题面/答案拆开入库"     # 讲师口径写
# ⚠️ 不要 --no-verify，除非钩子已经验证过

# 推荐走 GitHub Desktop push，原因：
#   - 历史会显示清
#   - commit 前钩子不会拦截（if any）
#   - 推送失败提示具体原因
```
**Render 检测到 main 分支更新 → 自动重建**，4-6 分钟（取决于 PaaS 排队）。

### ⑦ Render 控制台环境变量（如本次新增了 key/配置）
Dashboard → 服务 → Environment → Add Env Var → Save，会再次触发重建。

### ⑧ 在线验证（Render 重建完后）
1. 访问服务 URL，看新 UI 是否生效
2. 直接调接口验证逻辑：
```bash
curl https://your-app.onrender.com/api/documents/load-sample -X POST
curl https://your-app.onrender.com/api/documents/by-subject
```
> ⚠️ SPA 不能 `curl /` 拿 HTML 内容判断版本；Vue SPA 根 URL 永远返回空壳 `<div id="app">`，
> 必须看真有数据的接口或截图真页面。

---

## 2. 关键坑（每个都是踩过的）

| 坑 | 现象 | 排查 |
|---|---|---|
| 智谱 embedding 持续 429 | 入库 / 检索 502 | 账户级配额打爆，**切阿里 DashScope**（OpenAI 兼容，免费 50w token/90 天） |
| MOCK_EMBED NaN/Inf | Chroma 拒收向量 | 检查 `_mock_embed` 是否兜底 `isfinite()` |
| 入库只进 Q 排版文档 | 普通 Word 切出 0 段 | `parse_markdown` + `split_generic` 兜底 |
| Vue SPA curl 看不到内容 | 误以为部署没生效 | **`curl /` 看根 div 不是版本判断标准**，必须看接口或截图 |
| 启动时 Chroma 0 段 | demo 看着没数据 | `_auto_seed` 在 lifespan 后台线程自动灌库 |
| 前端调用跨域 | OPTIONS 失败 | 后端 CORS 已配 `ALLOWED_ORIGINS`；同源部署不触发 |
| 推送后 Render 没重建 | 路由/分支问题 | Render 已绑仓库 main 分支，看 Event Log |

---

## 3. 提问模板（卡住时如何截图贴图给我看）

把下面这段贴给我，省得来回追问：

```
【我的问题】
（如：模拟面试只剩 1 题时报错）

【期望 vs 实际】
- 期望：完成第 5 题后展示分数
- 实际：报错「cannot read property x of undefined」

【截图说明】
（标注红色框或贴 console 报错文本）

【已尝试】
- 刷新页面 → 同一报错
- 切到问答模式 → 正常

【环境】
- URL：https://campus-interview-rag.onrender.com
- 题库来源：一键载入示例
- 题目题型：<基础/进阶/困难>，<qa/multi_choice/judge/code_output>
```

---

## 4. 这个项目特有的约定（沿用 / 跨项目时改）

| 项 | 本项目 | 改成你时 |
|---|---|---|
| 服务端口 | uvicorn 8000 | 同 |
| 前端 dev 端口 | vite 5173 | 同 |
| PaaS | Render Free | Railway / 其他自换 |
| LLM chat | 智谱 GLM-4-Flash（不限流） | 智谱/百炼/OpenAI 自换 |
| embedding | 智谱 → 已切百炼 DashScope | 由 `.env EMBEDDING_PROVIDER` 切 |
| 向量库 | Chroma（本地持久化） | 同 |
| 题库示例路径 | `backend/data/sample_interview.md` | 自换文件名 |
| 主路由前缀 | `/api` | 同 |
| 鉴权 | APIKeyMiddleware（演示用） | 生产换 OAuth/JWT |
| 限流 | RateLimitMiddleware（IP+30 秒窗口） | 自调窗口 |

---

## 5. 思维模型（讲师总结）

- **数据建模为场景服务**：UI 改动 80% 的根因在 metadata 字段缺失，先回数据层补
- **一改一跑**：碎片化累积远胜一把梭
- **关键接口先 sanity**：所有 bug 都先 curl 验一遍再去看前端
- **API Key 永远不进仓库**：本地 .env + Render Environment 双轨
- **SPA 不能 curl 验**：UI 改动最终一定要看页面（截图/录屏）
- **降级路径比 happy path 更重要**：默认策略、用户原题为空、过滤后无结果——总是提供 fallback

> 这套流程在新项目里直接复用，只改第 4 节的环境变量值即可。
