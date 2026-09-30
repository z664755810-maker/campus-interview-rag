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


def search(query: str, top_k: int | None = None, min_score: float | None = None) -> list[dict]:
    """混合检索：向量语义召回 + BM25 关键词召回，RRF 融合后取 top-k。

    为什么混合：
      - 纯向量：语义相近但专有名词/编号/条款可能漏
      - 纯 BM25：字面匹配但换个说法就搜不到
      - 两路各召回 top_k*2，用 RRF（倒数排名融合）合并，比单路准

    Chroma 余弦距离：0=完全相同，1=完全不同。阈值过滤在后段做。
    """
    from app.services.embeddings import embed_query
    from app.services import bm25_index

    top_k = top_k or settings.top_k
    threshold = min_score if min_score is not None else settings.min_score
    fetch_k = top_k * 2  # 每路多召回一些，融合后再裁

    collection = get_collection()

    # ── 路 1：向量语义召回 ──
    q_vec = embed_query(query)
    vec_res = collection.query(
        query_embeddings=[q_vec],
        n_results=fetch_k,
        include=["documents", "metadatas", "distances"],
    )
    vec_ids = vec_res["ids"][0] if vec_res.get("ids") else []
    vec_docs = vec_res["documents"][0]
    vec_metas = vec_res["metadatas"][0]
    vec_dists = vec_res["distances"][0]

    # vec_rank: id -> 在向量结果里的名次（0 开始）
    vec_rank = {doc_id: i for i, doc_id in enumerate(vec_ids)}

    # ── 路 2：BM25 关键词召回 ──
    bm25_hits = bm25_index.search(query, k=fetch_k)
    bm25_rank = {doc_id: i for i, (_doc_id, _s) in enumerate(bm25_hits)}

    # ── RRF 融合：score = Σ 1/(60+rank)，出现在哪路就加哪路的分 ──
    rrf_scores: dict[str, float] = {}
    rrf_k = 60
    for doc_id, rank in vec_rank.items():
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank)
    for doc_id, rank in bm25_rank.items():
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank)

    # 按 RRF 分排序，取前 top_k
    fused = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    fused_ids = [doc_id for doc_id, _ in fused]

    # 用融合后的 id 列表，从向量结果里取出对应的 doc/meta/dist
    id_to_doc = dict(zip(vec_ids, vec_docs))
    id_to_meta = dict(zip(vec_ids, vec_metas))
    id_to_dist = dict(zip(vec_ids, vec_dists))

    out = []
    for doc_id in fused_ids:
        doc = id_to_doc.get(doc_id)
        meta = id_to_meta.get(doc_id, {})
        dist = id_to_dist.get(doc_id, 2.0)
        if doc is None:
            # BM25 召回了但向量没召回的 id，从 Chroma 单独取
            got = collection.get(ids=[doc_id], include=["documents", "metadatas"])
            if got["documents"]:
                doc = got["documents"][0]
                meta = got["metadatas"][0]
                dist = 2.0
            else:
                continue
        # 阈值过滤
        if threshold > 0 and dist > threshold:
            continue
        out.append({"text": doc, "metadata": meta, "distance": dist})
    return out
