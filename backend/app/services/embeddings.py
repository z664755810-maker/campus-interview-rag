"""Embedding provider 统一入口。

把「用哪个 embedding 服务」收敛到一处，ingestion / vector_store 都从这里导入，
切换 provider 时只改 config.embedding_provider，不必动业务代码。

支持的 provider（在 backend/.env 用 EMBEDDING_PROVIDER 指定）：
  - "zhipu"     : 智谱 embedding-3（2048 维），需要 ZHIPU_API_KEY
  - "dashscope" : 阿里百炼 text-embedding-v3（1024 维），需要 DASHSCOPE_API_KEY
"""
from app.core.config import settings


def _provider():
    """按配置返回 provider 模块，模块都暴露 embed_texts / embed_query。"""
    if settings.embedding_provider == "dashscope":
        from app.services import dashscope as p
    else:
        from app.services import zhipu as p
    return p


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量文本 -> 向量列表。"""
    return _provider().embed_texts(texts)


def embed_query(text: str) -> list[float]:
    """单条查询 -> 向量。检索时与入库用同一模型，坐标才同源。"""
    return _provider().embed_query(text)
