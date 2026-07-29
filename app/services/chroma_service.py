"""Chroma persistence and non-destructive embedding-dimension migration."""

import hashlib
import json
import logging
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import chromadb
from chromadb.errors import NotFoundError

from app.config import get_settings

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHROMA_PERSIST_DIR = str(PROJECT_ROOT / "app" / "data" / "chroma_db")
DEFAULT_COLLECTION = "ioai_knowledge"
DESCRIPTION = "IOAI 2027 concierge knowledge"
ACTIVE_KEY = "active_collection"
DIMENSION_KEY = "embedding_dimension"
MODEL_KEY = "embedding_model"
_client = None


def get_chroma_client(path: str | None = None):
    """Return the process client, or an isolated client for an explicit path."""
    global _client
    if path is not None:
        return chromadb.PersistentClient(path=path)
    if _client is None:
        Path(CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return _client


def _merged_metadata(collection, **updates: Any) -> dict[str, Any]:
    metadata = dict(collection.metadata or {})
    metadata.setdefault("description", DESCRIPTION)
    metadata.update(updates)
    return metadata


def collection_dimension(collection) -> int | None:
    """Read the persisted vector width without issuing a similarity query."""
    if collection.count() == 0:
        return None
    result = collection.get(limit=1, include=["embeddings"])
    embeddings = result.get("embeddings")
    return len(embeddings[0]) if embeddings is not None and len(embeddings) else None
def _migration_name(
    base_name: str,
    model: str,
    dimension: int,
    ids: Sequence[str],
    documents: Sequence[str],
    metadatas: Sequence[dict[str, Any]],
) -> str:
    """Build a deterministic name so interrupted/concurrent migrations resume."""
    model_hash = hashlib.sha256(model.encode("utf-8")).hexdigest()[:8]
    snapshot = json.dumps(
        list(zip(ids, documents, metadatas)),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    data_hash = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()[:10]
    return f"{base_name}__d{dimension}__{model_hash}__{data_hash}"


def _set_active_pointer(base_collection, active_collection, model: str, dimension: int):
    base_collection.modify(
        metadata=_merged_metadata(
            base_collection,
            **{
                ACTIVE_KEY: active_collection.name,
                MODEL_KEY: model,
                DIMENSION_KEY: dimension,
            },
        )
    )


def _resolve_active_collection(client, base_collection):
    active_name = (base_collection.metadata or {}).get(ACTIVE_KEY)
    if not active_name or active_name == base_collection.name:
        return base_collection
    try:
        return client.get_collection(active_name)
    except NotFoundError:
        logger.warning(
            "Configured active collection %s is missing; using preserved base %s",
            active_name,
            base_collection.name,
        )
        return base_collection


def ensure_compatible_collection(
    client,
    base_name: str,
    model: str,
    expected_dimension: int,
    embed_documents: Callable[[list[str]], list[list[float]]],
):
    """Return a compatible collection, preserving the source during migration."""
    base = client.get_or_create_collection(
        name=base_name, metadata={"description": DESCRIPTION}
    )
    source = _resolve_active_collection(client, base)
    count = source.count()
    actual_dimension = collection_dimension(source)
    declared_model = (source.metadata or {}).get(MODEL_KEY)
    # Empty collections have no fixed dimension yet. Matching legacy collections
    # can safely be claimed by the pinned model because no contrary model marker
    # exists; every subsequent vector is still checked before Chroma receives it.
    compatible = actual_dimension in (None, expected_dimension) and (
        not declared_model or declared_model == model
    )
    if compatible:
        source.modify(
            metadata=_merged_metadata(
                source,
                **{MODEL_KEY: model, DIMENSION_KEY: expected_dimension},
            )
        )
        _set_active_pointer(base, source, model, expected_dimension)
        return source

    records = source.get(include=["documents", "metadatas"])
    ids = list(records.get("ids") or [])
    documents = list(records.get("documents") or [])
    raw_metadatas = list(records.get("metadatas") or [])
    metadatas = [dict(metadata or {}) for metadata in raw_metadatas]
    if len(ids) != count or len(documents) != count or any(not doc for doc in documents):
        raise RuntimeError(
            "Cannot migrate embeddings because one or more stored records has no document."
        )

    logger.warning(
        "Migrating collection %s non-destructively from dimension %s to %d (%d records)",
        source.name,
        actual_dimension,
        expected_dimension,
        count,
    )
    vectors = embed_documents(documents)
    if len(vectors) != count or any(len(vector) != expected_dimension for vector in vectors):
        raise RuntimeError(
            "Embedding provider returned an unexpected count or dimension during migration."
        )

    target_name = _migration_name(
        base_name, model, expected_dimension, ids, documents, metadatas
    )
    target = client.get_or_create_collection(
        name=target_name,
        metadata={
            "description": DESCRIPTION,
            MODEL_KEY: model,
            DIMENSION_KEY: expected_dimension,
            "migrated_from": source.name,
        },
    )
    for start in range(0, count, 100):
        end = start + 100
        target.upsert(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
            embeddings=vectors[start:end],
        )

    migrated = target.get(ids=ids, include=["documents", "metadatas"])
    if set(migrated.get("ids") or []) != set(ids):
        raise RuntimeError("Migration verification failed; the source remains active and intact.")
    if collection_dimension(target) != expected_dimension:
        raise RuntimeError("Migration dimension verification failed; source remains intact.")

    source.modify(metadata=_merged_metadata(source, migrated_to=target.name))
    # Commit the pointer last. Until this succeeds, all readers continue using
    # the untouched source collection and a retry safely upserts the same IDs.
    _set_active_pointer(base, target, model, expected_dimension)
    logger.info(
        "Embedding migration complete: %s -> %s (%d records preserved)",
        source.name,
        target.name,
        count,
    )
    return target


def get_collection(name: str = DEFAULT_COLLECTION):
    """Return the active collection selected by the base collection pointer."""
    client = get_chroma_client()
    base = client.get_or_create_collection(
        name=name, metadata={"description": DESCRIPTION}
    )
    return _resolve_active_collection(client, base)


def _validate_vectors(embeddings: Sequence[Sequence[float]]) -> None:
    expected = get_settings().nvidia_embedding_dimensions
    if any(len(vector) != expected for vector in embeddings):
        raise ValueError(f"All embeddings must have configured dimension {expected}.")


def add_documents(
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict[str, Any]] | None = None,
    ids: list[str] | None = None,
    collection_name: str = DEFAULT_COLLECTION,
) -> int:
    """Legacy helper retained with strict dimension checks."""
    if not documents:
        return 0
    _validate_vectors(embeddings)
    collection = get_collection(collection_name)
    ids = ids or [str(uuid.uuid4()) for _ in documents]
    metadatas = metadatas or [{"source": "manual"} for _ in documents]
    collection.add(documents=documents, embeddings=embeddings, metadatas=metadatas, ids=ids)
    return len(documents)
def query_similar(
    query_embedding: list[float],
    n_results: int = 3,
    collection_name: str = DEFAULT_COLLECTION,
) -> dict[str, Any]:
    """Legacy similarity helper retained with strict dimension checks."""
    _validate_vectors([query_embedding])
    collection = get_collection(collection_name)
    count = collection.count()
    if count == 0:
        return {"documents": [[]], "metadatas": [[]], "distances": [[]], "ids": [[]]}
    return collection.query(
        query_embeddings=[query_embedding], n_results=min(n_results, count)
    )


def get_collection_stats(collection_name: str = DEFAULT_COLLECTION) -> dict[str, Any]:
    collection = get_collection(collection_name)
    return {"collection": collection.name, "document_count": collection.count()}


def delete_collection(collection_name: str = DEFAULT_COLLECTION) -> None:
    """Legacy explicit deletion API; never used by migration."""
    get_chroma_client().delete_collection(collection_name)
    logger.info("Deleted collection: %s", collection_name)
