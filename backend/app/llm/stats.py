"""LLM 调用统计记录：写入 llm_calls 表，清洗敏感信息，提取 usage token。"""

import json
import re
from collections.abc import Mapping

from app.db import SessionLocal
from app.models import LLMCall

_MASK_RE = re.compile(r"\S{16,}")


def mask_sensitive(text: str) -> str:
    """清洗可能含 API key 的文本：长度 >= 16 的连续非空白 token 替换为掩码。"""
    if not text:
        return text
    return _MASK_RE.sub("***", text)


def record_llm_call(
    *,
    provider_id: int | None,
    provider_name: str,
    model: str,
    node: str | None = None,
    thread_id: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    latency_ms: int = 0,
    success: bool,
    error: str | None = None,
    failover_from: list[int] | None = None,
) -> None:
    """将一次 LLM 调用写入 llm_calls 表（独立 session，提交后关闭）。"""
    call = LLMCall(
        provider_id=provider_id,
        provider_name=provider_name,
        model=model,
        node=node,
        thread_id=thread_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        success=success,
        error=mask_sensitive(error) if error is not None else None,
        failover_from=json.dumps(failover_from) if failover_from is not None else "[]",
    )
    with SessionLocal() as session:
        session.add(call)
        session.commit()


def provider_tokens_from_usage(usage) -> tuple[int, int, int]:
    """从 langchain 响应的 usage_metadata（或 usage）提取 (prompt, completion, total)。

    usage_metadata 使用 input_tokens/output_tokens/total_tokens；
    兼容 OpenAI 风格 prompt_tokens/completion_tokens/total_tokens；
    任一缺失记 0，total 缺失时由 prompt + completion 补齐。
    """
    if not isinstance(usage, Mapping):
        return (0, 0, 0)

    prompt = _token_value(usage, "prompt_tokens", "input_tokens")
    completion = _token_value(usage, "completion_tokens", "output_tokens")
    total = _token_value(usage, "total_tokens")
    if total == 0 and prompt and completion:
        total = prompt + completion
    return (prompt, completion, total)


def _token_value(usage: Mapping, *keys: str) -> int:
    for key in keys:
        value = usage.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0
