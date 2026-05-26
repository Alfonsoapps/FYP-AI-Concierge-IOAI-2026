"""
ChromaDB Vector Database Service

Manages the ChromaDB vector store for storing and retrieving
text embeddings. This is the foundation for RAG (Retrieval-Augmented
Generation) — allowing the AI to reference stored knowledge.

Architecture:
    - Uses ChromaDB in persistent mode (data survives restarts)
    - Stores documents with their embeddings and metadata
    - Supports similarity search to find relevant context
    - Designed to be extended with PDF/document ingestion later

ChromaDB stores:
    - documents: the original text chunks
    - embeddings: vector representations of the text
    - metadatas: extra info (source file, page number, etc.)
    - ids: unique identifiers for each entry
"""

import logging
from typing import List, Dict, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)

# --- Configuration ---
CHROMA_PERSIST_DIR = "./chroma_data"  # Where ChromaDB stores its data
DEFAULT_COLLECTION = "concierge_knowledge"  # Default collection name

# ChromaDB client instance (initialized once)
_client = None


def get_chroma_client():
    """
    Get or initialize the ChromaDB client.
    Uses persistent storage so data survives server restarts.
    
    Returns:
        The ChromaDB client instance.
    """
    global _client

    if _client is None:
        logger.info("Initializing ChromaDB (persist_dir=%s)...", CHROMA_PERSIST_DIR)
        _client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        logger.info("✓ ChromaDB initialized")

    return _client


def get_collection(name: str = DEFAULT_COLLECTION):
    """
    Get or create a ChromaDB collection.
    A collection is like a table — it groups related documents together.

    Args:
        name: Collection name.

    Returns:
        The ChromaDB collection object.
    """
    client = get_chroma_client()
    collection = client.get_or_create_collection(
        name=name,
        metadata={"description": "IOAI 2027 AI Concierge knowledge base"}
    )
    logger.info("Collection '%s' ready (count=%d)", name, collection.count())
    return collection


def add_documents(
    documents: List[str],
    embeddings: List[List[float]],
    metadatas: Optional[List[Dict]] = None,
    ids: Optional[List[str]] = None,
    collection_name: str = DEFAULT_COLLECTION,
) -> int:
    """
    Add documents with their embeddings to the vector database.

    Args:
        documents: List of text strings to store.
        embeddings: Corresponding embedding vectors.
        metadatas: Optional metadata dicts for each document.
        ids: Optional unique IDs. Auto-generated if not provided.
        collection_name: Which collection to add to.

    Returns:
        Number of documents added.
    """
    if not documents:
        return 0

    collection = get_collection(collection_name)

    # Auto-generate IDs if not provided
    if ids is None:
        import uuid
        ids = [str(uuid.uuid4()) for _ in documents]

    # Default metadata if not provided
    if metadatas is None:
        metadatas = [{"source": "manual"} for _ in documents]

    collection.add(
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids,
    )

    logger.info("Added %d documents to collection '%s'", len(documents), collection_name)
    return len(documents)


def query_similar(
    query_embedding: List[float],
    n_results: int = 3,
    collection_name: str = DEFAULT_COLLECTION,
) -> Dict:
    """
    Find the most similar documents to a query embedding.

    Args:
        query_embedding: The embedding vector to search with.
        n_results: Number of results to return (default: 3).
        collection_name: Which collection to search.

    Returns:
        Dict with keys: 'documents', 'metadatas', 'distances', 'ids'
        Each is a list of lists (ChromaDB format).
    """
    collection = get_collection(collection_name)

    if collection.count() == 0:
        logger.info("Collection '%s' is empty, no results", collection_name)
        return {"documents": [[]], "metadatas": [[]], "distances": [[]], "ids": [[]]}

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, collection.count()),
    )

    logger.info(
        "Query returned %d results from '%s'",
        len(results["documents"][0]) if results["documents"] else 0,
        collection_name,
    )
    return results


def get_collection_stats(collection_name: str = DEFAULT_COLLECTION) -> Dict:
    """
    Get statistics about a collection.

    Returns:
        Dict with count and collection name.
    """
    collection = get_collection(collection_name)
    return {
        "collection": collection_name,
        "document_count": collection.count(),
    }


def delete_collection(collection_name: str = DEFAULT_COLLECTION):
    """
    Delete an entire collection (use with caution).
    """
    client = get_chroma_client()
    client.delete_collection(collection_name)
    logger.info("Deleted collection: %s", collection_name)
