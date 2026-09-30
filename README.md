# 企业知识库智能助手 · RAG 知识管理平台

面向企业内部知识查询、流程梳理、风险审查和运营协同的 **检索增强生成（RAG）** 平台。
上传政策文档 / SOP / FAQ / 会议纪要 → 自动切分向量化 → 混合检索召回相关片段 → 基于检索结果生成带引用溯源的答案。

---

## ✨ 功能特性

- **多格式文档入库**：支持 Word / PDF / PPT / Excel / CSV / JSON / HTML / Markdown / TXT 等格式，自动解析文本与表格内容，按文档结构切分后向量化入库
- **混合检索**：向量语义召回（百炼 text-embedding-v3）+ BM25 关键词召回（jieba 中文分词），RRF 倒数排名融合两路结果，解决纯向量对专有名词/编号匹配不准的问题
- **相似度阈值过滤**：召回后按余弦距离阈值过滤低相关片段，减少高频词撞库带来的噪声
- **RAG 问答**：检索片段 + 受约束 Prompt 交由大模型生成答案，Prompt 限制"仅基于给定资料回答"以抑制幻觉
- **四种业务模式**：问答 / 摘要提炼 / 行动清单提取 / 风险审查，适配政策查询、流程梳理、任务落地、合规审查四类场景
- **引用溯源**：每条答案标注来源文档与对应片段，前端可展开查看原文
- **工程化**：API Key 鉴权、按 IP 限流、Pydantic 请求校验、查询缓存（重复问题 10 分钟内复用结果）

## 🧱 技术栈

| 层 | 选型 |
|---|---|
| 后端 | FastAPI + Uvicorn |
| 向量库 | Chroma（持久化，向量+原文+元数据一体存储） |
| Embedding | 阿里百炼 text-embedding-v3（1024 维），可切换智谱 embedding-3 |
| 大模型 | 智谱 GLM-4 |
| 关键词检索 | rank_bm25 + jieba 中文分词 |
| 前端 | Vue 3 + Vite |
| 部署 | Docker 多阶段构建 + Render 云平台 |

## 🏗️ 系统架构

```
入库流：文档 → 格式解析 → 结构切分 → 向量化 → Chroma + BM25 索引
问答流：问题 → 向量化召回 + BM25召回 → RRF融合 → 阈值过滤 → 拼Prompt → 大模型生成 → 带引用答案
```

## 📁 项目结构

```
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI 入口
│   │   ├── api/documents.py      # 上传/检索/问答接口
│   │   ├── core/config.py        # 配置（环境变量）
│   │   ├── core/security.py      # API Key 鉴权 + 限流
│   │   └── services/
│   │       ├── embeddings.py      # 向量化
│   │       ├── vector_store.py   # Chroma 封装 + 混合检索 RRF 融合
│   │       ├── bm25_index.py     # BM25 关键词索引
│   │       ├── ingestion.py      # 文档解析切分入库
│   │       ├── parsers.py        # 多格式解析（docx/pdf/pptx/xlsx/...）
│   │       └── rag.py            # RAG 问答主流程
│   └── requirements.txt
└── frontend/                     # Vue3 前端
```

## ⚙️ 环境要求

- Python 3.12（chromadb 1.5.9 无 3.13 预编译 wheel）
- Node.js 18+（前端构建）
- 智谱 API Key（问答生成）
- 阿里百炼 API Key（向量化）

## 🚀 本地运行

```bash
# 后端
cd backend
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env   # 填入 API Key
python -m uvicorn app.main:app --port 8000

# 前端（另开终端）
cd frontend
npm install
npm run dev
```

## ☁️ 部署

Docker 多阶段构建：前端 build 后拷入后端静态目录同源托管。示例：

```bash
docker build -t campus-rag .
docker run -p 8000:8000 \
  -e ZHIPU_API_KEY=xxx \
  -e DASHSCOPE_API_KEY=xxx \
  -e EMBEDDING_PROVIDER=dashscope \
  campus-rag
```

## 🔌 主要接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 探活 |
| POST | `/api/documents/upload` | 上传文档入库 |
| POST | `/api/search` | 混合检索 top-k 片段 |
| POST | `/api/ask` | RAG 问答（返回答案+引用） |
| GET | `/api/documents/stats` | 知识库统计 |

---

非商用学习项目。所调用的大模型服务请遵守对应平台的服务条款。
