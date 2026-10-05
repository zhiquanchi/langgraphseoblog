"""知识库服务:SQLite 存权威文档与分块,向量索引按需构建——索引只是缓存。

- 默认 InMemoryVectorStore（零额外依赖）;VECTOR_STORE=chroma / qdrant 时切换对应持久化实现;
- memory 索引重启即失,首次检索时自动从 knowledge_chunks 表重建;
- EMBEDDING_PROVIDER 未配置时服务整体降级:检索节点跳过、管理 API 返回 503;
- 切块用 RecursiveCharacterTextSplitter(800/120),入库保留 title/source 元数据做引用溯源。
"""

import os
import threading
import uuid
from collections.abc import Iterator
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import KnowledgeChunk, KnowledgeDoc
from app.rag.embeddings import build_env_embeddings

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
RETRIEVE_TOP_K = 4
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _point_id(chunk_id: str) -> str:
    """分块主键 "{doc_id}:{seq}" 映射为点位 id;Qdrant 只接受 uint/UUID,故统一用 uuid5。"""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


class RagNotConfiguredError(Exception):
    """RAG 未就绪:embedding 未配置或向量库依赖缺失。"""


_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
)


class KnowledgeService:
    """文档入库 / 检索 / 删除;线程安全(索引变更持锁)。"""

    def __init__(
        self,
        embeddings: Embeddings | None,
        vector_store: InMemoryVectorStore | object,
        store_kind: str = "memory",
    ) -> None:
        self._embeddings = embeddings
        self._store = vector_store
        self._store_kind = store_kind
        self._lock = threading.Lock()
        self._rebuilt = False

    @property
    def enabled(self) -> bool:
        return self._embeddings is not None

    @property
    def store_kind(self) -> str:
        return self._store_kind

    def _require_ready(self) -> None:
        if not self.enabled:
            raise RagNotConfiguredError("未配置 EMBEDDING_PROVIDER,知识库功能不可用")

    def ingest(self, title: str, content: str, source: str = "") -> dict[str, int]:
        """切分入库:持久化 doc/chunk 到 SQLite,同时写入向量索引。"""
        self._require_ready()
        pieces = [piece.strip() for piece in _splitter.split_text(content) if piece.strip()]
        if not pieces:
            raise ValueError("文档内容为空,切分后没有可用分块")
        with self._lock, SessionLocal() as session:
            doc = KnowledgeDoc(title=title, source=source, content=content)
            session.add(doc)
            session.flush()  # 取回自增 id 再生成分块主键
            for seq, piece in enumerate(pieces):
                session.add(
                    KnowledgeChunk(
                        id=f"{doc.id}:{seq}", doc_id=doc.id, seq=seq, content=piece
                    )
                )
            self._store.add_documents(
                [
                    Document(
                        page_content=piece,
                        metadata={"doc_id": doc.id, "title": title, "source": source, "seq": seq},
                    )
                    for seq, piece in enumerate(pieces)
                ],
                ids=[_point_id(f"{doc.id}:{seq}") for seq in range(len(pieces))],
            )
            session.commit()
            return {"doc_id": doc.id, "chunks": len(pieces)}

    def delete(self, doc_id: int) -> bool:
        """删除文档:同时清掉 SQLite 分块与向量索引中的对应条目。"""
        with self._lock, SessionLocal() as session:
            doc = session.get(KnowledgeDoc, doc_id)
            if doc is None:
                return False
            chunk_ids = list(
                session.scalars(
                    select(KnowledgeChunk.id).where(KnowledgeChunk.doc_id == doc_id)
                )
            )
            session.query(KnowledgeChunk).where(
                KnowledgeChunk.doc_id == doc_id
            ).delete(synchronize_session=False)
            session.delete(doc)
            session.commit()
        if chunk_ids:
            with self._lock:
                self._store.delete([_point_id(chunk_id) for chunk_id in chunk_ids])
        return True

    def search(self, query: str, k: int = RETRIEVE_TOP_K) -> list[dict]:
        """语义检索,带引用溯源元数据;memory 索引为空时先从 SQLite 重建。"""
        self._require_ready()
        self._ensure_index()
        with self._lock:
            hits = self._store.similarity_search_with_score(query, k=k)
        return [
            {
                "content": doc.page_content,
                "title": doc.metadata.get("title", ""),
                "source": doc.metadata.get("source", ""),
                "doc_id": doc.metadata.get("doc_id"),
                "score": round(float(score), 4),
            }
            for doc, score in hits
        ]

    def list_docs(self) -> list[dict]:
        with SessionLocal() as session:
            rows = session.execute(
                select(
                    KnowledgeDoc.id,
                    KnowledgeDoc.title,
                    KnowledgeDoc.source,
                    KnowledgeDoc.created_at,
                    func.count(KnowledgeChunk.id).label("chunks"),
                )
                .outerjoin(KnowledgeChunk, KnowledgeChunk.doc_id == KnowledgeDoc.id)
                .group_by(KnowledgeDoc.id)
                .order_by(KnowledgeDoc.id)
            ).all()
            return [
                {
                    "id": row.id,
                    "title": row.title,
                    "source": row.source,
                    "chunks": row.chunks,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def chunk_count(self) -> int:
        with SessionLocal() as session:
            return int(session.scalar(select(func.count(KnowledgeChunk.id))) or 0)

    def _ensure_index(self) -> None:
        """memory 索引重启即失:首个检索请求触发一次从 knowledge_chunks 的重建。"""
        if self._rebuilt or self._store_kind != "memory":
            return
        with self._lock:
            if self._rebuilt:
                return
            with SessionLocal() as session:
                rows = list(
                    session.execute(
                        select(KnowledgeChunk, KnowledgeDoc.title, KnowledgeDoc.source)
                        .join(KnowledgeDoc, KnowledgeChunk.doc_id == KnowledgeDoc.id)
                        .order_by(KnowledgeChunk.id)
                    ).all()
                )
            # InMemoryVectorStore 的 store 为键值字典,可直接判空
            if rows and len(getattr(self._store, "store", {})) == 0:
                self._store.add_documents(
                    [
                        Document(
                            page_content=chunk.content,
                            metadata={
                                "doc_id": chunk.doc_id,
                                "title": title,
                                "source": source,
                                "seq": chunk.seq,
                            },
                        )
                        for chunk, title, source in rows
                    ],
                    ids=[_point_id(chunk.id) for chunk, _, _ in rows],
                )
            self._rebuilt = True


def _build_vector_store(embeddings: Embeddings) -> tuple[InMemoryVectorStore | object, str]:
    """按 VECTOR_STORE 选择向量库实现;chroma/qdrant 为可选依赖,缺失时给出安装指引。"""
    kind = os.environ.get("VECTOR_STORE", "memory").strip().lower()
    if kind == "memory":
        return InMemoryVectorStore(embedding=embeddings), "memory"
    if kind == "chroma":
        try:
            from langchain_chroma import Chroma
        except ImportError as exc:
            raise RagNotConfiguredError(
                "VECTOR_STORE=chroma 需要先安装可选依赖: uv sync --extra chroma"
            ) from exc
        persist_dir = os.environ.get("CHROMA_DIR", str(DATA_DIR / "chroma"))
        return (
            Chroma(
                collection_name="seo_knowledge",
                embedding_function=embeddings,
                persist_directory=persist_dir,
            ),
            "chroma",
        )
    if kind == "qdrant":
        return _build_qdrant_store(embeddings), "qdrant"
    raise ValueError(f"未知的 VECTOR_STORE: {kind}")


def _build_qdrant_store(embeddings: Embeddings) -> object:
    """Qdrant:配 QDRANT_URL 走服务端,否则用本地嵌入式目录（免起服务）。集合按维度自动建。"""
    try:
        from langchain_qdrant import QdrantVectorStore
        from qdrant_client import QdrantClient, models
    except ImportError as exc:
        raise RagNotConfiguredError(
            "VECTOR_STORE=qdrant 需要先安装可选依赖: uv sync --extra qdrant"
        ) from exc

    collection = os.environ.get("QDRANT_COLLECTION", "seo_knowledge")
    url = os.environ.get("QDRANT_URL", "").strip()
    if url:
        client = QdrantClient(url=url, api_key=os.environ.get("QDRANT_API_KEY") or None)
    else:
        local_dir = Path(os.environ.get("QDRANT_DIR", str(DATA_DIR / "qdrant")))
        local_dir.mkdir(parents=True, exist_ok=True)
        client = QdrantClient(path=str(local_dir))

    if not client.collection_exists(collection):
        size = len(embeddings.embed_query("dimension probe"))
        client.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(size=size, distance=models.Distance.COSINE),
        )
    return QdrantVectorStore(client=client, collection_name=collection, embedding=embeddings)


_service: KnowledgeService | None = None


def get_knowledge_service() -> KnowledgeService:
    """进程级单例;按环境变量构建 embedding 与向量库,失败提前暴露配置错误。"""
    global _service
    if _service is None:
        embeddings = build_env_embeddings()
        if embeddings is None:
            _service = KnowledgeService(None, None, store_kind="disabled")
        else:
            store, kind = _build_vector_store(embeddings)
            _service = KnowledgeService(embeddings, store, store_kind=kind)
    return _service


def reset_knowledge_service() -> None:
    """测试钩子:清空单例,便于注入假 embedding。"""
    global _service
    _service = None


def iter_corpus_documents(corpus_dir: str | Path | None = None) -> Iterator[dict]:
    """读取内置示例语料 backend/data/corpus/*.md,标题取首个 H1,缺省用文件名。"""
    base = (
        Path(corpus_dir)
        if corpus_dir is not None
        else Path(__file__).resolve().parents[2] / "data" / "corpus"
    )
    if not base.is_dir():
        return
    for path in sorted(base.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        title = path.stem
        if text.startswith("# "):
            heading, _, rest = text.partition("\n")
            title = heading.removeprefix("# ").strip() or title
            text = rest.strip()
        if text:
            yield {"title": title, "content": text, "source": path.name}
