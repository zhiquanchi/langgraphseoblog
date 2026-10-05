"""Embedding 模型构建:与 LLM 的环境变量回退路径同风格。

EMBEDDING_PROVIDER 未设置时返回 None,知识库服务整体降级关闭;
设置后走 OpenAI 兼容协议(OpenAI / 火山方舟 / 阿里云百炼均适用)。
"""

import os

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from app.dashscope import (
    DEFAULT_EMBEDDING_MODEL,
    MAX_EMBED_BATCH,
    PROVIDER_ALIASES,
    resolve_base_url,
)


def build_env_embeddings() -> Embeddings | None:
    """按 EMBEDDING_PROVIDER 构建 embedding 模型;未配置返回 None（RAG 关闭）。"""
    provider = os.environ.get("EMBEDDING_PROVIDER", "").strip().lower()
    if not provider:
        return None
    model = os.environ.get("EMBEDDING_MODEL", "")
    if provider == "openai":
        return OpenAIEmbeddings(
            model=model or "text-embedding-3-small",
            api_key=_require_env("OPENAI_API_KEY"),
        )
    if provider == "ark":
        return OpenAIEmbeddings(
            model=model or "doubao-embedding",
            api_key=_require_env("ARK_API_KEY"),
            base_url=_require_env("ARK_BASE_URL"),
        )
    if provider in PROVIDER_ALIASES:
        return OpenAIEmbeddings(
            model=model or DEFAULT_EMBEDDING_MODEL,
            api_key=_require_env("DASHSCOPE_API_KEY"),
            base_url=resolve_base_url(),
            # 默认 1000 条一批，百炼上限 10 条，整篇文档入库会直接 400
            chunk_size=MAX_EMBED_BATCH,
        )
    raise ValueError(f"未知的 EMBEDDING_PROVIDER: {provider}")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"环境变量 {name} 未设置")
    return value
