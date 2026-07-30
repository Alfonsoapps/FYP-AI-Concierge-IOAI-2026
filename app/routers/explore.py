"""
Explore Router (Participant Experience Features)

Exposes the JSON API for the "Explore" tab and its page route.

    GET  /explore                       - Explore page (page route)
    GET  /api/explore/culture-guide     - culture facts, food recs, etiquette tips
    GET  /api/explore/catalog           - static challenge/activity catalog
    GET  /api/explore/progress          - a participant's completions + badges
    POST /api/explore/complete          - mark a catalog item complete

Identity is supplied by the client (from localStorage) since the host app has
no server-side auth, consistent with the rest of the platform.
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.services import explore_service as svc

logger = logging.getLogger(__name__)

# Anchor templates to the project root so rendering works regardless of the
# process working directory (e.g. under uvicorn's --reload subprocess).
_TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "templates",
)
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

router = APIRouter(tags=["explore"])


class CompleteItemBody(BaseModel):
    participant_name: str = Field(..., min_length=1, max_length=100)
    item_id: str = Field(..., min_length=1, max_length=100)


# ------------------------------------------------------------------
# Page route
# ------------------------------------------------------------------

@router.get("/explore")
async def explore_page(request: Request):
    """Explore page - Singapore culture guide, challenges, and badges."""
    return templates.TemplateResponse(
        request, "explore.html", {"request": request, "active_page": "explore"}
    )


# ------------------------------------------------------------------
# API
# ------------------------------------------------------------------

@router.get("/api/explore/culture-guide")
async def api_culture_guide():
    """Culture facts, food recommendations, and etiquette tips (F10R1-F10R3)."""
    return svc.get_culture_guide()


@router.get("/api/explore/catalog")
async def api_catalog():
    """Static catalog of exploration challenges and cultural learning activities."""
    return {"items": svc.get_catalog()}


@router.get("/api/explore/progress")
async def api_progress(participant_name: str = Query(...)):
    """A participant's completion status across the catalog, plus earned badges."""
    try:
        return svc.get_progress(participant_name)
    except svc.ExploreValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/explore/complete")
async def api_complete_item(body: CompleteItemBody):
    """Mark a challenge or cultural activity complete, awarding its badge."""
    try:
        return svc.complete_item(body.participant_name, body.item_id)
    except svc.ExploreValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except svc.ExploreNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
