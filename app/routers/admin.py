"""Organizer dashboard page and protected RAG administration API."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.routers import chat as chat_api
from app.routers.chat import manager
from app.services.rag_service import rag_db

# Keep the template path aligned with the existing project-level templates
# directory. The application is launched from the repository root.
templates = Jinja2Templates(directory="templates")
router = APIRouter()


class KnowledgePayload(BaseModel):
    """Exact JSON contract accepted by the admin knowledge endpoint."""

    text_id: str
    category: str
    content: str


def verify_admin(x_user_role: str | None = Header(default=None)) -> None:
    """Reject admin API calls that do not declare the Organiser role."""
    if x_user_role != "Organiser":
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Organiser access required",
        )


@router.get("/admin")
async def admin_dashboard(request: Request):
    """Render a fresh dashboard so browsers do not retain stale inline JS."""
    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        {"request": request},
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get(
    "/api/v1/admin/analytics",
    dependencies=[Depends(verify_admin)],
)
async def get_analytics(response: Response) -> dict[str, int | str]:
    """Return uncached metrics from durable analytics and the RAG database."""
    response.headers["Cache-Control"] = "no-store, max-age=0"
    try:
        kb_data = await rag_db.get_all_knowledge()
        return {
            "total_queries": chat_api.get_total_queries(),
            "active_users": chat_api.get_active_user_count(),
            "kb_size": len(kb_data),
            "system_health": "100% Online",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/api/v1/admin/knowledge",
    dependencies=[Depends(verify_admin)],
)
async def get_knowledge(response: Response) -> dict[str, object]:
    """Return uncached knowledge records stored in ChromaDB."""
    response.headers["Cache-Control"] = "no-store, max-age=0"
    try:
        return {"data": await rag_db.get_all_knowledge()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/v1/admin/knowledge")
async def ingest_knowledge(
    payload: KnowledgePayload,
    _authorized: None = Depends(verify_admin),
) -> dict[str, str]:
    """Validate, embed, and persist one knowledge record."""
    try:
        await rag_db.ingest_text(
            text_id=payload.text_id,
            content=payload.content,
            metadata={"category": payload.category},
        )
        return {"status": "success"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/api/v1/admin/knowledge/{text_id}")
async def delete_knowledge(
    text_id: str,
    _authorized: None = Depends(verify_admin),
) -> dict[str, str]:
    """Delete one knowledge record by its stable text identifier."""
    try:
        await rag_db.delete_knowledge(text_id)
        return {"status": "success"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
