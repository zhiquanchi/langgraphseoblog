from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from app.api.routes import research_topic
from app.api.schemas import ResearchRequest
from app.search.base import SearchResult


@dataclass
class FakeResearchModel:
    last_used: tuple[int | None, str, str] = (None, "test-provider", "test-model")

    def invoke(self, prompt: str, *, node: str | None = None) -> str:
        assert node == "research"
        assert "LangGraph" in prompt
        return """{
          "audience": "Python 后端开发者",
          "search_intent": "学习如何构建生产级 LangGraph 工作流",
          "content_angles": ["状态设计", "节点编排"],
          "related_questions": ["如何处理中断？"],
          "competitor_gaps": ["缺少可运行的断点续跑示例"],
          "recommended_title": "LangGraph 最佳实践：构建可恢复的工作流",
          "outline": ["核心概念", "断点续跑", "实践建议"]
        }"""


class FakeSearchProvider:
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        return [SearchResult("参考资料", "https://example.com/source", "来源内容")]


def test_research_topic_returns_structured_brief(monkeypatch) -> None:
    monkeypatch.setattr("app.api.routes.build_fallback_model", lambda *args, **kwargs: FakeResearchModel())
    monkeypatch.setattr("app.api.routes.get_search_provider", lambda *_args: FakeSearchProvider())

    response = research_topic(
        ResearchRequest(topic="LangGraph 最佳实践", keyword="langgraph tutorial")
    )

    assert response.topic == "LangGraph 最佳实践"
    assert response.keyword == "langgraph tutorial"
    assert response.audience == "Python 后端开发者"
    assert response.outline == ["核心概念", "断点续跑", "实践建议"]
    assert response.provider_name == "test-provider"
    assert response.model == "test-model"
    assert response.sources[0].url == "https://example.com/source"


def test_research_topic_rejects_blank_topic() -> None:
    with pytest.raises(ValidationError):
        ResearchRequest(topic="   ")
