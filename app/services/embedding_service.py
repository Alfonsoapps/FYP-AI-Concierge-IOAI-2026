"""
Embedding Service Module

Generates text embeddings using ChromaDB's built-in default embedding function.
This uses the all-MiniLM-L6-v2 model via ONNX runtime — lightweight, fast,
and requires no GPU or heavy dependencies like PyTorch.

Architecture note:
    ChromaDB includes its own embedding function by default.
    We expose it here as a standalone service for flexibility.
    Future: Can be swapped for NVIDIA NeMo embeddings or OpenAI embeddings.
"""

import logging
from typing import List

logger = logging.getLogger(__name__)

# The embedding function instance (loaded once, reused)
_embed_fn = None


def get_embedding_function():
    """
    Get or initialize the embedding function.
    Uses ChromaDB's default embedding function (all-MiniLM-L6-v2 via ONNX).
    Lazy-loaded on first use.

    Returns:
        A ChromaDB embedding function instance.
    """
    global _embed_fn

    if _embed_fn is None:
        logger.info("Loading embedding function (ChromaDB default)...")
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        _embed_fn = DefaultEmbeddingFunction()
        logger.info("✓ Embedding function loaded")

    return _embed_fn


def generate_embedding(text: str) -> List[float]:
    """
    Generate an embedding vector for a single text string.

    Args:
        text: The text to embed.

    Returns:
        A list of floats representing the embedding vector (384 dimensions).

    Raises:
        ValueError: If text is empty.
    """
    if not text or not text.strip():
        raise ValueError("Cannot generate embedding for empty text.")

    embed_fn = get_embedding_function()
    embeddings = embed_fn([text])

    logger.debug("Generated embedding for text (%d chars)", len(text))
    return embeddings[0]


def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for multiple texts in a batch (more efficient).

    Args:
        texts: List of text strings to embed.

    Returns:
        List of embedding vectors.
    """
    if not texts:
        return []

    embed_fn = get_embedding_function()
    embeddings = embed_fn(texts)

    logger.info("Generated %d embeddings in batch", len(texts))
    return embeddings
