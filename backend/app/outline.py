"""大纲生成与修订：prompt 构造与模型输出解析。"""

import json
import re
from collections.abc import Mapping
from typing import Any


def build_outline_prompt(topic: str, keyword: str) -> str:
    keyword_line = f"目标关键词：{keyword}" if keyword else "未指定目标关键词"
    return f"""你是一名 SEO 内容策略师，请为以下主题设计文章大纲。

主题：{topic}
{keyword_line}

只输出一个 JSON 对象，不要 Markdown 代码围栏，字段必须完整：
{{
  "title": "推荐文章标题（自然融入目标关键词）",
  "outline": ["文章小节标题"]
}}

要求：outline 给出 4-8 个小节，小节之间逻辑递进，覆盖主题的核心问题；不要输出 JSON 以外的任何内容。"""


def build_revise_prompt(topic: str, keyword: str, outline: list[str], instruction: str) -> str:
    keyword_line = f"目标关键词：{keyword}" if keyword else "未指定目标关键词"
    current = json.dumps(outline, ensure_ascii=False)
    return f"""你是一名 SEO 内容策略师，请按用户要求修订文章大纲。

主题：{topic}
{keyword_line}

当前大纲：
{current}

用户修订要求：{instruction}

只输出一个 JSON 对象，不要 Markdown 代码围栏，字段必须完整：
{{
  "title": "修订后的文章标题",
  "outline": ["修订后的小节标题"]
}}

要求：严格按照用户要求修改，未涉及的部分保持不变；outline 保持 3-10 个小节；不要输出 JSON 以外的任何内容。"""


def parse_outline_result(raw: Any) -> dict[str, Any]:
    """解析并校验模型返回的大纲 JSON，失败时给出可操作的错误。"""
    text = getattr(raw, "content", raw)
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip(), flags=re.IGNORECASE)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("大纲结果不是有效 JSON") from exc
    if not isinstance(data, Mapping):
        raise ValueError("大纲结果必须是 JSON 对象")

    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("大纲结果缺少有效字段: title")
    outline = data.get("outline")
    if not isinstance(outline, list) or not outline or not all(
        isinstance(item, str) and item.strip() for item in outline
    ):
        raise ValueError("大纲结果缺少有效数组字段: outline")
    return {"title": title.strip(), "outline": [item.strip() for item in outline]}
