"""
Announcements Router

Exposes the JSON API for the Announcements module:

User / participant endpoints:
    GET  /api/announcements                 - published announcements for a user's role
    POST /api/announcements/{id}/read        - mark an announcement read
    POST /api/announcements/{id}/acknowledge - acknowledge a critical announcement
    GET  /api/notifications                  - unread count for the notification bell
    GET  /api/announcements/latest           - latest published (used by AI concierge)

Organiser / admin endpoints (management):
    GET    /api/admin/announcements          - list all (drafts + published)
    POST   /api/admin/announcements          - create (draft)
    GET    /api/admin/announcements/{id}     - get one
    PUT    /api/admin/announcements/{id}     - update
    DELETE /api/admin/announcements/{id}     - delete
    POST   /api/admin/announcements/{id}/publish - publish
    GET    /api/admin/announcements/{id}/stats   - statistics

Identity/role are supplied by the client (from localStorage) since the host app
has no server-side auth. Roles are normalized server-side.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services import announcement_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["announcements"])


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

class AnnouncementIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=5000)
    category: str = Field(..., min_length=1, max_length=60)
    priority: str = Field(..., description="Normal or Critical")
    target_audience: str = Field(..., description="One of the fixed audience categories")
    ack_required: bool = Field(default=False)


class AnnouncementOut(BaseModel):
    id: str
    title: str
    message: str
    category: str
    priority: str
    target_audience: str
    ack_required: bool
    status: str
    created_at: str
    published_at: Optional[str] = None
    read_at: Optional[str] = None
    acknowledged_at: Optional[str] = None


class ActorBody(BaseModel):
    """Client-supplied identity for tracking/authorization."""
    participant_name: Optional[str] = Field(default=None, max_length=100)
    role: Optional[str] = Field(default=None, max_length=100)


def _require_organiser(role: Optional[str]) -> None:
    if not svc.is_organiser(role):
        raise HTTPException(status_code=403, detail="Not authorized: organisers only.")


# ------------------------------------------------------------------
# User endpoints
# ------------------------------------------------------------------

@router.get("/api/announcements", response_model=List[AnnouncementOut])
async def list_user_announcements(
    role: Optional[str] = Query(default=None),
    user: Optional[str] = Query(default=None),
):
    """Published announcements targeted to the caller's resolved audience."""
    try:
        return svc.list_for_user(role=role, participant_name=user)
    except Exception as e:  # pragma: no cover - defensive
        logger.error("list_user_announcements failed: %s", e)
        raise HTTPException(status_code=500, detail="Could not load announcements.")


@router.post("/api/announcements/{announcement_id}/read")
async def read_announcement(announcement_id: str, body: ActorBody):
    """Record that the caller has read the announcement."""
    try:
        return svc.mark_read(announcement_id, body.participant_name)
    except svc.AnnouncementValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except svc.AnnouncementNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except svc.AnnouncementStateError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/api/announcements/{announcement_id}/acknowledge")
async def acknowledge_announcement(announcement_id: str, body: ActorBody):
    """Acknowledge a critical announcement."""
    try:
        return svc.acknowledge(announcement_id, body.participant_name)
    except svc.AnnouncementValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except svc.AnnouncementNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/notifications")
async def notifications(
    role: Optional[str] = Query(default=None),
    user: Optional[str] = Query(default=None),
):
    """Unread announcement count for the notification bell."""
    try:
        count = svc.unread_count(role=role, participant_name=user)
        return {"unread": count}
    except Exception as e:  # pragma: no cover - defensive
        logger.error("notifications failed: %s", e)
        # Fail soft: the bell should never break a page.
        return {"unread": 0}


@router.get("/api/announcements/latest")
async def latest_announcements(
    audience: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
):
    """
    Latest published announcements for programmatic access (AI concierge).
    Accepts either a resolved `audience` category or a raw `role` to normalize.
    """
    resolved = audience
    if resolved is None and role is not None:
        resolved = svc.normalize_role(role)
    try:
        items = svc.latest_published(audience=resolved, limit=limit)
        return {"count": len(items), "announcements": items}
    except svc.AnnouncementValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------------
# Admin endpoints
# ------------------------------------------------------------------

@router.get("/api/admin/announcements", response_model=List[AnnouncementOut])
async def admin_list(role: Optional[str] = Query(default=None)):
    _require_organiser(role)
    return svc.list_all_announcements()


@router.post("/api/admin/announcements", response_model=AnnouncementOut)
async def admin_create(payload: AnnouncementIn, role: Optional[str] = Query(default=None)):
    _require_organiser(role)
    try:
        return svc.create_announcement(
            title=payload.title,
            message=payload.message,
            category=payload.category,
            priority=payload.priority,
            target_audience=payload.target_audience,
            ack_required=payload.ack_required,
        )
    except svc.AnnouncementValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/admin/announcements/{announcement_id}", response_model=AnnouncementOut)
async def admin_get(announcement_id: str, role: Optional[str] = Query(default=None)):
    _require_organiser(role)
    try:
        return svc.get_announcement(announcement_id)
    except svc.AnnouncementNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/api/admin/announcements/{announcement_id}", response_model=AnnouncementOut)
async def admin_update(
    announcement_id: str,
    payload: AnnouncementIn,
    role: Optional[str] = Query(default=None),
):
    _require_organiser(role)
    try:
        return svc.update_announcement(
            announcement_id,
            title=payload.title,
            message=payload.message,
            category=payload.category,
            priority=payload.priority,
            target_audience=payload.target_audience,
            ack_required=payload.ack_required,
        )
    except svc.AnnouncementNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except svc.AnnouncementValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/admin/announcements/{announcement_id}")
async def admin_delete(announcement_id: str, role: Optional[str] = Query(default=None)):
    _require_organiser(role)
    try:
        svc.delete_announcement(announcement_id)
        return {"deleted": announcement_id}
    except svc.AnnouncementNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/admin/announcements/{announcement_id}/publish", response_model=AnnouncementOut)
async def admin_publish(announcement_id: str, role: Optional[str] = Query(default=None)):
    _require_organiser(role)
    try:
        return svc.publish_announcement(announcement_id)
    except svc.AnnouncementNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except svc.AnnouncementStateError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/api/admin/announcements/{announcement_id}/stats")
async def admin_stats(announcement_id: str, role: Optional[str] = Query(default=None)):
    _require_organiser(role)
    try:
        return svc.get_statistics(announcement_id)
    except svc.AnnouncementNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
