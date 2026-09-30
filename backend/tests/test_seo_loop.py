"""SEO 评分循环与 RAG 检索接入工作流的测试。"""

import pytest
from langgraph.graph import END
from langgraph.types import Command

from app.graph import MAX_SEO_REVISIONS, SEO_SCORE_THRESHOLD, graph, route_after_seo_score
from app.seo import build_seo_rewrite_prompt, build_seo_score_prompt, parse_score_result
from test_blog_graph import (
    ARTICLE,
    REVISED_ARTICLE,
    FakeWrapper,
    _new_config,
    _run,
    _start_state,
    install_fake_model,
)


def test_parse_score_result_variants() -> None:
    parsed = parse_score_result('{"score": 0.82, "suggestions": ["补示例", "压缩开头"]}')
    assert parsed == {"score": 0.82, "suggestions": ["补示例", "压缩开头"]}

    # Markdown 围栏容错 + 越界分数收敛
    fenced = '```json\n{"score": 1.7, "suggestions": []}\n```'
    assert parse_score_result(fenced)["score"] == 1.0
    assert parse_score_result('{"score": -0.2}')["score"] == 0.0

    for bad in ("不是 JSON", '{"score": true}', '{"score": "0.5"}', '{"score": 0.5, "suggestions": [1]}'):
        with pytest.raises(ValueError):
            parse_score_result(bad)


def test_route_after_seo_score_boundaries() -> None:
    route = route_after_seo_score
    assert route({"seo_score": SEO_SCORE_THRESHOLD - 0.01, "seo_revisions": 0}) == "seo_optimize"
    assert route({"seo_score": SEO_SCORE_THRESHOLD, "seo_revisions": 0}) == END
    # 重写预算耗尽后即使分数不足也放行,避免死循环
    assert route({"seo_score": 0.1, "seo_revisions": MAX_SEO_REVISIONS}) == END


def test_seo_rewrite_prompt_contains_suggestions() -> None:
    prompt = build_seo_rewrite_prompt("主题", "关键词", "标题", ["一", "二"], "原文", ["建议A", "建议B"])
    assert "建议A" in prompt and "建议B" in prompt
    assert "原文" in prompt


def test_seo_loop_stops_at_revision_budget(monkeypatch) -> None:
    """持续低分时最多重写 MAX_SEO_REVISIONS 次后放行,不产生死循环。"""
    wrapper = install_fake_model(monkeypatch, FakeWrapper(scores=(0.4,)))
    config = _new_config()
    _run(_start_state(), config)
    _run(Command(resume={"action": "approve"}), config)
    optimize_prompts = [p for node, p in wrapper.prompts if node == "seo_optimize"]
    score_prompts = [p for node, p in wrapper.prompts if node == "seo_score"]
    assert len(optimize_prompts) == MAX_SEO_REVISIONS
    assert len(score_prompts) == MAX_SEO_REVISIONS + 1  # 初评 + 每次重写后复评
    final = graph.get_state(config).values
    assert final["seo_revisions"] == MAX_SEO_REVISIONS
    assert final["article"] == REVISED_ARTICLE


class FakeRagService:
    """返回固定命中片段的假知识库服务。"""

    enabled = True

    def search(self, query: str, k: int = 4) -> list[dict]:
        assert "LangGraph" in query
        return [
            {
                "content": "关键词研究是内容选题的第一步,先找词再定题。",
                "title": "关键词研究",
                "source": "keyword-research.md",
                "doc_id": 1,
                "score": 0.92,
            }
        ]


def _install_rag(monkeypatch, service) -> None:
    monkeypatch.setattr("app.graph.get_knowledge_service", lambda: service)


def test_draft_injects_rag_context(monkeypatch) -> None:
    _install_rag(monkeypatch, FakeRagService())
    wrapper = install_fake_model(monkeypatch, FakeWrapper(scores=(0.9,)))
    config = _new_config()
    _run(_start_state(), config)
    _run(Command(resume={"action": "approve"}), config)
    draft_prompt = next(p for node, p in wrapper.prompts if node == "draft_section")
    assert "知识库参考资料" in draft_prompt
    assert "关键词研究是内容选题的第一步" in draft_prompt
    final = graph.get_state(config).values
    assert final["rag_sources"][0]["title"] == "关键词研究"


def test_retrieve_failure_degrades_gracefully(monkeypatch) -> None:
    """知识库故障不能阻塞生成主流程：降级为无检索上下文继续写。"""

    class BoomService:
        enabled = True

        def search(self, query: str, k: int = 4) -> list[dict]:
            raise RuntimeError("vector store down")

    _install_rag(monkeypatch, BoomService())
    wrapper = install_fake_model(monkeypatch, FakeWrapper(scores=(0.9,)))
    config = _new_config()
    _run(_start_state(), config)
    _run(Command(resume={"action": "approve"}), config)
    final = graph.get_state(config).values
    assert final["rag_sources"] == []
    assert final["article"] == ARTICLE  # 无重写发生
    draft_prompt = next(p for node, p in wrapper.prompts if node == "draft_section")
    assert "知识库参考资料" not in draft_prompt


def test_score_prompt_carries_article_and_outline() -> None:
    prompt = build_seo_score_prompt("主题", "关键词", "标题", ["一", "二"], "正文内容")
    assert "正文内容" in prompt
    assert "1. 一" in prompt
