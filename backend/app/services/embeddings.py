"""Embedding provider 统一入口。

把「用哪个 embedding 服务」收敛到一处，ingestion / vector_store 都从这里导入，
切换 provider 时只改 config.embedding_provider，不必动业务代码。

支持的 provider（在 backend/.env 用 EMBEDDING_PROVIDER 指定）：
  - "zhipu"     : 智谱 embedding-3（2048 维），需要 ZHIPU_API_KEY
  - "dashscope" : 阿里百炼 text-embedding-v3（1024 维），需要 DASHSCOPE_API_KEY

MOCK 模式（本地无 key / 限流时验证用）：
  设环境变量 MOCK_EMBED=true 后，本模块直接产出「确定性伪向量」，
  不再调用任何外部 API。维度与当前 provider 保持一致（dashscope=1024 / zhipu=2048），
  保证本地灌库 / 检索链路可端到端验证，且重灌不会因 401/429 卡住。
  ⚠️ MOCK 向量只是占位，相似度无意义——只用于验证「流程通不通」，
     真实检索质量必须去掉 MOCK_EMBED、用真 key 在线上验证。
"""
import hashlib
import math
import os

from app.core.config import settings


# 各 provider 的向量维度，MOCK 据此对齐，避免与真实向量维度不一致导致 Chroma 报错
_DIM_BY_PROVIDER = {
    "dashscope": 1024,
    "zhipu": 2048,
}


def _provider():
    """按配置返回 provider 模块，模块都暴露 embed_texts / embed_query。"""
    if settings.embedding_provider == "dashscope":
        from app.services import dashscope as p
    else:
        from app.services import zhipu as p
    return p


def _mock_embed(texts: list[str]) -> list[list[float]]:
    """确定性伪向量：同一文本永远得到同一向量，维度跟随 provider。

    实现：用文本 SHA-256 作种子，生成 dim 个 [0,1) 随机数，
    再 L2 归一化（保证向量有限、可计算余弦相似度，不出现 NaN/Inf）。
    """
    dim = _DIM_BY_PROVIDER.get(settings.embedding_provider, 1024)
    out = []
    for text in texts:
        seed = hashlib.sha256((text or "").encode("utf-8")).digest()
        # 用种子构造一个可复现的伪随机序列
        state = int.from_bytes(seed[:8], "big")
        vec = []
        for _ in range(dim):
            # 线性同余发生器（LCG），纯本地、确定性强
            state = (state * 1103515245 + 12345) & 0x7FFFFFFF
            vec.append(state / 0x7FFFFFFF)
        # L2 归一化
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            norm = 1.0
        vec = [v / norm for v in vec]
        out.append(vec)
    return out


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量文本 -> 向量列表。"""
    if os.getenv("MOCK_EMBED", "").lower() in {"1", "true", "yes"}:
        return _mock_embed(texts)
    return _provider().embed_texts(texts)


def embed_query(text: str) -> list[float]:
    """单条查询 -> 向量。检索时与入库用同一模型，坐标才同源。"""
    if os.getenv("MOCK_EMBED", "").lower() in {"1", "true", "yes"}:
        return _mock_embed([text])[0]
    return _provider().embed_query(text)
