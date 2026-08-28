# 多格式文档上传改造说明

> commit `fda768c` · 2026-08-28

## 一、为什么要改

用户反馈：「文件类型太少了，连 Word 文档都放不进来，而且没有示例文件」。

排查后发现是**两层问题**，只解决第一层会做成"假支持"：

| 层 | 问题 | 只改这层的后果 |
|---|---|---|
| 接口层 | `documents.py` 硬编码只认 `.md` / `.txt` | 放开扩展名后 Word 能传 |
| 解析层 | `parse_markdown` 只认 `### Q1.` 结构 | **Word 传进来切不出题，入库 0 条，提问永远答不上来** |

第二层是关键。所以这次改造同时动了「白名单」和「切分策略」。

## 二、改了什么

### 后端

**新增 `backend/app/services/parsers.py`** —— 解析层，支持 13 种格式：

`.md` `.markdown` `.txt` `.text` `.log` `.docx` `.pdf` `.pptx` `.xlsx` `.csv` `.json` `.html` `.htm`

三个设计点：
- **按需 lazy import**：docx/pdf/pptx 等第三方库在用到时才导入，缺一个可选依赖不会拖垮整个服务
- **编码兜底** `utf-8 → utf-8-sig → gbk → gb18030 → big5 → latin-1`
  （中文 Windows 记事本默认存 GBK，直接 `decode("utf-8")` 必抛异常——新手项目最常见的线上 500 之一）
- **Word 标题样式还原**：Heading 1/2/3 → `#`/`##`/`###`，让结构化题库 Word 直接命中按题切分

拒绝老格式时给**可执行的转换建议**，而不是干巴巴一句"不支持"：
```
.doc  → 老版 Word(.doc) 是二进制格式，请用 Word/WPS 打开后「另存为 .docx」再上传
.png  → 图片需先做 OCR 转成文字；本项目暂不支持直接识图
```

**`ingestion.py` 新增 `split_generic`** —— 通用切分兜底：
无 `### Q` 结构的文档按段落累积到 500 字切片，保留 80 字 overlap（避免一句话被腰斩在两片里），
超长段落按中文句号硬切。**这是 Word/PDF 能否真正可用的关键。**

**`documents.py`** —— 上传加固 + 三个新端点：

| 端点 | 作用 |
|---|---|
| `POST /api/documents/upload` | 加固：10MB 上限(413) / 类型白名单(415) / 解析失败(400) / 向量异常(502) |
| `GET /api/documents/formats` | 格式白名单下发给前端，前后端共用一份，避免两处维护不一致 |
| `GET /api/documents/stats` | 真实题库状态。修复「seed 灌了 50 条但前端显示 0 段」 |
| `POST /api/documents/load-sample` | 手边没文件时一键体验，upsert 幂等 |

**依赖**（刻意选轻量，免费层构建时间敏感）：
`python-docx 1.1.2` / `pypdf 5.1.0` / `python-pptx 1.0.2` / `openpyxl 3.1.5`
避开了 `unstructured`（重型）、`pdfplumber`（重）。

### 前端

- `UploadPanel.vue` 重写：**「一键载入示例题库」设为绿色主入口**，格式标签可视化，不支持格式给转换建议
- `App.vue`：`onMounted` 同步真实题库状态；`onUploaded` 按 source 去重
  （后端 upsert 幂等，前端无脑累加会让计数虚高）
- 新增示例文件下载入口（Word / Markdown 两份）

### 新增脚本

- `backend/scripts/gen_sample_docx.py` —— md 题库转 Word 样例
- `backend/scripts/test_parsers.py` —— 解析层自测，不依赖网络与智谱 API

## 三、验证结果

```
scripts/test_parsers.py  →  17/17 通过
真实 Word 端到端         →  解析 6504 字 → 切出 50 道题 → 可被检索命中
上传 API                 →  docx ingested=50；.doc 被 415 拦截
load-sample 幂等         →  连调两次 count 仍 100，不膨胀
前端构建                 →  npm run build 通过（JS 73.46 kB）
```

## 四、沉淀的经验

1. **放开文件格式 ≠ 功能可用** —— 必须验证「传进去 → 切得出 → 检索得到」完整链路，
   只改扩展名白名单是自欺欺人
2. **前端要同步真实后端状态** —— PaaS 免费层数据易失，前端写死 0 会误导用户
3. **编码兜底是中文项目的必修课** —— 任何 `decode("utf-8")` 都要有 GBK 回退
