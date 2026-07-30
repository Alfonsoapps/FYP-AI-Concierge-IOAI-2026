"""
Explore / Cultural Experience Router (F10 Requirements)

Endpoints:
    GET  /explore                       - Explore page
    GET  /api/explore/culture-guide     - Culture guide content
    GET  /api/explore/catalog           - Challenges and activities
    GET  /api/explore/progress          - User's progress and badges
    POST /api/explore/complete          - Mark an item as completed
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.services import explore_service as svc

logger = logging.getLogger(__name__)

import os
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TEMPLATES_DIR = os.path.join(_BASE_DIR, "templates")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

router = APIRouter(tags=["explore"])


class CompleteBody(BaseModel):
    participant_name: str = Field(..., min_length=1, max_length=100)
    item_id: str = Field(..., min_length=1, max_length=50)


# Page route
@router.get("/explore")
async def explore_page(request: Request):
    """Explore / Cultural Experience page."""
    return templates.TemplateResponse(
        request, "explore.html", {"request": request, "active_page": "explore"}
    )


# API routes
@router.get("/api/explore/culture-guide")
async def api_culture_guide():
    """Return the full culture guide (facts, food, etiquette)."""
    return svc.get_culture_guide()


@router.get("/api/explore/catalog")
async def api_catalog():
    """Return all exploration challenges and activities."""
    return svc.get_catalog()


@router.get("/api/explore/progress")
async def api_progress(user: Optional[str] = Query(default=None)):
    """Return a participant's progress and earned badges."""
    return svc.get_progress(user or "")


@router.post("/api/explore/complete")
async def api_complete(body: CompleteBody):
    """Mark a challenge or activity as completed."""
    try:
        return svc.complete_item(body.participant_name, body.item_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
