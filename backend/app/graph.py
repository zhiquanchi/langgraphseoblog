"""博客生成 LangGraph 状态图：outline → review_outline(interrupt) → draft。

- `outline` 节点流式生成/修订大纲（修订指令驱动自循环）；
- `review_outline` 节点通过 `interrupt` 暂停，等待用户确认或修订；
- `draft` 节点按确认后的大纲流式撰写正文；
- 自定义流式事件经 `StreamWriter` 发出（outline_token / article_token），
  由 API 层转换为 SSE 推送给前端；
- MemorySaver 按 thread_id 保存检查点，支持多轮修订与断点续跑。
"""

from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import StreamWriter, interrupt
from langchain_core.runnables import RunnableConfig

from app.llm.fallback import FallbackChatModel, build_fallback_model
from app.outline import build_outline_prompt, build_revise_prompt, parse_outline_result


class BlogState(TypedDict, total=False):
    topic: str
    keyword: str
    provider: str | None
    model: str | None
    provider_api_keys: dict[int, str]
    title: str
    outline: list[str]
    instruction: str
    article: str
    provider_name: str
    model_name: str


def _thread_id(config: RunnableConfig) -> str | None:
    return config.get("configurable", {}).get("thread_id")


def _build_wrapper(state: BlogState, node: str) -> FallbackChatModel:
    return build_fallback_model(
        node,
        state.get("provider"),
        model_override=state.get("model"),
        provider_api_keys=state.get("provider_api_keys"),
    )


def _stream_llm(
    wrapper: FallbackChatModel,
    prompt: str,
    *,
    node: str,
    thread_id: str | None,
    event: str,
    writer: StreamWriter,
) -> str:
    """流式调用模型：逐 token 发出自定义事件，同时拼出完整文本。"""
    chunks: list[str] = []
    for text in wrapper.astream(prompt, node=node, thread_id=thread_id):
        chunks.append(text)
        writer({"type": event, "text": text})
    return "".join(chunks)


def outline_node(state: BlogState, config: RunnableConfig, *, writer: StreamWriter) -> dict[str, Any]:
    """生成或修订大纲；修订时带上用户指令与当前大纲。"""
    wrapper = _build_wrapper(state, "outline")
    instruction = state.get("instruction") or ""
    if instruction:
        prompt = build_revise_prompt(
            state["topic"], state.get("keyword", ""), state["outline"], instruction
        )
    else:
        prompt = build_outline_prompt(state["topic"], state.get("keyword", ""))
    raw = _stream_llm(
        wrapper, prompt, node="outline", thread_id=_thread_id(config), event="outline_token", writer=writer
    )
    parsed = parse_outline_result(raw)
    _, provider_name, model_name = wrapper.last_used or (None, "env", "env")
    return {
        "title": parsed["title"],
        "outline": parsed["outline"],
        "instruction": "",
        "provider_name": provider_name,
        "model_name": model_name,
    }


def review_outline_node(state: BlogState, config: RunnableConfig) -> dict[str, Any]:
    """人工确认节点：interrupt 暂停，等待修订指令或确认（可附手动编辑结果）。"""
    decision = interrupt({"title": state["title"], "outline": state["outline"]})
    if isinstance(decision, dict) and decision.get("action") == "revise":
        return {"instruction": decision["instruction"]}
    decision = decision if isinstance(decision, dict) else {}
    return {
        "title": decision.get("title") or state["title"],
        "outline": decision.get("outline") or state["outline"],
    }


def route_after_review(state: BlogState) -> str:
    """有修订指令则回到 outline 重新生成，否则进入正文撰写。"""
    return "outline" if state.get("instruction") else "draft"


def draft_node(state: BlogState, config: RunnableConfig, *, writer: StreamWriter) -> dict[str, Any]:
    """按确认后的大纲流式撰写完整正文。"""
    wrapper = _build_wrapper(state, "draft_section")
    keyword_section = f"目标关键词：{state['keyword']}\n" if state.get("keyword") else ""
    outline_section = "\n".join(
        f"{index}. {section}" for index, section in enumerate(state["outline"], start=1)
    )
    prompt = (
        f"请围绕主题「{state['topic']}」撰写一篇 SEO 优化的博客文章。\n"
        f"{keyword_section}"
        f"文章标题（H1）：{state['title']}\n"
        f"严格按照以下大纲逐节展开，每个小节对应一个 H2：\n{outline_section}\n"
        "要求：Markdown 格式；标题与正文自然融入目标关键词；"
        "每个小节内容详实、有深度，包含具体做法或示例；输出完整文章正文。"
    )
    article = _stream_llm(
        wrapper, prompt, node="draft_section", thread_id=_thread_id(config), event="article_token", writer=writer
    )
    _, provider_name, model_name = wrapper.last_used or (None, "env", "env")
    return {"article": article, "provider_name": provider_name, "model_name": model_name}


builder = StateGraph(BlogState)
builder.add_node("outline", outline_node)
builder.add_node("review_outline", review_outline_node)
builder.add_node("draft", draft_node)
builder.add_edge(START, "outline")
builder.add_edge("outline", "review_outline")
builder.add_conditional_edges(
    "review_outline", route_after_review, {"outline": "outline", "draft": "draft"}
)
builder.add_edge("draft", END)

graph = builder.compile(checkpointer=MemorySaver())
