"""故障自动切换：FallbackChatModel 自封装降级。

按候选链顺序尝试模型调用，可降级异常（认证失败 / 限流 / 超时 / 5xx）自动切换
到下一个候选，全链失败抛出 AllProvidersFailedError；每次尝试写入调用统计并记录
failover_from。流式模式下仅允许首 token 产生前的失败触发降级。
"""

import asyncio
import queue
import threading
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any

from langchain_core import exceptions as _lc_exceptions
from langchain_core.language_models import BaseChatModel

from app.db import SessionLocal
from app.llm import stats
from app.llm.factory import build_env_chat_model, get_chat_model
from app.models import Provider
from app.llm.resolver import resolve_provider_ids

Candidate = tuple[int | None, str, str, BaseChatModel]


class AllProvidersFailedError(Exception):
    """全部候选 provider 均调用失败。"""

    def __init__(self, failures: list[tuple[int | None, str]]) -> None:
        self.failures = failures
        summaries = ", ".join(
            f"{provider_id}: {stats.mask_sensitive(summary)}"
            if provider_id is not None
            else f"env: {stats.mask_sensitive(summary)}"
            for provider_id, summary in failures
        )
        super().__init__(f"所有 Provider 均调用失败: [{summaries}]")


def is_failover_eligible(exc: Exception) -> bool:
    """判定异常是否可触发降级：认证失败、限流、超时、5xx；其余（如 4xx 业务错误）不可降级。"""
    for name in ("AuthenticationError", "RateLimitError"):
        cls = getattr(_lc_exceptions, name, None)
        if cls is not None and isinstance(exc, cls):
            return True
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = str(current).lower()
        if "timeout" in message or "timed out" in message:
            return True
        status = _extract_status_code(current)
        if status is not None:
            return status in (401, 403, 429) or status >= 500
        current = current.__cause__
    return False


class FallbackChatModel:
    """按序尝试候选模型的降级封装。"""

    def __init__(self, candidates: list[Candidate]) -> None:
        self._candidates = candidates
        self._last_used: tuple[int | None, str, str] | None = None

    @property
    def last_used(self) -> tuple[int | None, str, str] | None:
        """最近一次成功调用的 (provider_id, provider_name, model)。"""
        return self._last_used

    def invoke(
        self,
        input: Any,
        *,
        node: str | None = None,
        thread_id: str | None = None,
    ) -> str:
        """按序尝试；可降级异常切换候选，不可降级异常立即抛出，全链失败抛 AllProvidersFailedError。"""
        failures: list[tuple[int | None, str]] = []
        for provider_id, provider_name, model_name, model in self._candidates:
            failover_from = _failed_ids(failures)
            start = time.monotonic()
            try:
                result = model.invoke(input)
            except Exception as exc:
                stats.record_llm_call(
                    provider_id=provider_id,
                    provider_name=provider_name,
                    model=model_name,
                    node=node,
                    thread_id=thread_id,
                    latency_ms=_elapsed_ms(start),
                    success=False,
                    error=_summarize(exc),
                    failover_from=failover_from,
                )
                if is_failover_eligible(exc):
                    failures.append((provider_id, _summarize(exc)))
                    continue
                raise
            prompt, completion, total = stats.provider_tokens_from_usage(
                getattr(result, "usage_metadata", None)
            )
            stats.record_llm_call(
                provider_id=provider_id,
                provider_name=provider_name,
                model=model_name,
                node=node,
                thread_id=thread_id,
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
                latency_ms=_elapsed_ms(start),
                success=True,
                failover_from=failover_from,
            )
            self._last_used = (provider_id, provider_name, model_name)
            return _content_text(result)
        raise AllProvidersFailedError(failures)

    def astream(
        self,
        input: Any,
        *,
        node: str | None = None,
        thread_id: str | None = None,
    ) -> Iterator[str]:
        """流式；仅首 token 产生前的可降级失败触发切换，之后错误直接抛出。"""
        failures: list[tuple[int | None, str]] = []
        for provider_id, provider_name, model_name, model in self._candidates:
            failover_from = _failed_ids(failures)
            start = time.monotonic()
            emitted: list[str] = []
            last_chunk: Any = None
            try:
                for chunk in self._iter_chunks(model.astream(input)):
                    last_chunk = chunk
                    text = _content_text(chunk)
                    emitted.append(text)
                    yield text
            except Exception as exc:
                stats.record_llm_call(
                    provider_id=provider_id,
                    provider_name=provider_name,
                    model=model_name,
                    node=node,
                    thread_id=thread_id,
                    latency_ms=_elapsed_ms(start),
                    success=False,
                    error=_summarize(exc),
                    failover_from=failover_from,
                )
                if emitted or not is_failover_eligible(exc):
                    raise
                failures.append((provider_id, _summarize(exc)))
                continue
            prompt, completion, total = stats.provider_tokens_from_usage(
                getattr(last_chunk, "usage_metadata", None)
            )
            stats.record_llm_call(
                provider_id=provider_id,
                provider_name=provider_name,
                model=model_name,
                node=node,
                thread_id=thread_id,
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
                latency_ms=_elapsed_ms(start),
                success=True,
                failover_from=failover_from,
            )
            self._last_used = (provider_id, provider_name, model_name)
            return
        raise AllProvidersFailedError(failures)

    def _iter_chunks(self, stream: Any) -> Iterator[Any]:
        """统一底层流为 chunk 迭代器；异步流由后台线程驱动，异常原样上抛。"""
        if isinstance(stream, AsyncIterator):
            yield from _drain_async_stream(stream)
        else:
            yield from stream


def _drain_async_stream(stream: AsyncIterator[Any]) -> Iterator[Any]:
    """在独立事件循环中消费异步流，经线程安全队列回传 chunk/异常/结束。"""
    results: queue.Queue[tuple[str, Any]] = queue.Queue()
    stop = threading.Event()

    def runner() -> None:
        async def consume() -> None:
            try:
                async for chunk in stream:
                    results.put(("chunk", chunk))
                    if stop.is_set():
                        break
            except BaseException as exc:  # noqa: BLE001
                try:
                    await stream.aclose()
                except Exception:  # noqa: BLE001
                    pass
                results.put(("error", exc))
            else:
                results.put(("end", None))

        try:
            asyncio.run(consume())
        except BaseException as exc:  # noqa: BLE001
            results.put(("error", exc))

    thread = threading.Thread(target=runner, name="fallback-astream", daemon=True)
    thread.start()
    try:
        while True:
            kind, payload = results.get()
            if kind == "chunk":
                yield payload
            elif kind == "error":
                raise payload
            else:
                thread.join()
                return
    finally:
        stop.set()


def build_fallback_model(
    node: str | None,
    request_provider: str | None,
    model_override: str | None = None,
    provider_api_keys: dict[int, str] | None = None,
) -> FallbackChatModel:
    """解析候选链并构建 FallbackChatModel；空链回退环境变量模式。

    model_override 可选：显式传入时覆盖候选 provider 的 default_model。
    provider_api_keys 为前端本地保存的密钥映射（provider_id -> api_key），
    仅用于本次构建、不持久化；链中缺 key 的候选被跳过，显式指定的 provider
    缺 key 时直接报错，空链回退环境变量模式。
    """
    provider_api_keys = provider_api_keys or {}
    provider_ids = resolve_provider_ids(node, request_provider)
    if not provider_ids:
        env_model = build_env_chat_model()
        model_name = model_override or getattr(env_model, "model_name", None) or "env"
        return FallbackChatModel([(None, "env", model_name, env_model)])
    candidates: list[Candidate] = []
    with SessionLocal() as session:
        for index, provider_id in enumerate(provider_ids):
            provider = session.get(Provider, provider_id)
            name = provider.name if provider is not None else str(provider_id)
            default_model = provider.default_model if provider is not None else "unknown"
            api_key = provider_api_keys.get(provider_id)
            if not api_key:
                if index == 0 and request_provider is not None:
                    raise ValueError(f"Provider {name} 未配置 API Key，请在本地填写后重试")
                continue
            candidates.append(
                (
                    provider_id,
                    name,
                    model_override or default_model,
                    get_chat_model(provider_id, model_override, api_key),
                )
            )
    if not candidates:
        env_model = build_env_chat_model()
        model_name = model_override or getattr(env_model, "model_name", None) or "env"
        return FallbackChatModel([(None, "env", model_name, env_model)])
    return FallbackChatModel(candidates)


def _content_text(chunk: Any) -> str:
    content = getattr(chunk, "content", chunk)
    return content if isinstance(content, str) else str(content)


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _summarize(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _failed_ids(failures: list[tuple[int | None, str]]) -> list[int]:
    return [provider_id for provider_id, _ in failures if provider_id is not None]


def _extract_status_code(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if isinstance(status, int):
        return status
    return None
