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
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.routers import chat
from app.routers import tts
from app.routers import rag

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
templates = Jinja2Templates(directory="templates")

# Register API routers (chat, TTS, RAG)
app.include_router(chat.router)
app.include_router(tts.router)
app.include_router(rag.router)

# Serve static assets (CSS, JS, Live2D models, images)
app.mount("/static", StaticFiles(directory="static"), name="static")


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
    return FileResponse("templates/index.html")


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


@app.get("/onboarding")
async def onboarding_page():
    """Onboarding page - collect participant info."""
    return FileResponse("templates/onboarding.html")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": settings.app_name}
