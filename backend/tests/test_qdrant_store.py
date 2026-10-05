"""Qdrant 向量库往返测试：本地嵌入式文件模式 + 假 embedding；真实实例需显式开 QDRANT_SMOKE_URL。"""

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

pytest.importorskip("langchain_qdrant", reason="需要 uv sync --extra qdrant")

DIM = 64

DOC = (
    "长尾关键词的搜索意图决定内容结构。"
    "Core Web Vitals 指标包含 LCP、CLS 与 INP。"
)


class FakeEmbeddings(Embeddings):
    """确定性词袋向量：重叠越多相似度越高。"""

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
    monkeypatch.setenv("VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_DIR", str(tmp_path / "qdrant"))
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.delenv("QDRANT_COLLECTION", raising=False)
    return tmp_path / "qdrant"


def _service() -> KnowledgeService:
    store, kind = _build_vector_store(FakeEmbeddings())
    return KnowledgeService(FakeEmbeddings(), store, store_kind=kind)


def test_qdrant_round_trip(qdrant_env) -> None:
    service = _service()
    assert service.store_kind == "qdrant"

    result = service.ingest("SEO 基础", DOC, "seed.md")
    assert result["chunks"] >= 1

    hits = service.search("Core Web Vitals LCP", k=3)
    assert hits and hits[0]["title"] == "SEO 基础"
    assert "Core Web Vitals" in hits[0]["content"]
    assert hits[0]["doc_id"] == result["doc_id"]

    assert service.delete(result["doc_id"]) is True
    assert service.search("Core Web Vitals", k=3) == []


def test_qdrant_persists_across_service_instances(qdrant_env) -> None:
    service = _service()
    service.ingest("持久化文档", DOC, "persist.md")
    service._store.client.close()

    revived = _service()
    hits = revived.search("长尾关键词", k=3)
    assert hits and hits[0]["title"] == "持久化文档"


def test_qdrant_custom_collection(qdrant_env, monkeypatch) -> None:
    monkeypatch.setenv("QDRANT_COLLECTION", "custom_seo")
    store, _kind = _build_vector_store(FakeEmbeddings())
    try:
        assert store.collection_name == "custom_seo"
        assert store.client.collection_exists("custom_seo") is True
    finally:
        store.client.close()


def test_unknown_vector_store_raises(qdrant_env, monkeypatch) -> None:
    monkeypatch.setenv("VECTOR_STORE", "milvus")
    with pytest.raises(ValueError, match="未知的 VECTOR_STORE"):
        _build_vector_store(FakeEmbeddings())


def test_missing_optional_dependency_reports_actionably(qdrant_env, monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name in {"langchain_qdrant", "qdrant_client"}:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(RagNotConfiguredError, match="uv sync --extra qdrant"):
        _build_vector_store(FakeEmbeddings())


@pytest.mark.skipif(
    not os.environ.get("QDRANT_SMOKE_URL"),
    reason="需显式设置 QDRANT_SMOKE_URL（docker compose up -d qdrant 后指向 http://localhost:6333）",
)
def test_qdrant_server_mode(monkeypatch) -> None:
    """真实 Qdrant 实例：验证 QDRANT_URL 分支与 uuid5 点位删除在服务端同样可用。"""
    collection = f"smoke_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("VECTOR_STORE", "qdrant")
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
