"""
IOAI 2027 Participant Platform - FastAPI Application Entry Point

Multi-page platform with AI Concierge as the guide feature.
Routes:
    /          → Home page
    /guide     → AI Concierge (avatar, chat, STT, TTS)
    /map       → Map (coming soon)
    /schedule  → Schedule (coming soon)
    /profile   → Profile (coming soon)
"""

import logging
import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates

# Anchor all file paths to the project root so the app works regardless of the
# process working directory (e.g. under uvicorn's --reload subprocess).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")


def _tpl(name: str) -> str:
    """Absolute path to a template file (for FileResponse)."""
    return os.path.join(TEMPLATES_DIR, name)

from app.config import get_settings
from app.routers import chat
from app.routers import tts
from app.routers import announcements
from app.routers import team_safety
from app.routers import explore
from app.routers.chat import router as chat_router
from app.services import announcement_service
from app.services import team_safety_service
from app.services import explore_service

# The RAG router depends on chromadb, which may be unavailable in some
# environments (e.g. no prebuilt wheel for the running Python version).
# Import it defensively so the rest of the platform still boots; when
# chromadb is installed this behaves exactly as before.
try:
    from app.routers import admin
    from app.routers import rag
    _RAG_AVAILABLE = True
except Exception as _rag_err:  # pragma: no cover - environment dependent
    admin = None
    rag = None
    _RAG_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "RAG router disabled (chromadb unavailable): %s", _rag_err
    )

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="IOAI 2027 Participant Platform with AI Concierge",
    version="1.0.0",
)

# Jinja2 templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)

def _router_path_signatures(router) -> set[tuple[str, frozenset[str]]]:
    """(path, methods) signatures for every HTTP route declared on a router."""
    signatures = set()
    for route in router.routes:
        methods = frozenset(getattr(route, "methods", None) or [])
        signatures.add((route.path, methods))
    return signatures


# Registry of (path, methods) signatures already registered on `app`, tracked
# explicitly because FastAPI wraps `include_router` results lazily and does
# not eagerly flatten them into `app.routes`.
_registered_route_signatures: set[tuple[str, frozenset[str]]] = set()


def _include_router_no_collisions(app: FastAPI, router, *, module_name: str, **kwargs) -> None:
    """
    Register a router only if none of its (path, method) pairs collide with a
    route already registered on the app. Colliding registrations fail
    application startup instead of silently shadowing an existing endpoint
    (Requirement 12.2).
    """
    incoming = _router_path_signatures(router)
    colliding = {
        path
        for path, methods in incoming
        if any(
            path == existing_path and (methods & existing_methods)
            for existing_path, existing_methods in _registered_route_signatures
        )
    }
    if colliding:
        raise RuntimeError(
            f"Startup aborted: router '{module_name}' declares path(s) "
            f"{sorted(colliding)} that collide with an already-registered route."
        )
    app.include_router(router, **kwargs)
    _registered_route_signatures.update(incoming)


# Register API routers (chat, TTS, RAG, Announcements). Registration order
# matters: chat, TTS, and RAG are the pre-existing endpoints that must remain
# reachable at their original paths; any later router (e.g. announcements)
# that declares a colliding path fails startup rather than partially
# registering (Requirement 12.1, 12.2).
_include_router_no_collisions(app, chat.router, module_name="chat")
_include_router_no_collisions(app, tts.router, module_name="tts")
if _RAG_AVAILABLE:
    _include_router_no_collisions(app, rag.router, module_name="rag")
    _include_router_no_collisions(app, admin.router, module_name="admin", tags=["Admin"])
_include_router_no_collisions(app, announcements.router, module_name="announcements")
_include_router_no_collisions(app, team_safety.router, module_name="team_safety")
_include_router_no_collisions(app, explore.router, module_name="explore")

# Serve static assets (CSS, JS, Live2D models, images)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
async def _init_announcements():
    """Initialize the announcements store and seed sample data if empty."""
    announcement_service.init_db()
    announcement_service.seed_sample_data()


@app.on_event("startup")
async def _init_team_safety():
    """
    No-op initialization hook for the Team Leader + Safety module. Production
    no longer seeds fake team members; real delegation rosters are built up
    as participants complete onboarding (see `team_safety_service.register_participant`).
    """
    pass


@app.on_event("startup")
async def _init_explore():
    """Initialize the Explore module's completion/badge store."""
    explore_service.init_db()


@app.on_event("startup")
async def _init_document_registry():
    """Initialize the document registry database."""
    from app.services.document_registry import init_db
    init_db()


@app.on_event("startup")
async def _init_chat_logger():
    """Initialize the chat logging database."""
    from app.services.chat_logger import init_db as init_chat_log_db
    init_chat_log_db()


# ============================================================
# PAGE ROUTES
# ============================================================

@app.get("/")
async def home_page(request: Request):
    """Home page - platform landing."""
    return templates.TemplateResponse(request, "home.html", {"request": request, "active_page": "home"})


@app.get("/guide")
async def guide_page():
    """AI Concierge guide page - full avatar experience."""
    return FileResponse(_tpl("index.html"))


@app.get("/map")
async def map_page(request: Request):
    """Map page - coming soon."""
    return templates.TemplateResponse(request, "map.html", {"request": request, "active_page": "map"})


@app.get("/schedule")
async def schedule_page(request: Request):
    """Schedule page - coming soon."""
    return templates.TemplateResponse(request, "schedule.html", {"request": request, "active_page": "schedule"})


@app.get("/profile")
async def profile_page(request: Request):
    """Profile page - coming soon."""
    return templates.TemplateResponse(request, "profile.html", {"request": request, "active_page": "profile"})


@app.get("/announcements")
async def announcements_page(request: Request):
    """User-facing announcements page (current + history)."""
    return templates.TemplateResponse(
        request, "announcements.html", {"request": request, "active_page": "announcements"}
    )


@app.get("/admin/dashboard")
async def admin_dashboard_page(request: Request):
    """Admin dashboard - overview page."""
    return templates.TemplateResponse(
        request, "admin_dashboard.html", {"request": request, "active_admin": "dashboard"}
    )


@app.get("/admin/announcements")
async def admin_announcements_page(request: Request):
    """Organiser announcement management console."""
    return templates.TemplateResponse(
        request, "admin_announcements.html", {"request": request, "active_page": "announcements", "active_admin": "announcements"}
    )


@app.get("/admin/schedule")
async def admin_schedule_page(request: Request):
    """Admin schedule management page."""
    return templates.TemplateResponse(
        request, "admin_schedule.html", {"request": request, "active_admin": "schedule"}
    )


@app.get("/admin/uploads")
async def admin_uploads_page(request: Request):
    """Admin document upload page."""
    return templates.TemplateResponse(
        request, "admin_uploads.html", {"request": request, "active_admin": "uploads"}
    )


@app.get("/admin/knowledge")
async def admin_knowledge_page(request: Request):
    """Admin knowledge base management page."""
    return templates.TemplateResponse(
        request, "admin_knowledge.html", {"request": request, "active_admin": "knowledge"}
    )


@app.get("/admin/chat-logs")
async def admin_chat_logs_page(request: Request):
    """Admin chat logs page."""
    return templates.TemplateResponse(
        request, "admin_chat_logs.html", {"request": request, "active_admin": "chat-logs"}
    )


@app.get("/admin/ai-settings")
async def admin_ai_settings_page(request: Request):
    """Admin AI settings page - shows current system configuration."""
    # Get live config values
    s = get_settings()
    # Get ChromaDB doc count safely
    doc_count = "N/A"
    try:
        from app.services.chroma_service import get_collection_stats
        stats = get_collection_stats()
        doc_count = str(stats.get("document_count", 0))
    except Exception:
        pass

    # Check guardrails availability
    guardrails_active = False
    try:
        from app.services.guardrails_service import is_available
        guardrails_active = is_available()
    except Exception:
        pass

    return templates.TemplateResponse(
        request, "admin_ai_settings.html", {
            "request": request,
            "active_admin": "ai-settings",
            "model": s.nvidia_model,
            "base_url": s.nvidia_base_url,
            "embedding_model": s.nvidia_embedding_model,
            "embedding_dims": s.nvidia_embedding_dimensions,
            "doc_count": doc_count,
            "guardrails_active": guardrails_active,
        }
    )


@app.get("/safety")
async def safety_page(request: Request):
    """Participant safety page - check-in and SOS submission."""
    return templates.TemplateResponse(
        request, "safety.html", {"request": request, "active_page": "safety"}
    )


@app.get("/team")
async def team_page():
    """Team / Delegation page."""
    return FileResponse(_tpl("team.html"))


@app.get("/onboarding")
async def onboarding_page():
    """Onboarding page - collect participant info."""
    return FileResponse(_tpl("onboarding.html"))


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": settings.app_name}


@app.post("/api/admin/uploads")
async def upload_documents(request: Request):
    """
    Upload official documents and ingest them into the ChromaDB knowledge base.

    Pipeline: Upload → Extract text → Chunk → Embed → Store in ChromaDB
    """
    import uuid
    from app.services.upload_service import validate_file, save_file, extract_text, delete_temp_file
    from app.services.rag_service import rag_db

    form = await request.form()
    files = form.getlist("files")

    if not files:
        return {"message": "No files provided.", "processed": 0, "results": []}

    results = []
    processed = 0
    chunk_size = 1000  # Characters per chunk (roughly 250 tokens)

    for file in files:
        if not hasattr(file, 'filename') or not file.filename:
            continue

        try:
            # Validate
            import os
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in {".pdf", ".docx", ".doc", ".txt"}:
                results.append({"file": file.filename, "status": "error", "detail": f"Unsupported type: {ext}"})
                continue

            # Save temporarily
            saved_path, size_bytes = await save_file(file)

            # Extract text
            text_content = extract_text(saved_path, ext)

            if not text_content or not text_content.strip():
                delete_temp_file(saved_path)
                results.append({"file": file.filename, "status": "error", "detail": "No text could be extracted"})
                continue

            # Chunk the text into manageable pieces
            chunks = []
            words = text_content.split()
            current_chunk = []
            current_len = 0

            for word in words:
                current_chunk.append(word)
                current_len += len(word) + 1
                if current_len >= chunk_size:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_len = 0

            if current_chunk:
                chunks.append(" ".join(current_chunk))

            # Ingest each chunk into ChromaDB
            for i, chunk in enumerate(chunks):
                chunk_id = f"doc_{uuid.uuid4().hex[:8]}_{file.filename}_{i}"
                await rag_db.ingest_text(
                    text_id=chunk_id,
                    content=chunk,
                    metadata={
                        "source": file.filename,
                        "category": "document",
                        "chunk": i + 1,
                        "total_chunks": len(chunks),
                    },
                )

            # Clean up temp file
            delete_temp_file(saved_path)

            # Record in persistent registry
            from app.services.document_registry import add_document
            size_str = f"{size_bytes / 1024:.0f} KB" if size_bytes < 1024 * 1024 else f"{size_bytes / (1024*1024):.1f} MB"
            add_document(
                filename=file.filename,
                file_type=ext.lstrip('.'),
                size_display=size_str,
                chunks=len(chunks),
                chars=len(text_content),
            )

            processed += 1
            results.append({
                "file": file.filename,
                "status": "success",
                "chunks": len(chunks),
                "chars": len(text_content),
            })

        except Exception as exc:
            results.append({"file": file.filename, "status": "error", "detail": str(exc)})

    return {
        "message": f"Processed {processed} file(s) into knowledge base.",
        "processed": processed,
        "results": results,
    }


@app.get("/api/admin/documents")
async def list_documents():
    """Return all registered uploaded documents."""
    from app.services.document_registry import get_all_documents
    return {"documents": get_all_documents()}


@app.get("/api/admin/chat-logs")
async def get_chat_logs(limit: int = 100, offset: int = 0):
    """Return recent chat logs for admin monitoring."""
    from app.services.chat_logger import get_recent_logs, get_stats
    return {
        "logs": get_recent_logs(limit=limit, offset=offset),
        "stats": get_stats(),
    }


@app.get("/api/admin/analytics/faq")
async def get_faq_analytics():
    """Return frequently asked questions."""
    from app.services.chat_logger import get_top_questions
    return {"questions": get_top_questions(limit=15)}


@app.get("/api/admin/analytics/unanswered")
async def get_unanswered_analytics():
    """Return questions the AI could not answer."""
    from app.services.chat_logger import get_unanswered_questions
    return {"questions": get_unanswered_questions(limit=20)}


@app.get("/api/admin/analytics/engagement")
async def get_engagement_analytics():
    """Return participant engagement metrics."""
    from app.services.chat_logger import get_engagement_metrics, get_stats
    return {
        "engagement": get_engagement_metrics(),
        "stats": get_stats(),
    }


@app.delete("/api/admin/documents/{doc_id}")
async def remove_document(doc_id: int):
    """Delete a document record from the registry."""
    from app.services.document_registry import delete_document
    if delete_document(doc_id):
        return {"status": "success"}
    return {"status": "not_found"}


# Advanced RAG + audio WebSocket endpoint. This additional prefixed mounting
# leaves every existing teammate route and startup event above unchanged.
app.include_router(chat_router, prefix="/api/v1/chat", tags=["Chat"])
