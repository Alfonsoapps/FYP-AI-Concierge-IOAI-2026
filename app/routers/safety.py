"""
Safety & Emergency Router (F6 Requirements)

Endpoints:
    GET  /api/safety/emergency-contacts  - Emergency numbers
    GET  /api/safety/medical-facilities  - Nearby medical facilities
    POST /api/team/lost-reports          - Report a lost participant
    GET  /api/team/lost-reports          - View lost reports
    PATCH /api/team/lost-reports/{id}    - Update report status
    GET  /safety-info                    - Safety info page
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.services import safety_service as svc

logger = logging.getLogger(__name__)

import os
_TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "templates",
)
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

router = APIRouter(tags=["safety"])


class LostReportBody(BaseModel):
    reporter_name: str = Field(..., min_length=1, max_length=100)
    missing_name: str = Field(..., min_length=1, max_length=100)
    last_seen_location: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=500)


class ReportStatusBody(BaseModel):
    status: str = Field(..., description="Reported, Searching, or Found")


# Page route
@router.get("/safety-info")
async def safety_info_page(request: Request):
    """Safety information page."""
    return templates.TemplateResponse(
        "safety_info.html", {"request": request, "active_page": "safety-info"}
    )


# API routes
@router.get("/api/safety/emergency-contacts")
async def api_emergency_contacts():
    """Return all emergency contact numbers."""
    return {"contacts": svc.get_emergency_contacts()}


@router.get("/api/safety/medical-facilities")
async def api_medical_facilities():
    """Return medical facilities near event venues."""
    return {"facilities": svc.get_medical_facilities()}


@router.post("/api/team/lost-reports")
async def api_create_lost_report(body: LostReportBody):
    """Report a lost participant."""
    try:
        return svc.create_lost_report(
            reporter_name=body.reporter_name,
            missing_name=body.missing_name,
            last_seen_location=body.last_seen_location,
            description=body.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/team/lost-reports")
async def api_list_lost_reports(status: Optional[str] = Query(default=None)):
    """List all lost-participant reports."""
    try:
        return {"reports": svc.get_lost_reports(status=status)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/api/team/lost-reports/{report_id}")
async def api_update_lost_report(report_id: str, body: ReportStatusBody):
    """Update the status of a lost report."""
    try:
        return svc.update_lost_report_status(report_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
