"""RAG 问答服务（阶段2 核心）。

把「检索到的资料」+「用户问题」拼成带引用编号的 Prompt，交给 GLM 生成，
返回「答案 + 引用溯源映射」。

这是 RAG 抑制幻觉的关键环节：模型不再"凭记忆自由发挥"，而是被约束在
我们提供的资料范围内作答，并且每条论断都能溯源到具体题目。
"""
from app.services.vector_store import search
from app.services.zhipu import generate_text


def build_prompt(query: str, contexts: list[dict]) -> tuple[str, list[dict]]:
    """把检索到的片段拼成带引用编号的 Prompt，同时产出引用映射表。

    contexts: [{text, metadata, distance}]（来自 vector_store.search）
    返回 (prompt, citations)，citations 用于前端展示"出处卡片"。
    """
    parts = []
    citations = []
    for i, ctx in enumerate(contexts, start=1):
        meta = ctx.get("metadata", {})
        src = meta.get("source", "未知")
        subject = meta.get("subject", "")
        title = meta.get("title", "")
        q_index = meta.get("q_index")
        # 引用映射：编号 -> 该片段的元数据，前端据此渲染出处
        citations.append(
            {
                "index": i,
                "source": src,
                "subject": subject,
                "q_index": q_index,
                "title": title,
                "distance": round(ctx.get("distance", 0.0), 4),
                "content": ctx["text"],
            }
        )
        parts.append(f"【资料 {i}】来源：{src}（{subject} - {title}）\n{ctx['text']}")

    context_block = "\n\n".join(parts)

    prompt = f"""你是一个校招软件开发面试辅导助手。请仅根据下面提供的【资料】回答用户的问题，严格遵循以下规则：
1. 只能使用【资料】中的内容作答，严禁使用你自己的知识或任何外部信息。
2. 如果【资料】中没有相关信息，请明确回答"资料库中未包含该内容"，不要编造。
3. 回答时请在相关论断后标注引用，格式为 [1]、[2] 等，对应下方资料的编号。
4. 回答要条理清晰、适合面试备考场景，必要时分点列出要点。

【资料】
{context_block}

【用户问题】
{query}

【回答】"""
    return prompt, citations


def ask(query: str, top_k: int | None = None) -> dict:
    """阶段2 主入口：检索 -> 拼 Prompt -> GLM 生成 -> 引用溯源。"""
    contexts = search(query, top_k=top_k)
    if not contexts:
        return {
            "query": query,
            "answer": "资料库为空，请先通过 /api/documents/upload 上传面试题文档。",
            "citations": [],
        }
    prompt, citations = build_prompt(query, contexts)
    answer = generate_text(prompt, temperature=0.3)
    return {"query": query, "answer": answer, "citations": citations}
