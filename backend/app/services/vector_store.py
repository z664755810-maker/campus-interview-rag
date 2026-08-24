"""Chroma 向量库封装。

Chroma 负责：把「向量 + 原文 + 元数据」一体存储，并提供 ANN 近似最近邻检索。
我们只用它存数据和查数据，向量由我们自己（智谱）算好后显式塞进去，
这样能完全掌控「入库/检索用同一套坐标系」，也方便以后换成别的服务。
"""
import chromadb

from app.core.config import settings

COLLECTION_NAME = "interview_qa"


def get_client():
    # 持久化到本地磁盘，重启也在；路径来自配置，便于迁移
    return chromadb.PersistentClient(path=settings.chroma_persist_dir)


def get_collection(name: str = COLLECTION_NAME):
    client = get_client()
    # 不传 embedding_function：我们自己在 add/query 时显式给向量
    return client.get_or_create_collection(name=name)


def add_chunks(chunks: list[dict]):
    """chunks: [{"id","text","metadata","vector"}]。

    用 upsert 而非 add：重复入库相同 id 时自动覆盖，脚本可反复跑不会报错。
    """
    collection = get_collection()
    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
        embeddings=[c["vector"] for c in chunks],
    )


def search(query: str, top_k: int | None = None) -> list[dict]:
    """检索 top-k 相关片段，返回原文 + 元数据 + 距离（越小越相关）。"""
    from app.services.zhipu import embed_query

    top_k = top_k or settings.top_k
    collection = get_collection()
    q_vec = embed_query(query)
    res = collection.query(
        query_embeddings=[q_vec],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    out = []
    for doc, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        out.append({"text": doc, "metadata": meta, "distance": dist})
    return out
