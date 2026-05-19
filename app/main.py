"""
AI Concierge - FastAPI Application Entry Point

This is the main entry point for the FastAPI application.
It sets up routing, static file serving, and the frontend.
"""

import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import get_settings
from app.routers import chat

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="AI Concierge backend powered by NVIDIA LLM",
    version="1.0.0",
)

# Register routers
app.include_router(chat.router)

# Serve static assets (CSS, JS, Live2D models, images)
# The "static" folder holds all frontend assets
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def serve_frontend():
    """Serve the frontend HTML page."""
    return FileResponse("templates/index.html")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": settings.app_name}
