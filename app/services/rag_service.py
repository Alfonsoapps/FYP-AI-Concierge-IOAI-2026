"""
RAG Service Module (Retrieval-Augmented Generation)

Orchestrates the embedding and retrieval pipeline:
1. Takes user text → generates embedding
2. Searches ChromaDB for similar stored knowledge
3. Returns relevant context that can augment AI responses

Architecture note:
    This module ties together the embedding_service and chroma_service.
    It provides a clean interface for the rest of the app to use RAG
    without knowing the internal details.

    Future enhancements:
    - PDF document ingestion
    - Automatic chunking of long documents
    - Re-ranking of results
    - Integration with the NVIDIA AI prompt (context injection)
"""

import logging
from typing import List, Dict, Optional

from app.services.embedding_service import generate_embedding, generate_embeddings
from app.services.chroma_service import (
    add_documents,
    query_similar,
    get_collection_stats,
)

logger = logging.getLogger(__name__)


def store_knowledge(
    texts: List[str],
    metadatas: Optional[List[Dict]] = None,
    source: str = "manual",
) -> int:
    """
    Store text knowledge in the vector database.
    Automatically generates embeddings for each text.

    Args:
        texts: List of text strings to store as knowledge.
        metadatas: Optional metadata for each text.
        source: Source label (e.g., "manual", "pdf", "web").

    Returns:
        Number of documents stored.

    Example:
        store_knowledge([
            "IOAI 2027 will be held in Singapore from July 15-22.",
            "The venue is the National University of Singapore.",
        ], source="event_info")
    """
    if not texts:
        return 0

    logger.info("Storing %d knowledge entries (source=%s)...", len(texts), source)

    # Generate embeddings for all texts
    embeddings = generate_embeddings(texts)

    # Add default metadata if not provided
    if metadatas is None:
        metadatas = [{"source": source} for _ in texts]
    else:
        # Ensure source is in metadata
        for meta in metadatas:
            if "source" not in meta:
                meta["source"] = source

    # Store in ChromaDB
    count = add_documents(
        documents=texts,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    logger.info("✓ Stored %d knowledge entries", count)
    return count


def retrieve_context(query: str, n_results: int = 3) -> List[Dict]:
    """
    Retrieve relevant context for a user query.
    Finds the most semantically similar stored knowledge.

    Args:
        query: The user's question or message.
        n_results: How many relevant results to return.

    Returns:
        List of dicts, each with 'text', 'metadata', and 'distance' keys.
        Sorted by relevance (most relevant first).
        Returns empty list if no knowledge is stored.

    Example:
        results = retrieve_context("Where is IOAI 2027?")
        # [{"text": "IOAI 2027 will be held in Singapore...", "distance": 0.23, ...}]
    """
    logger.info("Retrieving context for: '%s'", query[:80])

    # Generate embedding for the query
    query_embedding = generate_embedding(query)

    # Search ChromaDB for similar documents
    results = query_similar(query_embedding, n_results=n_results)

    # Format results into a clean list
    formatted = []
    if results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            formatted.append({
                "text": doc,
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else None,
                "id": results["ids"][0][i] if results["ids"] else None,
            })

    logger.info("Retrieved %d relevant context entries", len(formatted))
    return formatted


def get_stats() -> Dict:
    """
    Get current RAG system statistics.

    Returns:
        Dict with database stats.
    """
    return get_collection_stats()
