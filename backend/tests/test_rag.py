"""RAG 知识库服务与 API 测试：假 embedding 驱动，覆盖入库/检索/删除/重建/降级。"""

import math
import re

import pytest
from fastapi.testclient import TestClient
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

from app.db import SessionLocal
from app.main import app
from app.models import KnowledgeChunk, KnowledgeDoc
from app.rag.service import (
    RagNotConfiguredError,
    KnowledgeService,
    iter_corpus_documents,
)

DIM = 64


class FakeEmbeddings(Embeddings):
    """确定性词袋向量：中文按字、英文按词切分，重叠越多相似度越高。"""

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


def build_service() -> KnowledgeService:
    embeddings = FakeEmbeddings()
    return KnowledgeService(
        embeddings, InMemoryVectorStore(embedding=embeddings), store_kind="memory"
    )


@pytest.fixture()
def rag_service():
    """干净的知识库服务：每用例重建索引实例，结束后清空权威表。"""
    service = build_service()
    yield service
    with SessionLocal() as session:
        session.query(KnowledgeChunk).delete(synchronize_session=False)
        session.query(KnowledgeDoc).delete(synchronize_session=False)
        session.commit()


@pytest.fixture()
def rag_client(monkeypatch, rag_service):
    monkeypatch.setattr("app.api.routes.get_knowledge_service", lambda: rag_service)
    return TestClient(app)


DOC_A = (
    "关键词研究是 SEO 内容的第一步。先找词，再定题，最后写文。"
    "长尾关键词由多个词组成，搜索量低但意图明确，新站优先做长尾词。"
) * 6  # 撑起多个分块
DOC_B = (
    "Core Web Vitals 包含 LCP、CLS、INP 三项指标。LCP 衡量最大内容绘制时间，"
    "CLS 衡量布局偏移。图片懒加载与压缩可以改善核心指标。"
) * 6


def test_ingest_then_search_ranks_relevant_doc_first(rag_service) -> None:
    rag_service.ingest("关键词研究方法", DOC_A, "keyword.md")
    rag_service.ingest("核心指标", DOC_B, "vitals.md")

    hits = rag_service.search("长尾关键词怎么选", k=2)
    assert hits, "应至少命中一个分块"
    assert hits[0]["title"] == "关键词研究方法"
    assert hits[0]["source"] == "keyword.md"
    assert hits[0]["doc_id"] is not None
    assert 0.0 <= hits[0]["score"] <= 1.0
    assert rag_service.chunk_count() > 0


def test_delete_removes_doc_and_chunks(rag_service) -> None:
    result = rag_service.ingest("待删除文档", DOC_A, "tmp.md")
    doc_id = result["doc_id"]
    assert rag_service.delete(doc_id) is True
    assert rag_service.delete(doc_id) is False  # 二次删除返回 False
    assert rag_service.search("长尾关键词", k=5) == []
    with SessionLocal() as session:
        assert session.get(KnowledgeDoc, doc_id) is None
        assert (
            session.query(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc_id).count() == 0
        )


def test_memory_index_rebuilds_from_sqlite(rag_service) -> None:
    """权威数据在 SQLite：新服务实例（模拟重启）首次检索时自动重建索引。"""
    rag_service.ingest("重启前的文档", DOC_A, "persist.md")

    revived = build_service()  # 新实例 = 空索引，但共享同一个测试数据库
    hits = revived.search("长尾关键词", k=3)
    assert hits
    assert hits[0]["title"] == "重启前的文档"


def test_search_disabled_service_raises(rag_service) -> None:
    disabled = KnowledgeService(None, None, store_kind="disabled")
    assert disabled.enabled is False
    with pytest.raises(RagNotConfiguredError):
        disabled.search("任意")


def test_iter_corpus_documents_parses_h1(tmp_path) -> None:
    (tmp_path / "a.md").write_text("# 标题甲\n\n正文内容。", encoding="utf-8")
    (tmp_path / "b.md").write_text("无标题正文。", encoding="utf-8")
    docs = list(iter_corpus_documents(tmp_path))
    assert docs[0] == {"title": "标题甲", "content": "正文内容。", "source": "a.md"}
    assert docs[1]["title"] == "b"  # 无 H1 时回退文件名


def test_rag_api_crud_and_search(rag_client, rag_service) -> None:
    status = rag_client.get("/api/rag/status")
    assert status.status_code == 200
    assert status.json() == {
        "enabled": True,
        "vector_store": "memory",
        "doc_count": 0,
        "chunk_count": 0,
    }

    created = rag_client.post(
        "/api/rag/documents",
        json={"title": "接口创建的文档", "content": DOC_B, "source": "api.md"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["chunks"] >= 1

    listed = rag_client.get("/api/rag/documents")
    assert listed.status_code == 200
    assert [doc["title"] for doc in listed.json()] == ["接口创建的文档"]

    searched = rag_client.post(
        "/api/rag/search", json={"query": "LCP CLS 核心指标", "k": 3}
    )
    assert searched.status_code == 200
    hits = searched.json()["hits"]
    assert hits and "Core Web Vitals" in hits[0]["content"]

    deleted = rag_client.delete(f"/api/rag/documents/{body['doc_id']}")
    assert deleted.status_code == 204
    assert rag_client.delete(f"/api/rag/documents/{body['doc_id']}").status_code == 404


def test_rag_api_seed_is_idempotent(rag_client, monkeypatch) -> None:
    corpus = [
        {"title": "语料一", "content": DOC_A, "source": "c1.md"},
        {"title": "语料二", "content": DOC_B, "source": "c2.md"},
    ]
    monkeypatch.setattr("app.api.routes.iter_corpus_documents", lambda: iter(corpus))

    first = rag_client.post("/api/rag/seed")
    assert first.status_code == 200
    assert len(first.json()["ingested"]) == 2
    assert first.json()["skipped"] == []

    second = rag_client.post("/api/rag/seed")
    assert second.status_code == 200
    assert second.json()["ingested"] == []
    assert second.json()["skipped"] == ["c1.md", "c2.md"]


def test_rag_api_unconfigured_returns_503(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.get_knowledge_service",
        lambda: KnowledgeService(None, None, store_kind="disabled"),
    )
    client = TestClient(app)
    assert client.get("/api/rag/status").json()["enabled"] is False
    assert client.post("/api/rag/search", json={"query": "x"}).status_code == 503
    assert (
        client.post(
            "/api/rag/documents", json={"title": "t", "content": "c"}
        ).status_code
        == 503
    )


def test_rag_api_empty_content_rejected(rag_client) -> None:
    resp = rag_client.post(
        "/api/rag/documents",
        json={"title": "空文档", "content": "\n\n  \n"},
    )
    assert resp.status_code == 400
