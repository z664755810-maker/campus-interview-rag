"""配置中心：从环境变量 / .env 读取配置。

生产环境里你会用配置中心或 Secrets 管理（如 Railway 的 Variables），
核心原则：密钥绝不写死在代码里，统一从这里读取。
阶段0 先用 python-dotenv 读取本地 .env，后续阶段直接复用本文件。
"""
import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # 智谱开放平台 API Key；阶段1/2 才会真正调用 embedding / 生成，阶段0 仅做存在性检查
    zhipu_api_key: str = os.getenv("ZHIPU_API_KEY", "")

    # 智谱 LLM 模型名（阶段2 启用，开发期用 flash 控成本；可换 glm-4-plus 提质）
    glm_model: str = os.getenv("GLM_MODEL", "glm-4-flash")

    # Chroma 向量库持久化目录（阶段1 启用，数据落本地磁盘）
    chroma_persist_dir: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")

    # 单次检索返回的片段数 top-k（阶段2 启用）
    top_k: int = int(os.getenv("TOP_K", "4"))

    # ── 阶段4 业务加固：鉴权与限流 ───────────────────────────
    # 客户端 API Key（用于 API Key 中间件）。支持配置多个，逗号分隔。
    # 为空时中间件退化为「不鉴权」（仅开发便利，生产务必配置）。
    api_keys: list = [
        k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()
    ]

    # 限流：单个客户端 IP 每分钟最多允许的请求数（针对 /api 业务接口）。
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))


settings = Settings()
