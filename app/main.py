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
from app.services import announcement_service
from app.services import team_safety_service

# The RAG router depends on chromadb, which may be unavailable in some
# environments (e.g. no prebuilt wheel for the running Python version).
# Import it defensively so the rest of the platform still boots; when
# chromadb is installed this behaves exactly as before.
try:
    from app.routers import rag
    _RAG_AVAILABLE = True
except Exception as _rag_err:  # pragma: no cover - environment dependent
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

# Register API routers (chat, TTS, RAG, Announcements)
app.include_router(chat.router)
app.include_router(tts.router)
if _RAG_AVAILABLE:
    app.include_router(rag.router)
app.include_router(announcements.router)
app.include_router(team_safety.router)

# Serve static assets (CSS, JS, Live2D models, images)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
async def _init_announcements():
    """Initialize the announcements store and seed sample data if empty."""
    announcement_service.init_db()
    announcement_service.seed_sample_data()


@app.on_event("startup")
async def _init_team_safety():
    """Seed the Team Leader + Safety in-memory store with sample data."""
    team_safety_service.seed_sample_data()


# ============================================================
# PAGE ROUTES
# ============================================================

@app.get("/")
async def home_page(request: Request):
    """Home page - platform landing."""
    return templates.TemplateResponse("home.html", {"request": request, "active_page": "home"})


@app.get("/guide")
async def guide_page():
    """AI Concierge guide page - full avatar experience."""
    return FileResponse(_tpl("index.html"))


@app.get("/map")
async def map_page(request: Request):
    """Map page - coming soon."""
    return templates.TemplateResponse("map.html", {"request": request, "active_page": "map"})


@app.get("/schedule")
async def schedule_page(request: Request):
    """Schedule page - coming soon."""
    return templates.TemplateResponse("schedule.html", {"request": request, "active_page": "schedule"})


@app.get("/profile")
async def profile_page(request: Request):
    """Profile page - coming soon."""
    return templates.TemplateResponse("profile.html", {"request": request, "active_page": "profile"})


@app.get("/announcements")
async def announcements_page(request: Request):
    """User-facing announcements page (current + history)."""
    return templates.TemplateResponse(
        "announcements.html", {"request": request, "active_page": "announcements"}
    )


@app.get("/admin/announcements")
async def admin_announcements_page(request: Request):
    """Organiser announcement management console."""
    return templates.TemplateResponse(
        "admin_announcements.html", {"request": request, "active_page": "announcements"}
    )


@app.get("/safety")
async def safety_page(request: Request):
    """Participant safety page - check-in and SOS submission."""
    return templates.TemplateResponse(
        "safety.html", {"request": request, "active_page": "safety"}
    )


@app.get("/onboarding")
async def onboarding_page():
    """Onboarding page - collect participant info."""
    return FileResponse(_tpl("onboarding.html"))


@app.get("/avatar-setup")
async def avatar_setup_page():
    """Avatar setup page - customize avatar appearance."""
    return FileResponse(_tpl("avatar-setup.html"))


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": settings.app_name}
