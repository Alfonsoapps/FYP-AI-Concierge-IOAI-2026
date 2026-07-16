"""
Team Leader + Safety Router

Exposes the JSON API and page routes for the Team Leader + Safety module.

Page routes:
    GET /team/dashboard   - Team Leader Dashboard (cards, recent alerts, overview)
    GET /team/manage      - Team Management (member list + status filtering)
    GET /team/sos         - SOS Management (incoming alerts, details, history)

API routes:
    GET  /api/team/dashboard   - dashboard statistics + recent alerts + overview
    GET  /api/team/members     - members for a leader (optional status filter)
    POST /api/team/check-in    - record a participant check-in
    GET  /api/team/alerts      - SOS alerts for a leader (optional status filter)
    POST /api/team/sos         - create a new SOS alert
    PATCH /api/team/alerts/{id}/status - update an alert's status

Identity/role are supplied by the client (from localStorage), consistent with
the rest of the platform which has no server-side auth. The leader scope is
passed as a query/body field and defaults to the sample leader.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.services import team_safety_service as svc

logger = logging.getLogger(__name__)

# Anchor templates to the project root so rendering works regardless of the
# process working directory (e.g. under uvicorn's --reload subprocess).
import os
_TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "templates",
)
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

router = APIRouter(tags=["team-safety"])


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

class CheckInBody(BaseModel):
    participant_name: str = Field(..., min_length=1, max_length=100)
    location: Optional[str] = Field(default=None, max_length=200)


class SOSBody(BaseModel):
    participant_name: str = Field(..., min_length=1, max_length=100)
    location: Optional[str] = Field(default=None, max_length=200)
    message: Optional[str] = Field(default=None, max_length=1000)


class AlertStatusBody(BaseModel):
    status: str = Field(..., description="New, In Progress, or Resolved")


# ------------------------------------------------------------------
# Page routes
# ------------------------------------------------------------------

@router.get("/team/dashboard")
async def team_dashboard_page(request: Request):
    """Team Leader Dashboard page."""
    return templates.TemplateResponse(
        "team_dashboard.html", {"request": request, "active_page": "team"}
    )


@router.get("/team/manage")
async def team_manage_page(request: Request):
    """Team Management page."""
    return templates.TemplateResponse(
        "team_manage.html", {"request": request, "active_page": "team"}
    )


@router.get("/team/sos")
async def team_sos_page(request: Request):
    """SOS Management page."""
    return templates.TemplateResponse(
        "team_sos.html", {"request": request, "active_page": "team"}
    )


# ------------------------------------------------------------------
# API: reads
# ------------------------------------------------------------------

@router.get("/api/team/dashboard")
async def api_dashboard(leader: Optional[str] = Query(default=None)):
    """Dashboard statistics, recent alerts, and team overview for a leader."""
    try:
        return svc.get_dashboard(leader_name=leader)
    except Exception as e:  # pragma: no cover - defensive
        logger.error("dashboard failed: %s", e)
        raise HTTPException(status_code=500, detail="Could not load dashboard.")


@router.get("/api/team/members")
async def api_members(
    leader: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    """Members for a leader, optionally filtered by Member_Status."""
    try:
        return {"members": svc.list_members(leader_name=leader, status=status)}
    except svc.SafetyValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/team/alerts")
async def api_alerts(
    leader: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    """SOS alerts for a leader, optionally filtered by Alert_Status."""
    try:
        return {"alerts": svc.list_alerts(leader_name=leader, status=status)}
    except svc.SafetyValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/team/alerts/history")
async def api_alert_history(leader: Optional[str] = Query(default=None)):
    """Resolved alert history for a leader."""
    return {"alerts": svc.alert_history(leader_name=leader)}


@router.get("/api/team/alerts/{alert_id}")
async def api_alert_detail(alert_id: str):
    """Details for a single alert."""
    try:
        return svc.get_alert(alert_id)
    except svc.SafetyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ------------------------------------------------------------------
# API: mutations
# ------------------------------------------------------------------

@router.post("/api/team/check-in")
async def api_check_in(body: CheckInBody):
    """Record a participant check-in."""
    try:
        return svc.check_in(body.participant_name, location=body.location)
    except svc.SafetyValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except svc.SafetyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/team/sos")
async def api_create_sos(body: SOSBody):
    """Create a new SOS alert."""
    try:
        return svc.create_sos(
            body.participant_name, location=body.location, message=body.message
        )
    except svc.SafetyValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except svc.SafetyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/api/team/alerts/{alert_id}/status")
async def api_update_alert_status(alert_id: str, body: AlertStatusBody):
    """Update an alert's status (New -> In Progress -> Resolved)."""
    try:
        return svc.update_alert_status(alert_id, body.status)
    except svc.SafetyValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except svc.SafetyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
