"""选题研究：把模型输出规范化为可供后续写作使用的研究简报。"""

import json
import re
from collections.abc import Mapping
from typing import Any

from app.search.base import SearchProvider, SearchResult


RESEARCH_FIELDS = (
    "audience",
    "search_intent",
    "content_angles",
    "related_questions",
    "competitor_gaps",
    "recommended_title",
    "outline",
)


def collect_topic_sources(
    provider: SearchProvider, topic: str, keyword: str, *, max_sources: int = 8
) -> list[SearchResult]:
    """用不同研究意图检索主题，并按 URL 去重。"""
    subject = f"{topic} {keyword}".strip()
    queries = (
        f"{subject} 现状 趋势",
        f"{subject} 教程 常见问题",
        f"{subject} 对比 竞品",
    )
    results: list[SearchResult] = []
    seen_urls: set[str] = set()
    for query in queries:
        for item in provider.search(query, max_results=4):
            if item.url in seen_urls:
                continue
            seen_urls.add(item.url)
            results.append(item)
            if len(results) >= max_sources:
                return results
    return results


def build_research_prompt(
    topic: str, keyword: str, sources: list[SearchResult] | None = None
) -> str:
    keyword_line = f"目标关键词：{keyword}" if keyword else "未指定目标关键词"
    return f"""你是一名 SEO 内容策略师，请为以下主题做选题研究。

主题：{topic}
{keyword_line}

以下是实时搜索得到的参考资料。只能基于这些资料归纳事实；资料不足时明确说明，不要编造具体搜索量、排名、用户评论或外部来源。
{_format_sources(sources or [])}

只输出一个 JSON 对象，不要 Markdown 代码围栏，字段必须完整：
{{
  "audience": "核心受众及其痛点",
  "search_intent": "主要搜索意图",
  "content_angles": ["差异化内容角度"],
  "related_questions": ["用户可能继续搜索的问题"],
  "competitor_gaps": ["常见内容不足或可填补的空白"],
  "recommended_title": "推荐文章标题",
  "outline": ["文章小节标题"]
}}

要求：每个数组至少 1 项；content_angles、related_questions、competitor_gaps 各给出 3-5 项；outline 给出 4-8 个小节。"""


def _format_sources(sources: list[SearchResult]) -> str:
    if not sources:
        return "（没有检索到可用资料，请在结果中明确标记资料不足。）"
    chunks = []
    for index, source in enumerate(sources, start=1):
        content = source.content[:4000]
        published = f"；日期：{source.published_at}" if source.published_at else ""
        chunks.append(f"[来源 {index}] {source.title}\nURL：{source.url}{published}\n内容：{content}")
    return "\n\n".join(chunks)


def parse_research_result(raw: Any) -> dict[str, Any]:
    """解析并校验模型返回的研究 JSON，失败时给出可操作的错误。"""
    text = getattr(raw, "content", raw)
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip(), flags=re.IGNORECASE)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("选题研究结果不是有效 JSON") from exc
    if not isinstance(data, Mapping):
        raise ValueError("选题研究结果必须是 JSON 对象")

    result: dict[str, Any] = {}
    for field in RESEARCH_FIELDS:
        value = data.get(field)
        if field in {"audience", "search_intent", "recommended_title"}:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"选题研究结果缺少有效字段: {field}")
            result[field] = value.strip()
        else:
            if not isinstance(value, list) or not value or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                raise ValueError(f"选题研究结果缺少有效数组字段: {field}")
            result[field] = [item.strip() for item in value]
    return result
