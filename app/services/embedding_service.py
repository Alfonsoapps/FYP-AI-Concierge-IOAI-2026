"""Pinned NVIDIA embedding generation with output-dimension validation."""

import logging
from collections.abc import Sequence

from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

from app.config import get_settings

logger = logging.getLogger(__name__)
_embed_fn: NVIDIAEmbeddings | None = None


def get_embedding_function() -> NVIDIAEmbeddings:
    """Return the shared embedding client with a stable model and dimension."""
    global _embed_fn
    if _embed_fn is None:
        settings = get_settings()
        _embed_fn = NVIDIAEmbeddings(
            model=settings.nvidia_embedding_model,
            dimensions=settings.nvidia_embedding_dimensions,
        )
        logger.info(
            "Embedding model configured (model=%s, dimensions=%d)",
            settings.nvidia_embedding_model,
            settings.nvidia_embedding_dimensions,
        )
    return _embed_fn


def validate_embeddings(
    embeddings: Sequence[Sequence[float]], expected_dimension: int | None = None
) -> list[list[float]]:
    """Copy vectors to lists and reject provider/model dimension drift."""
    expected = expected_dimension or get_settings().nvidia_embedding_dimensions
    vectors = [list(vector) for vector in embeddings]
    for index, vector in enumerate(vectors):
        if len(vector) != expected:
            raise ValueError(
                f"Embedding {index} has dimension {len(vector)}; expected {expected}. "
                "Check NVIDIA_EMBEDDING_MODEL and NVIDIA_EMBEDDING_DIMENSIONS."
            )
    return vectors
def generate_embedding(text: str) -> list[float]:
    """Generate one query embedding (backward-compatible public helper)."""
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("Cannot generate embedding for empty text.")
    vector = get_embedding_function().embed_query(clean_text)
    return validate_embeddings([vector])[0]


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate document embeddings in the model's retrieval document mode."""
    if not texts:
        return []
    if any(not text or not text.strip() for text in texts):
        raise ValueError("Cannot generate embeddings for empty text.")
    vectors = get_embedding_function().embed_documents(
        [text.strip() for text in texts]
    )
    logger.info("Generated %d document embeddings", len(texts))
    return validate_embeddings(vectors)
