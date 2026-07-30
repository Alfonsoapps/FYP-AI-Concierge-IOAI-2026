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

class RegisterBody(BaseModel):
    participant_name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(..., min_length=1, max_length=100)
    country: str = Field(..., min_length=1, max_length=100)


class CheckInBody(BaseModel):
    participant_name: str = Field(..., min_length=1, max_length=100)
    location: Optional[str] = Field(default=None, max_length=200)


class SOSBody(BaseModel):
    participant_name: str = Field(..., min_length=1, max_length=100)
    location: Optional[str] = Field(default=None, max_length=200)
    message: Optional[str] = Field(default=None, max_length=1000)


class AlertStatusBody(BaseModel):
    status: str = Field(..., description="New, In Progress, or Resolved")


class LostReportBody(BaseModel):
    participant_name: str = Field(..., min_length=1, max_length=100)
    reported_by: str = Field(..., min_length=1, max_length=100)
    last_known_location: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)


class LostReportStatusBody(BaseModel):
    status: str = Field(..., description="Reported, Searching, or Found")


# ------------------------------------------------------------------
# Page routes
# ------------------------------------------------------------------

@router.get("/team/dashboard")
async def team_dashboard_page(request: Request):
    """Team Leader Dashboard page."""
    return templates.TemplateResponse(
        request, "team_dashboard.html", {"request": request, "active_page": "team"}
    )


@router.get("/team/manage")
async def team_manage_page(request: Request):
    """Team Management page."""
    return templates.TemplateResponse(
        request, "team_manage.html", {"request": request, "active_page": "team"}
    )


@router.get("/team/sos")
async def team_sos_page(request: Request):
    """SOS Management page."""
    return templates.TemplateResponse(
        request, "team_sos.html", {"request": request, "active_page": "team"}
    )


# ------------------------------------------------------------------
# API: registration (real participants join their delegation roster)
# ------------------------------------------------------------------

@router.post("/api/team/register")
async def api_register_participant(body: RegisterBody):
    """
    Register a real, onboarded participant into their country's delegation
    roster. Called after onboarding (and safe to call again on every visit)
    so team rosters reflect actual signed-in participants rather than fixture
    data.
    """
    try:
        return svc.register_participant(
            body.participant_name, role=body.role, country=body.country
        )
    except svc.SafetyValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/team/my-team")
async def api_my_team(participant_name: str = Query(...)):
    """
    Return the delegation team (with roster) for a non-leader participant,
    so they can see their own team members on the Team page.
    """
    team = svc.get_team_for_member(participant_name)
    if team is None:
        raise HTTPException(status_code=404, detail="No team found for this participant yet.")
    return team


# ------------------------------------------------------------------
# API: reads
# ------------------------------------------------------------------

@router.get("/api/team/dashboard")
async def api_dashboard(leader: Optional[str] = Query(default=None)):
    """Dashboard statistics, recent alerts, welfare alerts, and team overview
    for a leader (Requirements F7R4, F7R5)."""
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


# ------------------------------------------------------------------
# API: lost participant reporting (Requirement F6R5)
# ------------------------------------------------------------------

@router.post("/api/team/lost-reports")
async def api_create_lost_report(body: LostReportBody):
    """Report a participant as lost/missing."""
    try:
        return svc.create_lost_report(
            body.participant_name,
            reported_by=body.reported_by,
            last_known_location=body.last_known_location,
            description=body.description,
        )
    except svc.SafetyValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/team/lost-reports")
async def api_list_lost_reports(
    leader: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    """Lost-participant reports for a leader, optionally filtered by status."""
    try:
        return {"reports": svc.list_lost_reports(leader_name=leader, status=status)}
# Registration + My Team (F5 / F7 requirements)
# ------------------------------------------------------------------

class RegisterBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    country: str = Field(..., min_length=1, max_length=100)
    role: str = Field(..., min_length=1, max_length=50)


@router.post("/api/team/register")
async def api_register(body: RegisterBody):
    """Register a participant into their country's delegation team (called during onboarding)."""
    try:
        return svc.register_participant(body.name, body.country, body.role)
    except svc.SafetyValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/api/team/lost-reports/{report_id}/status")
async def api_update_lost_report_status(report_id: str, body: LostReportStatusBody):
    """Update a lost-participant report's status (Reported -> Searching -> Found)."""
    try:
        return svc.update_lost_report_status(report_id, body.status)
@router.get("/api/team/my-team")
async def api_my_team(user: Optional[str] = Query(default=None)):
    """Return the team roster for a participant (read-only view)."""
    if not user:
        raise HTTPException(status_code=400, detail="user query parameter required.")
    try:
        return svc.get_my_team(user)
    except svc.SafetyValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except svc.SafetyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ------------------------------------------------------------------
# API: emergency contacts + nearby medical facilities (F6R1, F6R6)
# ------------------------------------------------------------------

@router.get("/api/safety/emergency-contacts")
async def api_emergency_contacts():
    """Static emergency contact directory."""
    return {"contacts": svc.get_emergency_contacts()}


@router.get("/api/safety/medical-facilities")
async def api_medical_facilities(near: Optional[str] = Query(default=None)):
    """Nearby medical facilities, optionally filtered by venue."""
    return {"facilities": svc.get_medical_facilities(near=near)}


# ------------------------------------------------------------------
# API: delegation schedule + announcement acknowledgement monitoring
# (Requirements F7R1, F7R3)
# ------------------------------------------------------------------

@router.get("/api/team/delegation-audiences")
async def api_delegation_audiences(leader: Optional[str] = Query(default=None)):
    """
    Audience_Category values present in a Team Leader's delegation, so the
    frontend can filter the schedule and announcements down to exactly this
    delegation's relevant categories (Requirement F7R1, F7R2).
    """
    return {"audience_categories": svc.get_delegation_audience_categories(leader_name=leader)}


@router.get("/api/team/announcements/{announcement_id}/ack-status")
async def api_delegation_ack_status(
    announcement_id: str,
    leader: Optional[str] = Query(default=None),
):
    """
    Per-participant read/acknowledged status for a critical announcement,
    scoped to a Team Leader's own delegation members (Requirement F7R3).
    Unlike the organiser-only aggregate `/api/admin/announcements/{id}/stats`,
    this always reports on the caller's own participants only.
    """
    from app.services import announcement_service as ann_svc

    members = svc.list_members(leader_name=leader)
    participant_names = [m["name"] for m in members]
    try:
        return {
            "announcement_id": announcement_id,
            "participants": ann_svc.get_ack_status_for_participants(
                announcement_id, participant_names
            ),
        }
    except ann_svc.AnnouncementNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
