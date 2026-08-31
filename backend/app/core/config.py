"""配置中心：从环境变量 / .env 读取配置。

生产环境里你会用配置中心或 Secrets 管理（如 Railway 的 Variables），
核心原则：密钥绝不写死在代码里，统一从这里读取。
阶段0 先用 python-dotenv 读取本地 .env，后续阶段直接复用本文件。
"""
import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # 智谱开放平台 API Key；阶段1/2 才会真正调用 embedding / 生成，阶段0 仅做存在性检查。
    # 兼容两种常见命名：ZHIPU_API_KEY（官方文档）与 ZHIPUAI_API_KEY（部分教程误写），
    # 避免因为环境变量名不一致导致 key 读不到、问答功能静默失效。
    zhipu_api_key: str = os.getenv("ZHIPU_API_KEY") or os.getenv("ZHIPUAI_API_KEY", "")

    # 智谱 LLM 模型名（阶段2 启用，开发期用 flash 控成本；可换 glm-4-plus 提质）
    glm_model: str = os.getenv("GLM_MODEL", "glm-4-flash")

    # ── Embedding provider 切换（智谱免费档 embedding 接口持续 429 限流时的备选）──
    # "zhipu"     : 用智谱 embedding-3（2048 维），需要 ZHIPU_API_KEY
    # "dashscope" : 用阿里百炼 text-embedding-v3（1024 维），需要 DASHSCOPE_API_KEY
    # ⚠️ 切换 provider 时务必清空 chroma_db 重灌：不同模型/维度的向量空间不可比，
    #    混用会让检索结果错乱（看起来能搜但实际命中错题）。
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "zhipu")

    # 阿里百炼 DashScope API Key（embedding 专用，与智谱 chat 的 key 分开）
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")

    # DashScope embedding 模型名（默认 text-embedding-v3，1024 维）
    dashscope_embedding_model: str = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3")

    # Chroma 向量库持久化目录（阶段1 启用，数据落本地磁盘）
    chroma_persist_dir: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")

    # 单次检索返回的片段数 top-k（阶段2 启用）
    top_k: int = int(os.getenv("TOP_K", "5"))

    # 检索相似度阈值（Chroma 余弦距离：0=完全相同，1=完全不同，2=完全相反）。
    # 0.5 是经验值：低于它说明「真的相关」，高于它基本是「高频词撞库」（如"三大"）。
    # 太高 → 把相关题也过滤掉；太低 → 噪声被塞进答案。
    # 作品集场景下可让用户按 RAG_MIN_SCORE 环境变量微调。
    min_score: float = float(os.getenv("RAG_MIN_SCORE", "0.5"))

    # ── 阶段4 业务加固：鉴权与限流 ───────────────────────────
    # 客户端 API Key（用于 API Key 中间件）。支持配置多个，逗号分隔。
    # 为空时中间件退化为「不鉴权」（仅开发便利，生产务必配置）。
    api_keys: list = [
        k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()
    ]

    # 限流：单个客户端 IP 每分钟最多允许的请求数（针对 /api 业务接口）。
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))


settings = Settings()
