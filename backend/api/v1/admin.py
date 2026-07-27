import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.v1 import chat as chat_api
from api.v1.chat import manager
from services.rag_service import rag_db


class KnowledgePayload(BaseModel):
    text_id: str
    content: str
    category: str


router = APIRouter()


@router.post("/knowledge")
async def ingest_knowledge(payload: KnowledgePayload) -> dict[str, str]:
    """Embed and persist organizer-provided knowledge in ChromaDB."""
    try:
        await rag_db.ingest_text(
            doc_id=payload.text_id,
            text=payload.content,
            metadata={"category": payload.category},
        )
        return {
            "status": "success",
            "message": f"Successfully ingested {payload.text_id}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/knowledge")
async def get_knowledge() -> dict[str, object]:
    """Return every knowledge entry currently stored in ChromaDB."""
    try:
        data = await rag_db.get_all_knowledge()
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/knowledge/{text_id}")
async def delete_knowledge(text_id: str) -> dict[str, str]:
    """Delete one knowledge entry by its stable text ID."""
    try:
        await rag_db.delete_knowledge(text_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/analytics")
async def get_analytics() -> dict[str, int | str]:
    """Return live chat activity, connection, and knowledge-base metrics."""
    try:
        active_users = manager.active_user_count
        kb_size = await asyncio.to_thread(rag_db.collection.count)
        return {
            "total_queries": chat_api.TOTAL_QUERIES,
            "active_users": active_users,
            "kb_size": kb_size,
            "system_health": "100% Online",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
