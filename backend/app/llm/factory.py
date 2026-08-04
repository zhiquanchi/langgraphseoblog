"""LLM 模型工厂:按数据库 Provider 配置 + 请求级 api_key 构建 ChatModel,带热更新缓存;无动态配置时回退环境变量。"""

import hashlib
import os
from datetime import datetime

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.db import SessionLocal
from app.models import Provider

# 模型实例缓存: (provider_id, model, api_key_hash) -> (updated_at, model)
# api_key 由前端本地保存、随请求传入,仅以哈希参与缓存键,避免明文留存内存
_cache: dict[tuple[int, str | None, str], tuple[datetime, BaseChatModel]] = {}


def get_chat_model(
    provider_id: int, model: str | None = None, api_key: str | None = None
) -> BaseChatModel:
    """按 provider_id 从数据库读取配置,结合请求携带的 api_key 构建/复用 ChatModel。

    model 可选：显式传入时覆盖该 provider 的 default_model。
    api_key 必须由调用方提供（前端本地保存），后端不持久化；缺失时抛 ValueError。
    """
    with SessionLocal() as session:
        provider = session.get(Provider, provider_id)
        if provider is None:
            raise ValueError(f"Provider {provider_id} 不存在")
        if not api_key:
            raise ValueError(f"Provider {provider_id} 未配置 API Key")

        cache_key = (provider_id, model, _hash_key(api_key))
        cached = _cache.get(cache_key)
        if cached is not None and cached[0] == provider.updated_at:
            return cached[1]

        model_instance = _build_model(provider, model, api_key)
        _cache[cache_key] = (provider.updated_at, model_instance)
        return model_instance


def _hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


def _build_model(
    provider: Provider, model: str | None = None, api_key: str | None = None
) -> BaseChatModel:
    model_name = model or provider.default_model
    if provider.type == "openai":
        return ChatOpenAI(model=model_name, api_key=api_key)
    if provider.type == "anthropic":
        return ChatAnthropic(model=model_name, api_key=api_key)
    if provider.type in ("ark", "openai-compatible"):
        if not provider.base_url:
            raise ValueError(f"Provider {provider.id} 类型 {provider.type} 必须提供 base_url")
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=provider.base_url,
        )
    raise ValueError(f"Provider {provider.id} 类型 {provider.type} 不受支持")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"环境变量 {name} 未设置")
    return value


def build_env_chat_model() -> BaseChatModel:
    """环境变量回退路径:LLM_PROVIDER 指定提供商,配合 *_API_KEY / *_MODEL 构建模型。"""
    provider = os.environ.get("LLM_PROVIDER", "openai").strip().lower()

    if provider == "openai":
        return ChatOpenAI(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=_require_env("OPENAI_API_KEY"),
        )
    if provider == "anthropic":
        return ChatAnthropic(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
            api_key=_require_env("ANTHROPIC_API_KEY"),
        )
    if provider == "ark":
        return ChatOpenAI(
            model=os.environ.get("ARK_MODEL", "doubao-seed-1-6-250615"),
            api_key=_require_env("ARK_API_KEY"),
            base_url=_require_env("ARK_BASE_URL"),
        )
    raise ValueError(f"未知的 LLM_PROVIDER: {provider}")
