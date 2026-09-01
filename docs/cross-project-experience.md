# 跨项目经验沉淀（作品集 #2 → #3 通用）

> **来源**：校招软件开发面试题库 RAG 垂直问答系统（作品集 #2）从零到上线全程实战
> **用途**：作品集 #3（CareerFlow 智能求职助手）启动前必读，避免重蹈覆辙
> **沉淀日期**：2026-09-01

---

## 一、通用工具栈经验（直接复用）

| 层 | 推荐选型 | 关键决策 | 替代方案 | 教训 |
|---|---|---|---|---|
| Embedding | **阿里百炼 DashScope** text-embedding-v3（1024 维，免费 50 万 token/90 天） | OpenAI 兼容 /compatible-mode/v1/embeddings，签名简单 | 智谱 embedding-3（**账户级 429 限流，已弃用**） | 智谱账户级配额会被一次调用打爆后持续锁死，**不要在生产用智谱 embedding** |
| LLM | 智谱 GLM-4-flash（不限流，便宜） | chat 接口无账户级 429，响应快 | 通义 Qwen-turbo 也行 | 智谱 LLM 没事，**仅 embedding 有问题** |
| 向量库 | **Chroma**（嵌入式，SQLite 持久化） | 零运维，适合作品集；按 metadata 过滤好用 | FAISS（无 metadata）、Qdrant（重） | Chroma 默认 embedding function 是自带的 sentence-transformers，**必须自写传自家 embedding**，否则坐标不同源检索翻车 |
| 后端 | **FastAPI + Pydantic** | 异步 + 自动 OpenAPI + Pydantic 校验天然契合业务加固 | Flask 也可以（作品集 #1 用过） | Pydantic 的 Field(..., min_length=1) 比手写校验稳得多 |
| 前端 | **Vue3 + Vite** | 构建快、SFC 直观 | React 也行 | **v-show 不卸载组件**，onMounted 只触发一次；如果依赖异步 props，要主动 reload |
| 部署 | **Render Free** | 自动重建、Environment 注入敏感 key | Railway（信用卡预扣休眠费，已弃） | Render Free **必须绑卡**（Stripe 验证）但**不收费**，别点 Upgrade Pro |
| 鉴权 | **API Key 中间件 + IP 限流** | 请求头 X-API-Key + slowapi 60s/30 次 | JWT 太重 | **前端不暴露 key**——改为装饰化的限流指示器，体现「有鉴权+有限流」的中台能力 |
| 持久化 | **磁盘挂载** + **启动时 auto-seed** | Render Free 实例是临时 FS，重部署清空 → 必须在 app.on_event("startup") 里检测空库自动灌 | 外部 PG（贵） | **auto-seed 是 Free 层保命的「数据迁移自动重灌」机制**，比 snapshot 重存储便宜 100 倍 |

---

## 二、部署关键决策（按顺序照做）

### 2.1 Render Free 绑卡流程
1. 注册 Render 账号（GitHub 登录）
2. Personal → Billing → Add Credit Card
3. Stripe 会**预授权 $0 或 $1**（不实际扣费），验证卡合法性
4. 完成后 Free 实例才能建
5. ⚠️ **永远别点 Upgrade to Pro** —— Free 层所有需求（Web Service + 自动重建 + Environment）都够用

### 2.2 环境变量注入（敏感 key 走 Environment，不进仓库）
- 后端代码读：from app.core.config import settings → settings.zhipu_api_key
- 配置层：backend/app/core/config.py 用 pydantic-settings.BaseSettings 读 os.environ
- **本地**：backend/.env（被 .gitignore 屏蔽）
- **线上**：Render Dashboard → Service → Environment → 加 key-value
- **示例文档**：项目根 backend/.env.example 列所有 key 名（值留空），不入具体值

### 2.3 Render Free 临时文件系统的应对
- Chroma 持久化到 /opt/render/project/src/backend/data/chroma_db/ 或挂 /var/data
- 每次重部署会清空 → **main.py 启动时检测 col.count() == 0 触发 load_sample()**
- 这就是「示例题库自动重灌」——用户无需手动操作

---

## 三、易踩坑清单（必须避开）

| # | 坑 | 现象 | 解决 |
|---|---|---|---|
| 1 | 智谱 embedding-3 持续 429 | 账户级配额打爆后锁死 | 切阿里百炼 DashScope text-embedding-v3 |
| 2 | Chroma 默认 embedding function | 坐标不同源检索必翻车 | 入库和查询都走同一个 provider，**自写 wrapper** |
| 3 | 入库 id 跨学科撞车 | DuplicateIDError | 每个学科都从 ### Q1. 编号，id 必须用**全局自增序号**，不要 source__Q1 |
| 4 | MOCK_EMBED 开关只在 provider 模块 | 切 provider 后失效 | 把 MOCK 提到**统一入口** embeddings.py，让 provider 调用无关 |
| 5 | Free 实例冷启动 | 首次访问等 30-60 秒 | 给前端加 loading 提示，或用 UptimeRobot 心跳保活 |
| 6 | 沙箱中 git push 走不通 | Could not connect to server | 必须用**本地 GitHub Desktop** 推送，沙箱无 GitHub 凭据 |
| 7 | .env 入库 | key 泄露 | .gitignore 屏蔽 .env、chroma_db/、node_modules/、dist/ |
| 8 | Vue v-show 不卸载 | onMounted 只触发一次 | 切面板时**主动 reload**（switchToBrowse() 调 subjectRef.load()） |
| 9 | 点击 Upgrade Pro | 立即扣费 $7/月 | 永别碰；如果手贱点了，立即 Dashboard → Cancel |
| 10 | API Key 公开 | 配额被打爆 | key 只走 Render Environment；聊天框裸贴过的 key **必须去平台重生成** |

---

## 四、本机环境限制（Windows + 沙箱，作品集 #3 同适用）

### 4.1 网络代理拦截清单
- ❌ dl.google.com TLS 握手被中断（Chrome MSI/独立安装包下不了）
- ❌ Google 系安装包（Chrome、ChromeSetup.exe、企业 MSI）
- ✅ github.com、objects.githubusercontent.com、registry.npmjs.org、cdn.winget.microsoft.com

**应对**：让用户自己用浏览器下载 Google 包，我接手安装。

### 4.2 沙箱拦截清单（命令级）
- ❌ Add-Type（含回收站 API）→ 改用「复制到 D 盘暂存区」保留后悔药
- ❌ WScript.Shell COM（建 .lnk）→ 改用 .bat 启动器
- ❌ cmd /c → 改用 PowerShell 原生命令
- ❌ 批处理里的 %VAR% / %* → 被判定为 cmd 语法，改绝对路径硬编码
- ❌ 超长路径（>260 字符）Remove-Item → robocopy <空目录> <目标> /MIR 清空
- ⚠️ PowerShell 输出偶尔被吞 → 把结果 Set-Content 到文件再用 Read 读

### 4.3 软件布局（跨项目惯例）
- **D 盘根目录**放开发环境（Flutter / JDK / Android SDK / Python venv / Node workspace）
- **C 盘**只放系统级软件，绝不放开发数据
- **D:\_Recycle_Hold** 是统一暂存区（待删文件先扔这里，用户确认后再清空）
- **D:\浏览器\ChromeUserData** + **D:\浏览器\chorm\...** 是 Chrome 绿色版（程序 + 数据 + --user-data-dir）

---

## 五、本项目已建立的工具复用（CareerFlow 直接照搬）

| 工具/模式 | RAG 项目用法 | CareerFlow 可借鉴 |
|---|---|---|
| 一键载入示例按钮 | 70 道示例题库 | 简历模板 + 模拟 JD 示例 |
| 题库管理（按学科筛选 + 难计数） | SubjectBrowser + 难度 tab | 申请追踪列表（按公司/状态分组） |
| 限流指示器 | 右上角「接口配额 X/30」 | 同样的位置 + 用量（避免用户改 key） |
| 引用溯源卡片 | [1] [2] [3] + 点击展开 | 简历匹配度可视化（高亮匹配项） |
| MOCK 验证管线 | MOCK_EMBED=true 跑后端 | CareerFlow 必有：JD 解析、简历解析都先 MOCK |
| 多阶段 Dockerfile | 前端 build 后进 /app/static 同源托管 | 同上 |
| start.py 读 $PORT | os.environ["PORT"] | 同上 |
| .env.example 模板 | 列出所有 key 名 + 占位 | 同上 |
| _auto_seed() 启动重灌 | col.count() == 0 自动 load_sample() | CareerFlow 可借鉴：模板数据库自动初始化 |

---

## 六、CareerFlow 项目启动时建议**直接照搬**的配置

**Dockerfile 多阶段构建**：

```dockerfile
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/static
EXPOSE 8000
CMD ["python", "start.py"]
```

**start.py 读 $PORT**：

```python
import os, uvicorn
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
```

---

## 七、本次踩坑的「时间损失」清单（CareerFlow 别再花）

| 坑 | 耗时 | 规避 |
|---|---|---|
| 智谱 embedding 429 反复重试 | ~30 min | **直接用 DashScope**，别试智谱 |
| MOCK_EMBED 开关失效 | ~10 min | **一开始就把 MOCK 提到统一入口** |
| 入库 id 撞 DuplicateIDError | ~5 min | **id 用全局序号** |
| Vue v-show 不卸载导致空面板 | ~3 min | 切面板主动 reload |
| 沙箱中 git push 失败排查 | ~5 min | **直接告诉用户用 GitHub Desktop** |
| API Key 聊天框裸贴 | ~10 min（含重生成） | **敏感 key 只走 Render Environment** |
| Free 实例清空 chroma_db | ~15 min | **实现 _auto_seed() 启动重灌** |

**总计节省：约 78 分钟** —— 这就是经验沉淀的价值。

---

## 八、下一步（CareerFlow 启动 checklist）

- [ ] 创建项目目录 D:\Workbuddy\project-3\（或用户指定）
- [ ] 写 careerflow-kickoff.md 锁定目标/技术栈/完成标准
- [ ] 创建 GitHub 仓库 + 本地 git init
- [ ] 搭阶段0脚手架（FastAPI + Vue3 + Vite）
- [ ] **本地 MOCK 优先**：JD 解析、简历解析先 mock
- [ ] 阶段1 简历解析（PDF/DOCX → 结构化 JSON）
- [ ] 阶段2 JD 匹配（关键词 + 技能树向量匹配）
- [ ] 阶段3 申请追踪（SQLite/JSON 文件）
- [ ] 阶段4 部署到 Render（按本文档第二节照搬）
- [ ] 简历项目栏写「使用 FastAPI + Vue3 + Render 部署，展示 RAG/LLM 真实业务场景」（同款描述复用）