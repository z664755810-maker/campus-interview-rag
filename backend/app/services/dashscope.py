"""阿里百炼 DashScope embedding 客户端。

背景：智谱免费档 embedding 接口持续 429（账户级配额超限），
因此新增 DashScope 作为 embedding provider（专用于「向量化」环节）；
文本生成仍用智谱 GLM-4（chat 接口不限流，作品集生成质量不受影响）。

与 zhipu.py 保持完全一致的函数签名：embed_texts(list[str]) -> list[list[float]]
这样 vector_store / ingestion 切换 provider 时零成本。

接口选择：OpenAI 兼容接口（https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings）。
理由：返回格式与智谱/OpenAI 一致（data[].embedding + index），比原生 DashScope API 更简洁，
且不需要额外装 SDK（用 requests 直接调，与 zhipu.py 同构）。
"""
import os

import requests

from app.core.config import settings

EMBEDDING_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
EMBEDDING_MODEL = "text-embedding-v3"
# 维度：text-embedding-v3 默认 1024（可选 512/768/1024）。
# 注意：必须与 chroma_db 里已存向量维度一致；切换 provider 时务必清空 chroma_db 重灌，
# 不同维度/不同模型的向量空间不可比，混用会导致检索结果错乱。
EMBED_DIM = 1024
# OpenAI 兼容接口单次最多 10 条输入
_BATCH_SIZE = 10


def _call_embedding(texts: list[str]) -> list[list[float]]:
    if not settings.dashscope_api_key:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY，请在 backend/.env 中填写")
    out = []
    # 分批，避免单次请求超过 10 条上限
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        resp = requests.post(
            EMBEDDING_API_URL,
            headers={
                "Authorization": f"Bearer {settings.dashscope_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": EMBEDDING_MODEL,
                "input": batch,
                "dimensions": EMBED_DIM,
            },
            timeout=60,
        )
        resp.raise_for_status()
        # OpenAI 兼容返回：{"data":[{"embedding":[...],"index":0}, ...], ...}
        data = resp.json()["data"]
        # 按 index 排序，保证向量与输入顺序严格一致（分批后顺序由 index 决定）
        data.sort(key=lambda x: x["index"])
        out.extend([item["embedding"] for item in data])
    return out


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量文本 -> 向量列表。"""
    return _call_embedding(texts)


def embed_query(text: str) -> list[float]:
    """单条查询 -> 向量。检索时与入库用同一模型，坐标才同源。"""
    return _call_embedding([text])[0]
