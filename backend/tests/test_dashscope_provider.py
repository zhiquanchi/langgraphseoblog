"""阿里云百炼（DashScope）接入：Provider 构建、环境变量回退、embedding 分批上限与模型目录。"""

import pytest
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.dashscope import DEFAULT_BASE_URL
from app.llm.factory import _build_model, build_env_chat_model
from app.llm.model_catalog import CATALOG
from app.models import Provider
from app.rag.embeddings import build_env_embeddings


def test_dashscope_provider_falls_back_to_default_base_url() -> None:
    provider = Provider(name="dashscope-default", type="dashscope", default_model="qwen-plus")
    model = _build_model(provider, api_key="sk-dash")
    assert isinstance(model, ChatOpenAI)
    assert model.openai_api_base == DEFAULT_BASE_URL


def test_dashscope_provider_honors_custom_base_url() -> None:
    url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    provider = Provider(
        name="dashscope-intl", type="dashscope", default_model="qwen-max", base_url=url
    )
    assert _build_model(provider, api_key="sk-dash").openai_api_base == url


def test_env_chat_model_builds_dashscope(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "aliyun")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dash")
    monkeypatch.delenv("DASHSCOPE_MODEL", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)

    model = build_env_chat_model()
    assert model.model_name == "qwen-plus"
    assert model.openai_api_base == DEFAULT_BASE_URL


def test_env_chat_model_dashscope_reads_overrides(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "dashscope")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dash")
    monkeypatch.setenv("DASHSCOPE_MODEL", "qwen3-max")
    monkeypatch.setenv("DASHSCOPE_BASE_URL", f"{DEFAULT_BASE_URL}/")

    model = build_env_chat_model()
    assert model.model_name == "qwen3-max"
    assert model.openai_api_base == DEFAULT_BASE_URL


def test_env_embeddings_batches_to_provider_limit(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "dashscope")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dash")
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)

    embeddings = build_env_embeddings()
    assert isinstance(embeddings, OpenAIEmbeddings)
    assert embeddings.model == "text-embedding-v4"
    assert embeddings.openai_api_base == DEFAULT_BASE_URL
    # 百炼单次请求上限 10 条，langchain 默认 1000 会整批 400
    assert embeddings.chunk_size == 10


def test_embeddings_reject_missing_dashscope_key(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "bailian")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
        build_env_embeddings()


def test_dashscope_model_catalog_registered() -> None:
    catalog = CATALOG["dashscope"]
    assert catalog.models_url == f"{DEFAULT_BASE_URL}/models"
    assert catalog.label == "阿里云百炼 (DashScope)"
