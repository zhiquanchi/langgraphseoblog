"""Qdrant 特有行为:自定义集合、依赖缺失指引、服务端冒烟(需显式开 QDRANT_SMOKE_URL)。

入库/检索/删除/重建/持久化等通用往返场景已并入 test_rag.py(服务层现唯一使用 Qdrant)。
"""

import math
import os
import re
import uuid

import pytest
from langchain_core.embeddings import Embeddings

from app.rag.service import (
    KnowledgeService,
    RagNotConfiguredError,
    _build_vector_store,
)

DIM = 64

DOC = (
    "长尾关键词的搜索意图决定内容结构。"
    "Core Web Vitals 指标包含 LCP、CLS 与 INP。"
)


class FakeEmbeddings(Embeddings):
    """确定性词袋向量:重叠越多相似度越高。"""

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * DIM
        for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", text.lower()):
            vec[hash(token) % DIM] += 1.0
        norm = math.sqrt(sum(value * value for value in vec)) or 1.0
        return [value / norm for value in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


@pytest.fixture()
def qdrant_env(monkeypatch, tmp_path):
    monkeypatch.setenv("QDRANT_DIR", str(tmp_path / "qdrant"))
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.delenv("QDRANT_COLLECTION", raising=False)
    return tmp_path / "qdrant"


def _service() -> KnowledgeService:
    store, kind = _build_vector_store(FakeEmbeddings())
    return KnowledgeService(FakeEmbeddings(), store, store_kind=kind)


def test_qdrant_local_mode_store_and_round_trip(qdrant_env) -> None:
    service = _service()
    assert service.store_kind == "qdrant"

    result = service.ingest("SEO 基础", DOC, "seed.md")
    hits = service.search("Core Web Vitals LCP", k=3)
    assert hits and hits[0]["title"] == "SEO 基础"
    assert service.delete(result["doc_id"]) is True
    assert service.search("Core Web Vitals", k=3) == []


def test_qdrant_custom_collection(qdrant_env, monkeypatch) -> None:
    monkeypatch.setenv("QDRANT_COLLECTION", "custom_seo")
    store, _kind = _build_vector_store(FakeEmbeddings())
    try:
        assert store.collection_name == "custom_seo"
        assert store.client.collection_exists("custom_seo") is True
    finally:
        store.client.close()


def test_missing_dependency_reports_actionably(qdrant_env, monkeypatch) -> None:
    """langchain-qdrant 已是主依赖:仍要在环境损坏时给出可执行指引(uv sync)。"""
    import builtins

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name in {"langchain_qdrant", "qdrant_client"}:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(RagNotConfiguredError, match="uv sync"):
        _build_vector_store(FakeEmbeddings())


@pytest.mark.skipif(
    not os.environ.get("QDRANT_SMOKE_URL"),
    reason="需显式设置 QDRANT_SMOKE_URL（docker compose up -d qdrant 后指向 http://localhost:6333）",
)
def test_qdrant_server_mode(monkeypatch) -> None:
    """真实 Qdrant 实例:验证 QDRANT_URL 分支与 uuid5 点位删除在服务端同样可用。"""
    collection = f"smoke_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("QDRANT_URL", os.environ["QDRANT_SMOKE_URL"])
    monkeypatch.setenv("QDRANT_COLLECTION", collection)

    service = _service()
    try:
        result = service.ingest("服务端模式", DOC, "server.md")
        hits = service.search("Core Web Vitals", k=3)
        assert hits and hits[0]["title"] == "服务端模式"
        assert service.delete(result["doc_id"]) is True
        assert service.search("Core Web Vitals", k=3) == []
    finally:
        service._store.client.delete_collection(collection)
        service._store.client.close()
