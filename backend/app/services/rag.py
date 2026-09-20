"""RAG 问答服务（企业知识库增强版）。

把知识库中的资料与用户问题拼成带引用编号的 Prompt，交给大模型生成结构化答案。
这里不再局限于面试题库，而是面向真实企业场景：政策查询、流程梳理、执行摘要、风险审查。
"""
from app.services.vector_store import search
from app.services.zhipu import generate_text


PROMPT_TEMPLATES = {
    "answer": """你是一个企业知识库助手。请仅基于下面的【资料】回答问题，严格遵守以下规则：
1. 只能使用【资料】中的内容，禁止凭空补充外部知识。
2. 若资料与问题明显不相关，请直接说明“当前知识库中未找到相关资料”，不要强行编造。
3. 在关键结论后标注引用 [1]、[2] 等，引用必须准确对应下方资料编号。
4. 回答格式要清晰，适合团队内部查询和知识沉淀。

【资料】
{context_block}

【用户问题】
{query}

【回答】""",
    "summary": """你是企业运营分析助手。请基于【资料】提炼出结论，并按以下结构输出：
1. 结论概述
2. 关键事实与依据
3. 影响范围
4. 需要进一步确认的事项

要求：只使用【资料】中的内容；关键事实必须标注 [1]、[2] 等引用；不能引入外部经验。

【资料】
{context_block}

【任务】
{query}

【输出】""",
    "action_items": """你是一个流程执行助手。请从【资料】中提炼可执行动作清单，输出结构如下：
1. 关键动作
2. 优先级
3. 负责人建议（如资料中明确提到负责人则写出，若无明确负责人则写“待明确”）
4. 完成验收标准

需要严格参考资料，必要时使用引用 [1]、[2]。

【资料】
{context_block}

【任务】
{query}

【输出】""",
    "risk_check": """你是合规与风险评估助手。请基于【资料】识别潜在风险，并输出：
1. 潜在风险
2. 触发条件
3. 影响对象
4. 风险控制建议

仅使用资料内容；如果没有明显风险，请明确说明“当前资料未发现明显风险”并给出理由。

【资料】
{context_block}

【任务】
{query}

【输出】""",
}


def build_prompt(query: str, contexts: list[dict], mode: str = "answer") -> tuple[str, list[dict]]:
    """把检索到的片段拼成带引用编号的 Prompt，同时产出引用映射表。"""
    parts = []
    citations = []
    for i, ctx in enumerate(contexts, start=1):
        meta = ctx.get("metadata", {})
        src = meta.get("source", "未知")
        subject = meta.get("subject", "")
        title = meta.get("title", "")
        q_index = meta.get("q_index")
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
    template = PROMPT_TEMPLATES.get(mode, PROMPT_TEMPLATES["answer"])
    prompt = template.format(context_block=context_block, query=query)
    return prompt, citations


def ask(query: str, top_k: int | None = None, mode: str = "answer") -> dict:
    """主入口：检索 -> 拼 Prompt -> 生成 -> 溯源。"""
    contexts = search(query, top_k=top_k)
    if not contexts:
        return {
            "query": query,
            "mode": mode,
            "answer": "当前知识库中未找到与该问题相关的资料。请换一个更具体的关键词，或上传对应的政策、流程、FAQ、会议纪要等文档。",
            "citations": [],
        }
    prompt, citations = build_prompt(query, contexts, mode=mode)
    answer = generate_text(prompt, temperature=0.25)
    return {"query": query, "mode": mode, "answer": answer, "citations": citations}
