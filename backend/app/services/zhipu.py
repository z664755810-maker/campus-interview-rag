"""智谱 GLM 客户端：同时负责「向量化」与「文本生成」两件事。

阶段1 用的是 embedding（文字 -> 向量，用于检索）；
阶段2 新增 chat/completions（Prompt -> 文字，用于生成回答）。
两者同属智谱开放平台，但接口路径、请求体、返回结构完全不同——这是新手最容易混的点。
"""
import requests

from app.core.config import settings

EMBEDDING_API_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
EMBEDDING_MODEL = "embedding-3"

# 智谱 GLM 对话生成接口（阶段2 启用）
CHAT_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"


def _call_embedding(texts: list[str]) -> list[list[float]]:
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
