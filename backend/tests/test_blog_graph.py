"""博客生成工作流（LangGraph 图 + SSE 接口）测试。"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from langgraph.types import Command

from app.graph import graph
from app.main import app

OUTLINE_JSON = '{"title": "原始标题", "outline": ["第一节", "第二节"]}'
REVISED_JSON = '{"title": "修订标题", "outline": ["新第一节", "新第二节", "新第三节"]}'
ARTICLE = "# 原始标题\n\n第一节正文。\n\n## 第二节\n\n第二节正文。"


class FakeWrapper:
    """按 prompt 内容区分大纲生成/修订/正文撰写的假模型。"""

    last_used = (None, "test-provider", "test-model")

    def __init__(self) -> None:
        self.prompts: list[tuple[str | None, str]] = []

    def astream(self, prompt: str, *, node: str | None = None, thread_id: str | None = None):
        self.prompts.append((node, prompt))
        if node == "outline":
            text = REVISED_JSON if "用户修订要求" in prompt else OUTLINE_JSON
        else:
            text = ARTICLE
        # 模拟逐 token 流式输出
        for char in text:
            yield char


@pytest.fixture()
def fake_model(monkeypatch) -> FakeWrapper:
    wrapper = FakeWrapper()
    monkeypatch.setattr("app.graph.build_fallback_model", lambda *args, **kwargs: wrapper)
    monkeypatch.setattr(
        "app.api.routes.build_fallback_model", lambda *args, **kwargs: wrapper
    )
    return wrapper


def _new_config() -> dict:
    return {"configurable": {"thread_id": uuid.uuid4().hex}}


def _start_state() -> dict:
    return {
        "topic": "LangGraph 最佳实践",
        "keyword": "langgraph tutorial",
        "provider": None,
        "model": None,
        "provider_api_keys": {},
    }


def _run(source, config) -> tuple[list[dict], dict[str, str]]:
    """驱动图执行，收集 interrupt 载荷与自定义 token 流。"""
    interrupts: list[dict] = []
    tokens: dict[str, list[str]] = {"outline_token": [], "article_token": []}
    for mode, chunk in graph.stream(source, config, stream_mode=["updates", "custom"]):
        if mode == "custom":
            tokens[chunk["type"]].append(chunk["text"])
        elif "__interrupt__" in chunk:
            interrupts.append(chunk["__interrupt__"][0].value)
    return interrupts, {kind: "".join(parts) for kind, parts in tokens.items()}


def test_graph_outline_interrupt_revise_approve(fake_model) -> None:
    config = _new_config()

    # 首次运行：生成大纲后在 interrupt 处暂停
    interrupts, tokens = _run(_start_state(), config)
    assert len(interrupts) == 1
    assert interrupts[0] == {"title": "原始标题", "outline": ["第一节", "第二节"]}
    assert json.loads(tokens["outline_token"])["title"] == "原始标题"

    # 修订：回到 outline 节点重新生成，再次暂停
    interrupts, _ = _run(
        Command(resume={"action": "revise", "instruction": "增加一节性能优化"}), config
    )
    assert interrupts == [
        {"title": "修订标题", "outline": ["新第一节", "新第二节", "新第三节"]}
    ]
    revise_prompts = [p for node, p in fake_model.prompts if node == "outline"]
    assert any("增加一节性能优化" in p for p in revise_prompts)

    # 确认（附手动编辑后的大纲）：流式撰写正文直至完成
    interrupts, tokens = _run(
        Command(
            resume={
                "action": "approve",
                "title": "手动改后的标题",
                "outline": ["手动一节", "手动二节"],
            }
        ),
        config,
    )
    assert interrupts == []
    assert tokens["article_token"] == ARTICLE
    final = graph.get_state(config).values
    assert final["article"] == ARTICLE
    assert final["title"] == "手动改后的标题"
    draft_prompts = [p for node, p in fake_model.prompts if node == "draft_section"]
    assert len(draft_prompts) == 1
    assert "手动一节" in draft_prompts[0]
    assert "手动改后的标题" in draft_prompts[0]


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append((event, data))
    return events


def test_sse_start_and_resume_flow(fake_model) -> None:
    client = TestClient(app)

    start = client.post("/api/blog/threads", json={"topic": "LangGraph 最佳实践"})
    assert start.status_code == 200
    events = _parse_sse(start.text)
    kinds = [kind for kind, _ in events]
    assert kinds[0] == "thread"
    assert "outline_token" in kinds
    assert "interrupt" in kinds
    assert kinds[-1] == "done"
    thread_id = events[0][1]["thread_id"]
    interrupt_data = next(data for kind, data in events if kind == "interrupt")
    assert interrupt_data["outline"] == ["第一节", "第二节"]

    resume = client.post(
        f"/api/blog/threads/{thread_id}/resume", json={"action": "approve"}
    )
    assert resume.status_code == 200
    events = _parse_sse(resume.text)
    kinds = [kind for kind, _ in events]
    assert "article_token" in kinds
    result = next(data for kind, data in events if kind == "result")
    assert result["article"] == ARTICLE
    assert result["provider_name"] == "test-provider"

    article = "".join(
        data["text"] for kind, data in events if kind == "article_token"
    )
    assert article == ARTICLE


def test_sse_resume_revise_streams_new_outline(fake_model) -> None:
    client = TestClient(app)
    start = client.post("/api/blog/threads", json={"topic": "LangGraph 最佳实践"})
    thread_id = _parse_sse(start.text)[0][1]["thread_id"]

    resume = client.post(
        f"/api/blog/threads/{thread_id}/resume",
        json={"action": "revise", "instruction": "增加一节性能优化"},
    )
    assert resume.status_code == 200
    events = _parse_sse(resume.text)
    interrupt_data = next(data for kind, data in events if kind == "interrupt")
    assert interrupt_data == {
        "title": "修订标题",
        "outline": ["新第一节", "新第二节", "新第三节"],
    }


def test_sse_resume_unknown_thread_404(fake_model) -> None:
    client = TestClient(app)
    resp = client.post("/api/blog/threads/nonexistent/resume", json={"action": "approve"})
    assert resp.status_code == 404


def test_sse_revise_requires_instruction() -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/blog/threads/whatever/resume", json={"action": "revise"}
    )
    assert resp.status_code == 422
