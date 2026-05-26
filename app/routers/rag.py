"""
RAG Router - Debug and Test Endpoints

Provides endpoints to verify the ChromaDB + embedding system is working.
These are useful for development and testing.

Endpoints:
    POST /rag/store    - Store knowledge text in the vector database
    POST /rag/query    - Query for similar knowledge
    GET  /rag/stats    - Get database statistics
    POST /rag/seed     - Seed the database with sample IOAI 2027 knowledge
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.rag_service import store_knowledge, retrieve_context, get_stats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])


# --- Request/Response schemas ---

class StoreRequest(BaseModel):
    """Request to store knowledge in the vector database."""
    texts: List[str] = Field(..., min_length=1, description="List of text entries to store")
    source: str = Field(default="manual", description="Source label for the entries")


class StoreResponse(BaseModel):
    """Response after storing knowledge."""
    stored: int
    message: str


class QueryRequest(BaseModel):
    """Request to query the knowledge base."""
    query: str = Field(..., min_length=1, description="Search query text")
    n_results: int = Field(default=3, ge=1, le=10, description="Number of results")


class QueryResult(BaseModel):
    """A single query result."""
    text: str
    distance: Optional[float]
    metadata: dict


class QueryResponse(BaseModel):
    """Response with query results."""
    query: str
    results: List[QueryResult]
    count: int


# --- Endpoints ---

@router.post("/store", response_model=StoreResponse)
async def store_endpoint(request: StoreRequest):
    """
    Store knowledge text in the vector database.
    Automatically generates embeddings.

    Example body:
        {"texts": ["IOAI 2027 is in Singapore", "The event runs July 15-22"], "source": "event_info"}
    """
    try:
        count = store_knowledge(request.texts, source=request.source)
        return StoreResponse(stored=count, message=f"Successfully stored {count} entries.")
    except Exception as e:
        logger.error("Store failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    """
    Query the knowledge base for relevant context.
    Returns the most semantically similar stored entries.

    Example body:
        {"query": "Where is IOAI 2027?", "n_results": 3}
    """
    try:
        results = retrieve_context(request.query, n_results=request.n_results)
        formatted = [
            QueryResult(
                text=r["text"],
                distance=r["distance"],
                metadata=r["metadata"],
            )
            for r in results
        ]
        return QueryResponse(query=request.query, results=formatted, count=len(formatted))
    except Exception as e:
        logger.error("Query failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def stats_endpoint():
    """
    Get current vector database statistics.
    Shows how many documents are stored.
    """
    try:
        return get_stats()
    except Exception as e:
        logger.error("Stats failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/seed")
async def seed_endpoint():
    """
    Seed the database with sample IOAI 2027 knowledge.
    Useful for testing the RAG system quickly.
    """
    sample_knowledge = [
        "IOAI 2027 (International Olympiad in Artificial Intelligence) will be held in Singapore from July 15 to July 22, 2027.",
        "The main venue for IOAI 2027 is the National University of Singapore (NUS) campus.",
        "Participants should arrive at Singapore Changi Airport (SIN). The airport has excellent MRT train connections to the city.",
        "Singapore's official languages are English, Mandarin, Malay, and Tamil. English is the primary language of business and education.",
        "The weather in Singapore in July is hot and humid, with temperatures around 27-33°C. Bring light clothing and an umbrella for sudden rain showers.",
        "Must-try Singaporean foods include Hainanese Chicken Rice, Laksa, Char Kway Teow, and Chili Crab. Hawker centres offer affordable meals.",
        "The Singapore MRT (Mass Rapid Transit) is the best way to get around. Get an EZ-Link card for convenient travel on trains and buses.",
        "Important cultural tips: Remove shoes before entering homes, don't chew gum (it's restricted), and tipping is not expected in Singapore.",
        "IOAI 2027 registration opens in January 2027. Each country can send a team of up to 4 students with 2 team leaders.",
        "The competition covers machine learning, neural networks, computer vision, natural language processing, and AI ethics.",
        "Free Wi-Fi is available at most public places in Singapore including MRT stations, libraries, and shopping malls.",
        "Emergency numbers in Singapore: Police 999, Ambulance/Fire 995, Non-emergency police hotline 1800-255-0000.",
    ]

    try:
        count = store_knowledge(sample_knowledge, source="ioai_2027_seed")
        return {
            "message": f"Seeded {count} sample knowledge entries",
            "count": count,
            "source": "ioai_2027_seed",
        }
    except Exception as e:
        logger.error("Seed failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
