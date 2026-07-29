"""Focused regression tests for persisted Chroma embedding dimensions."""

import asyncio

import chromadb

from app.services.chroma_service import DEFAULT_COLLECTION, collection_dimension
from app.services.rag_service import KnowledgeBase


class FakeEmbeddings:
    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self.document_calls = 0
        self.query_calls = 0

    def embed_documents(self, documents: list[str]) -> list[list[float]]:
        self.document_calls += 1
        return [self._vector(text) for text in documents]

    def embed_query(self, query: str) -> list[float]:
        self.query_calls += 1
        return self._vector(query)

    def _vector(self, text: str) -> list[float]:
        value = float((sum(map(ord, text)) % 11) + 1)
        return [value] * self.dimension


def _knowledge_base(tmp_path, embeddings: FakeEmbeddings) -> KnowledgeBase:
    return KnowledgeBase(
        persist_path=str(tmp_path),
        embeddings=embeddings,
        embedding_model="test/embed-v2",
        embedding_dimension=embeddings.dimension,
    )


def test_migrates_1024_to_2048_without_deleting_source(tmp_path):
    client = chromadb.PersistentClient(path=str(tmp_path))
    source = client.get_or_create_collection(DEFAULT_COLLECTION)
    source.upsert(
        ids=["venue"],
        documents=["The venue is NUS."],
        metadatas=[{"category": "venue", "source": "organiser"}],
        embeddings=[[0.25] * 1024],
    )

    embeddings = FakeEmbeddings(2048)
    kb = _knowledge_base(tmp_path, embeddings)
    records = asyncio.run(kb.get_all_knowledge())

    assert records == [{
        "id": "venue",
        "content": "The venue is NUS.",
        "metadata": {"category": "venue", "source": "organiser"},
        "category": "venue",
    }]
    assert kb.collection.name != DEFAULT_COLLECTION
    assert collection_dimension(kb.collection) == 2048
    preserved = client.get_collection(DEFAULT_COLLECTION)
    assert preserved.count() == 1
    assert collection_dimension(preserved) == 1024
    original = preserved.get(include=["documents", "metadatas"])
    assert original["documents"] == ["The venue is NUS."]
    assert original["metadatas"] == [{"category": "venue", "source": "organiser"}]

    restarted_embeddings = FakeEmbeddings(2048)
    restarted = _knowledge_base(tmp_path, restarted_embeddings)
    assert asyncio.run(restarted.count()) == 1
    assert restarted.collection.name == kb.collection.name
    assert restarted_embeddings.document_calls == 0


def test_matching_collection_is_used_without_reembedding(tmp_path):
    client = chromadb.PersistentClient(path=str(tmp_path))
    source = client.get_or_create_collection(DEFAULT_COLLECTION)
    source.upsert(
        ids=["schedule"],
        documents=["Opening ceremony is Monday."],
        metadatas=[{"category": "schedule"}],
        embeddings=[[0.5] * 2048],
    )

    embeddings = FakeEmbeddings(2048)
    kb = _knowledge_base(tmp_path, embeddings)
    results = asyncio.run(kb._query_entries("opening", top_k=1))

    assert kb.collection.name == DEFAULT_COLLECTION
    assert embeddings.document_calls == 0
    assert results[0]["id"] == "schedule"
    assert results[0]["metadata"] == {"category": "schedule"}


def test_new_empty_collection_adopts_configured_dimension(tmp_path):
    embeddings = FakeEmbeddings(2048)
    kb = _knowledge_base(tmp_path, embeddings)

    assert asyncio.run(kb.count()) == 0
    asyncio.run(
        kb.ingest_text(
            "arrival",
            "Arrive through Changi Airport.",
            {"category": "travel"},
        )
    )
    results = asyncio.run(kb._query_entries("airport", top_k=1))

    assert kb.collection.name == DEFAULT_COLLECTION
    assert collection_dimension(kb.collection) == 2048
    assert results[0]["id"] == "arrival"
    assert results[0]["metadata"] == {"category": "travel"}
