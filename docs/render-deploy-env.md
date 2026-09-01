# Render 部署：配置 DashScope 环境变量

> ⚠️ **安全提醒**：本文档早期版本曾把真实 `DASHSCOPE_API_KEY` 明文写进过历史提交。
> 该 key 已被视为**可能已泄露**，必须去阿里云百炼控制台「重新生成」一个新 key，
> 并同步更新 Render 的 Environment 变量与本地 `backend/.env`。本文件现仅保留占位符。
>
> 适用场景：本仓库已切换 embedding provider 到阿里百炼 DashScope（commit `f7437ee`）。
> 代码里 `EMBEDDING_PROVIDER` 默认值是 `zhipu`，**不在 Render 上加下面两个变量就会继续走智谱 → 持续 429**。
> 本步骤必须在「GitHub Desktop 推送 3 个 commit」之后做。

---

## 一、为什么必须加

智谱免费档 embedding 接口是**账户级持续 429**（不是临时窗口限流），本地单条探针 + 线上截图双重确认。
切换方案：向量化改用阿里百炼 `text-embedding-v3`（1024 维，免费 50 万 token / 90 天）；
文本生成（问答）仍用智谱 GLM-4（chat 接口不限流）。

代码通过环境变量 `EMBEDDING_PROVIDER` 切换 provider，默认 `zhipu`。
**不显式改成 `dashscope` 就会继续用智谱 → 429**。

---

## 二、在哪里加（Render 控制台）

1. 打开 https://dashboard.render.com/
2. 点进你的 Web Service（`campus-interview-rag`）
3. 左侧菜单点 **Environment**（环境变量页）
4. 页面中部「Environment Variables」区域 → 点 **Add Environment Variable**（或已有变量区域的 + 按钮）
5. 逐条添加下面两个变量（KEY / VALUE 两栏）

---

## 三、要加的变量（复制即可）

| KEY | VALUE | 说明 |
|---|---|---|
| `EMBEDDING_PROVIDER` | `dashscope` | 切换 embedding provider（**核心，不加就 429**） |
| `DASHSCOPE_API_KEY` | `<你的阿里百炼 API Key，从 dashscope.console.aliyun.com 获取>` | 阿里百炼 API Key（**勿把真实 key 提交进仓库**） |

> **保留不动的变量**：`ZHIPU_API_KEY`（GLM 问答生成还在用）、`API_KEYS`、`RATE_LIMIT_PER_MINUTE`、`CHROMA_PERSIST_DIR`、`TOP_K` 等原有变量不要删。

---

## 四、加完之后

- 点 **Save Changes** → Render 会自动触发一次重建（约 4-6 分钟，因为多了 4 个解析依赖）。
- 重建完成后服务启动，`main.py` 的 `_auto_seed()` 会发现 chroma_db 为空 →
  **自动用 DashScope 灌入 70 道样例题**，无需手动点「一键载入示例题库」。
- 如果之前旧库残留（极少情况），可手动点一次「一键载入示例题库」补全，或直接上传文档。

---

## 五、验证（重建后做）

| 检查项 | 预期 | 失败现象 / 原因 |
|---|---|---|
| 访问根 URL | 看到中文 UI，顶部有「问答 / 专题刷题 / 模拟面试」三 tab | 还是 Swagger / 旧 UI → 推送没成功或没重建完 |
| 右上角限流指示器 | 显示「今日已请求 0/30」之类 | 仍显示 API Key 输入框 → 还是旧前端 |
| 点「一键载入示例题库」 | 返回"已索引 70 段"（**不再 429**） | 仍 429 → `EMBEDDING_PROVIDER` 没设成 `dashscope` |
| 提问"进程和线程区别" | 答案带 [1][2][3] 引用 | 无引用 → seed 没跑 / 向量空 |
| 上传一份 Word | 入库成功 | 429 → DashScope key 无效或没配置 |

---

## 六、安全提醒（重要）

该 `DASHSCOPE_API_KEY` 曾在聊天框里裸贴过一次。部署跑通后，**去阿里云控制台「重新生成」一个新 key**，
把本表 `DASHSCOPE_API_KEY` 的 VALUE 也换成新的，再 Save 触发一次重建。旧 key 即便泄露也立即失效。
