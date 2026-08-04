"""LLM 工厂测试：api_key 由调用方传入，后端不读取/不存储 Provider 密钥。"""

from uuid import uuid4

import pytest
from langchain_openai import ChatOpenAI

from app.db import SessionLocal
from app.llm.factory import _build_model, get_chat_model
from app.models import Provider


def test_build_model_uses_passed_api_key() -> None:
    provider = Provider(name="openai-test", type="openai", default_model="gpt-4o")
    model = _build_model(provider, api_key="sk-from-request")
    assert isinstance(model, ChatOpenAI)
    assert model.openai_api_key.get_secret_value() == "sk-from-request"


def test_get_chat_model_requires_api_key() -> None:
    with SessionLocal() as session:
        provider = Provider(
            name=f"factory-no-key-{uuid4().hex[:8]}", type="openai", default_model="gpt-4o"
        )
        session.add(provider)
        session.commit()
        provider_id = provider.id

    with pytest.raises(ValueError, match="未配置 API Key"):
        get_chat_model(provider_id)


def test_get_chat_model_caches_per_api_key() -> None:
    with SessionLocal() as session:
        provider = Provider(
            name=f"factory-cache-{uuid4().hex[:8]}", type="openai", default_model="gpt-4o"
        )
        session.add(provider)
        session.commit()
        provider_id = provider.id

    first = get_chat_model(provider_id, api_key="sk-key-a")
    again = get_chat_model(provider_id, api_key="sk-key-a")
    other = get_chat_model(provider_id, api_key="sk-key-b")

    assert first is again
    assert first is not other
