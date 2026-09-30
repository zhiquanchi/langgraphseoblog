"""SEO 质量评估与重写：prompt 构造与模型输出解析。

评分节点输出 JSON（score + suggestions），重写节点按建议修订全文；
score 与 suggestions 驱动图的条件边：评分不足且未超重写上限时回到
seo_optimize 节点循环重写。
"""

import json
import re
from collections.abc import Mapping
from typing import Any


def _outline_block(outline: list[str]) -> str:
    return "\n".join(f"{i}. {section}" for i, section in enumerate(outline, start=1))


def build_seo_score_prompt(
    topic: str, keyword: str, title: str, outline: list[str], article: str
) -> str:
    keyword_line = f"目标关键词：{keyword}" if keyword else "未指定目标关键词"
    return f"""你是一名严格的 SEO 内容审核员，请对以下博客文章做质量评分。

主题：{topic}
{keyword_line}
文章标题（H1）：{title}
约定大纲：
{_outline_block(outline)}

待评审文章：
{article}

评分维度：关键词是否自然融入标题与小节；小节是否覆盖约定大纲；内容是否详实、
有具体做法或示例而非空泛表述；结构是否符合 Markdown 规范（H1/H2 层级清晰）。

只输出一个 JSON 对象，不要 Markdown 代码围栏：
{{
  "score": 0.0 到 1.0 之间的数字，
  "suggestions": ["不及格维度对应的具体修改建议，按重要性排序，最多 5 条；达标时为空数组"]
}}

不要输出 JSON 以外的任何内容。"""


def build_seo_rewrite_prompt(
    topic: str,
    keyword: str,
    title: str,
    outline: list[str],
    article: str,
    suggestions: list[str],
) -> str:
    keyword_section = f"目标关键词：{keyword}\n" if keyword else ""
    suggestion_block = "\n".join(f"- {item}" for item in suggestions)
    return f"""请按审核意见修订以下博客文章。

主题：{topic}
{keyword_section}文章标题（H1）：{title}
约定大纲：
{_outline_block(outline)}

审核意见（必须逐条落实）：
{suggestion_block}

原文章：
{article}

要求：保持原文章的主题与结构，仅按审核意见修改与补强；Markdown 格式；
输出修订后的完整文章正文，不要输出任何解释。"""


def parse_score_result(raw: Any) -> dict[str, Any]:
    """解析并校验评分 JSON；score 收敛到 [0, 1]，失败时给出可操作的错误。"""
    text = getattr(raw, "content", raw)
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip(), flags=re.IGNORECASE)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("SEO 评分结果不是有效 JSON") from exc
    if not isinstance(data, Mapping):
        raise ValueError("SEO 评分结果必须是 JSON 对象")

    score = data.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise ValueError("SEO 评分结果缺少有效字段: score")
    suggestions = data.get("suggestions", [])
    if not isinstance(suggestions, list) or not all(
        isinstance(item, str) and item.strip() for item in suggestions
    ):
        raise ValueError("SEO 评分结果缺少有效数组字段: suggestions")
    return {
        "score": round(min(max(float(score), 0.0), 1.0), 4),
        "suggestions": [item.strip() for item in suggestions if item.strip()][:5],
    }
