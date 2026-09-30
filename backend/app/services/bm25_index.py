"""BM25 关键词索引：和向量检索互补的一路召回。

为什么需要它：
  纯向量检索擅长"语义相近"，但对专有名词、编号、合同条款这种
  "必须字面精确匹配"的情况经常搜不出来。BM25 是经典的关键词检索，
  正好补上这块短板。两路召回结果再用 RRF 融合，比单路召回准得多。

实现要点：
  - 中文用 jieba 分词（BM25 默认按空格切，中文不分词等于废了）
  - 索引建在内存里，服务启动时从 Chroma 全量读一次
  - 每次入库后重建索引（数据量小，企业知识库几十~几百条，重建毫秒级）
"""
from __future__ import annotations

import threading

import jieba
from rank_bm25 import BM25Okapi

_bm25: BM25Okapi | None = None
_bm25_ids: list[str] = []
_lock = threading.Lock()

# 停用词：这些词对检索没有区分度，去掉避免噪声
_STOPWORDS = {
    "的", "了", "和", "是", "在", "我", "有", "也", "就", "都", "而",
    "及", "与", "或", "一个", "没有", "我们", "你们", "他们", "这个",
    "那个", "可以", "需要", "应该", "如果", "因为", "所以", "但是",
}


def _tokenize(text: str) -> list[str]:
    """中文分词 + 去停用词 + 去单字噪声。"""
    words = jieba.lcut(text.lower())
    return [
        w.strip()
        for w in words
        if w.strip() and len(w.strip()) > 1 and w.strip() not in _STOPWORDS
    ]


def rebuild_index() -> int:
    """从 Chroma 全量读出文档，重建 BM25 索引。返回索引条数。"""
    global _bm25, _bm25_ids
    from app.services.vector_store import get_collection

    collection = get_collection()
    res = collection.get(include=["documents"])
    docs = res.get("documents") or []
    ids = res.get("ids") or []

    if not docs:
        with _lock:
            _bm25 = None
            _bm25_ids = []
        return 0

    tokenized = [_tokenize(d) for d in docs]
    # 过滤掉空 token 的文档（BM25Okapi 对空列表会报错）
    valid = [(i, toks) for i, toks in enumerate(tokenized) if toks]
    if not valid:
        with _lock:
            _bm25 = None
            _bm25_ids = []
        return 0

    valid_idx = [i for i, _ in valid]
    valid_tokens = [toks for _, toks in valid]
    valid_ids = [ids[i] for i in valid_idx]

    with _lock:
        _bm25 = BM25Okapi(valid_tokens)
        _bm25_ids = valid_ids
    return len(valid_ids)


def _ensure_index() -> None:
    if _bm25 is None:
        rebuild_index()


def search(query: str, k: int = 10) -> list[tuple[str, float]]:
    """BM25 召回 top-k，返回 [(id, score)]，score > 0。"""
    _ensure_index()
    if _bm25 is None:
        return []
    tokens = _tokenize(query)
    if not tokens:
        return []
    scores = _bm25.get_scores(tokens)
    ranked = sorted(
        zip(_bm25_ids, scores), key=lambda x: x[1], reverse=True
    )[:k]
    return [(doc_id, float(s)) for doc_id, s in ranked if s > 0]
