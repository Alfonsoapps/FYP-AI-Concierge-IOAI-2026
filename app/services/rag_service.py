"""Async NVIDIA-embedding RAG storage for the IOAI 2027 concierge."""

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.config import get_settings
from app.services.chroma_service import (
    CHROMA_PERSIST_DIR,
    DEFAULT_COLLECTION,
    ensure_compatible_collection,
    get_chroma_client,
)
from app.services.embedding_service import (
    get_embedding_function,
    validate_embeddings,
)

logger = logging.getLogger(__name__)

CHROMA_PATH = CHROMA_PERSIST_DIR
COLLECTION_NAME = DEFAULT_COLLECTION


class KnowledgeBase:
    """Persist and retrieve event knowledge without blocking the event loop."""

    def __init__(
        self,
        persist_path: str | None = None,
        embeddings: Any | None = None,
        embedding_model: str | None = None,
        embedding_dimension: int | None = None,
    ) -> None:
        settings = get_settings()
        self.embedding_model = embedding_model or settings.nvidia_embedding_model
        self.embedding_dimension = (
            embedding_dimension or settings.nvidia_embedding_dimensions
        )
        self.client = get_chroma_client(persist_path)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "IOAI 2027 concierge knowledge"},
        )
        self.embeddings = embeddings
        self._ready = False
        self._ready_lock = asyncio.Lock()

    def _embedding_client(self) -> Any:
        if self.embeddings is None:
            self.embeddings = get_embedding_function()
        return self.embeddings

    def _embed_documents(self, documents: list[str]) -> list[list[float]]:
        vectors = self._embedding_client().embed_documents(documents)
        return validate_embeddings(vectors, self.embedding_dimension)

    def _embed_query(self, query: str) -> list[float]:
        vector = self._embedding_client().embed_query(query)
        return validate_embeddings([vector], self.embedding_dimension)[0]

    async def _ensure_ready(self) -> None:
        """Lazily select or migrate the collection before any operation."""
        if self._ready:
            return
        async with self._ready_lock:
            if self._ready:
                return
            self.collection = await asyncio.to_thread(
                ensure_compatible_collection,
                self.client,
                COLLECTION_NAME,
                self.embedding_model,
                self.embedding_dimension,
                self._embed_documents,
            )
            self._ready = True

    async def ingest_text(
        self,
        text_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Embed and upsert one knowledge record by its stable identifier."""
        clean_id = text_id.strip()
        clean_content = content.strip()
        if not clean_id or not clean_content:
            raise ValueError("text_id and content must not be empty.")

        try:
            await self._ensure_ready()
            embedding = await asyncio.to_thread(
                self._embed_documents, [clean_content]
            )
            await asyncio.to_thread(
                self.collection.upsert,
                ids=[clean_id],
                embeddings=embedding,
                documents=[clean_content],
                metadatas=[metadata or {}],
            )
        except Exception as exc:
            logger.exception("Failed to ingest knowledge record %s", clean_id)
            raise RuntimeError(f"Failed to ingest knowledge: {exc}") from exc

    async def _query_entries(
        self, query: str, top_k: int = 3
    ) -> list[dict[str, Any]]:
        """Return structured nearest-neighbour entries for internal callers."""
        clean_query = query.strip()
        if not clean_query:
            raise ValueError("query must not be empty.")
        if top_k < 1:
            raise ValueError("top_k must be at least 1.")

        try:
            await self._ensure_ready()
            count = await asyncio.to_thread(self.collection.count)
            if count == 0:
                return []

            query_embedding = await asyncio.to_thread(
                self._embed_query, clean_query
            )
            results = await asyncio.to_thread(
                self.collection.query,
                query_embeddings=[query_embedding],
                n_results=min(top_k, count),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.exception("Failed to retrieve RAG context")
            raise RuntimeError(f"Failed to retrieve context: {exc}") from exc

        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        ids = (results.get("ids") or [[]])[0]
        return [
            {
                "id": ids[index] if index < len(ids) else None,
                "text": document or "",
                "metadata": metadatas[index] if index < len(metadatas) else {},
                "distance": distances[index] if index < len(distances) else None,
            }
            for index, document in enumerate(documents)
        ]

    async def retrieve_context(self, query: str, top_k: int = 3) -> str:
        """Return citation-ready context for the LLM prompt."""
        entries = await self._query_entries(query, top_k)
        if not entries:
            return "No verified knowledge-base sources matched this question."

        context_blocks = []
        for entry in entries:
            metadata = entry["metadata"] or {}
            # The stable record ID often carries essential meaning (for example,
            # "University event"). Always expose it instead of replacing it with
            # a generic category such as "event".
            source = metadata.get("source") or entry["id"] or "knowledge-base"
            category = metadata.get("category")
            category_line = f"\n[Category: {category}]" if category else ""
            context_blocks.append(
                f"[Source: {source}]{category_line}\n{entry['text']}"
            )
        return "\n\n".join(context_blocks)

    async def get_all_knowledge(self) -> list[dict[str, Any]]:
        """Return all records, safely handling an empty collection."""
        try:
            await self._ensure_ready()
            results = await asyncio.to_thread(
                self.collection.get, include=["documents", "metadatas"]
            )
        except Exception as exc:
            logger.exception("Failed to list knowledge records")
            raise RuntimeError(f"Failed to list knowledge: {exc}") from exc

        if not results or not results.get("ids"):
            return []

        ids = results["ids"]
        documents = results.get("documents") or [""] * len(ids)
        metadatas = results.get("metadatas") or [{} for _ in ids]
        return [
            {
                "id": text_id,
                "content": documents[index] or "",
                "metadata": metadatas[index] or {},
                "category": (metadatas[index] or {}).get("category", "general"),
            }
            for index, text_id in enumerate(ids)
        ]

    async def delete_knowledge(self, text_id: str) -> None:
        """Delete one record by ID without blocking the event loop."""
        clean_id = text_id.strip()
        if not clean_id:
            raise ValueError("text_id must not be empty.")
        try:
            await self._ensure_ready()
            await asyncio.to_thread(self.collection.delete, ids=[clean_id])
        except Exception as exc:
            logger.exception("Failed to delete knowledge record %s", clean_id)
            raise RuntimeError(f"Failed to delete knowledge: {exc}") from exc

    async def count(self) -> int:
        """Return the number of stored records."""
        await self._ensure_ready()
        return await asyncio.to_thread(self.collection.count)


rag_db = KnowledgeBase()


# ---------------------------------------------------------------------------
# Backward-compatible synchronous API used by the teammate's existing RAG
# router. New application code should call ``rag_db`` asynchronously instead.
# ---------------------------------------------------------------------------
def _run_compat(coroutine: Any) -> Any:
    """Run an async operation from legacy sync code, including in an event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


def store_knowledge(
    texts: list[str],
    metadatas: list[dict[str, Any]] | None = None,
    source: str = "manual",
) -> int:
    """Compatibility wrapper for the existing ``POST /rag/store`` route."""
    if not texts:
        return 0

    async def _store_all() -> int:
        for index, text in enumerate(texts):
            metadata = dict(metadatas[index]) if metadatas else {}
            metadata.setdefault("source", source)
            await rag_db.ingest_text(uuid.uuid4().hex, text, metadata)
        return len(texts)

    return _run_compat(_store_all())


def retrieve_context(query: str, n_results: int = 3) -> list[dict[str, Any]]:
    """Compatibility wrapper for the existing ``POST /rag/query`` route."""
    return _run_compat(rag_db._query_entries(query, n_results))


def get_stats() -> dict[str, Any]:
    """Compatibility wrapper for the existing ``GET /rag/stats`` route."""
    return {
        "collection": COLLECTION_NAME,
        "document_count": _run_compat(rag_db.count()),
    }
