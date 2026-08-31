"""智谱 GLM 客户端：同时负责「向量化」与「文本生成」两件事。

阶段1 用的是 embedding（文字 -> 向量，用于检索）；
阶段2 新增 chat/completions（Prompt -> 文字，用于生成回答）。
两者同属智谱开放平台，但接口路径、请求体、返回结构完全不同——这是新手最容易混的点。
"""
import hashlib
import math
import os
import struct

import requests

from app.core.config import settings

EMBEDDING_API_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
EMBEDDING_MODEL = "embedding-3"

# 智谱 GLM 对话生成接口（阶段2 启用）
CHAT_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 段 A 测试用：本地/CI 环境下，智谱 free tier 限流经常让我们没法跑端到端；
# MOCK_EMBED=true 时用「文本 hash → 伪向量」替代真实 API 调用。
# 仅用于开发演示，生产环境务必保持 false（否则检索质量=0，但其他功能链路都能验证）。
MOCK_EMBED = os.getenv("MOCK_EMBED", "").lower() in ("1", "true", "yes")
EMBED_DIM = 1024  # 与智谱 embedding-3 维度一致，避免改 Chroma schema


def _mock_embed(texts: list[str]) -> list[list[float]]:
    """把文本 hash 成 1024 维伪向量。

    只保证：相同文本 → 相同向量；不同文本 → 几乎一定不同。
    检索质量肯定是 0（hash 不会学语义），但能完整跑通「入库/查/删/分组」全链路。
    """
    out = []
    for t in texts:
        seed = hashlib.sha256(t.encode("utf-8")).digest()
        # 1024 个 float 需要 1024*4=4096 字节，sha256 不够长，循环
        buf = (seed * ((EMBED_DIM * 4) // len(seed) + 1))[: EMBED_DIM * 4]
        raw = struct.unpack(f"{EMBED_DIM}f", buf)
        # 关键修复：hash 字节直接当 float 解，某些组合会是 NaN/Inf（指数位全 1），
        # Chroma 会拒收。先兜底成 0，再 L2 归一化成单位向量，保证有限且可用。
        vec = [v if math.isfinite(v) else 0.0 for v in raw]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        out.append([v / norm for v in vec])
    return out


def _call_embedding(texts: list[str]) -> list[list[float]]:
    if MOCK_EMBED:
        return _mock_embed(texts)
    if not settings.zhipu_api_key:
        raise RuntimeError("未配置 ZHIPU_API_KEY，请在 backend/.env 中填写")
    resp = requests.post(
        EMBEDDING_API_URL,
        headers={
            "Authorization": f"Bearer {settings.zhipu_api_key}",
            "Content-Type": "application/json",
        },
        json={"model": EMBEDDING_MODEL, "input": texts},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    # 按 index 排序，保证向量与输入顺序严格一致
    data.sort(key=lambda x: x["index"])
    return [item["embedding"] for item in data]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量文本 -> 向量列表。"""
    return _call_embedding(texts)


def embed_query(text: str) -> list[float]:
    """单条查询 -> 向量。检索时与入库用同一模型，坐标才同源。"""
    return _call_embedding([text])[0]


def generate_text(prompt: str, temperature: float = 0.3, max_tokens: int = 1024) -> str:
    """阶段2 核心：把拼好的 Prompt 交给智谱 GLM 生成回答。

    与 embedding 的区别（讲师划重点）：
    - embedding 是「文字 -> 向量」，用于检索；
    - chat/completions 是「对话 -> 文字」，用于生成。
    两者都是同一个开放平台的 API，但路径、请求体、返回结构都不同。
    """
    if not settings.zhipu_api_key:
        raise RuntimeError("未配置 ZHIPU_API_KEY，请在 backend/.env 中填写")
    resp = requests.post(
        CHAT_API_URL,
        headers={
            "Authorization": f"Bearer {settings.zhipu_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.glm_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
