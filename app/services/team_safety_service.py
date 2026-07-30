"""
Team Leader + Safety Service Module

Business logic and storage for the Team Leader + Safety module:
    - Teams, Team Members, and their safety status
    - Member check-ins
    - SOS emergency alerts and their New -> In Progress -> Resolved workflow
    - Aggregate dashboard statistics for a Team Leader

Storage note (intentional / temporary):
    Per the current project scope this uses a simple in-memory store guarded by
    a lock. It exposes plain module-level functions, mirroring the existing
    service pattern (see announcement_service / rag_service). The store is
    seeded with sample data on first use so the UI is immediately usable.

    Because storage is in-memory, data resets when the server restarts. The
    module is written so it can later be swapped for a persistent backend
    (SQLite/JSON) without changing the router or templates.
"""

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

# Member_Status values.
STATUS_SAFE = "Safe"
STATUS_PENDING = "Pending Check-in"
STATUS_SOS = "SOS Active"
MEMBER_STATUSES = [STATUS_SAFE, STATUS_PENDING, STATUS_SOS]

# Alert_Status values.
ALERT_NEW = "New"
ALERT_IN_PROGRESS = "In Progress"
ALERT_RESOLVED = "Resolved"
ALERT_STATUSES = [ALERT_NEW, ALERT_IN_PROGRESS, ALERT_RESOLVED]

# Alerts whose status counts as "active".
ACTIVE_ALERT_STATUSES = {ALERT_NEW, ALERT_IN_PROGRESS}

# Default Team Leader used when a caller does not specify one. Since the host
# app has no server-side accounts, this keeps the feature usable out of the box.
DEFAULT_LEADER = "Jordan Lee"

# ------------------------------------------------------------------
# In-memory store
# ------------------------------------------------------------------

_lock = threading.Lock()
_seeded = False

# id -> team dict
_teams: Dict[str, Dict] = {}
# id -> member dict
_members: Dict[str, Dict] = {}
# id -> alert dict
_alerts: Dict[str, Dict] = {}


# ------------------------------------------------------------------
# Errors
# ------------------------------------------------------------------

class SafetyValidationError(ValueError):
    """Raised when a request fails validation."""


class SafetyNotFoundError(LookupError):
    """Raised when a referenced record does not exist."""


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------

def _now_iso() -> str:
    """Current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _member_to_dict(m: Dict) -> Dict:
    """Return a shallow copy of a member record for output."""
    team = _teams.get(m["team_id"], {})
    return {
        "id": m["id"],
        "name": m["name"],
        "country": m["country"],
        "team_id": m["team_id"],
        "team_name": team.get("name", ""),
        "leader_name": team.get("leader_name", ""),
        "status": m["status"],
        "last_check_in": m["last_check_in"],
        "location": m["location"],
    }


def _alert_to_dict(a: Dict) -> Dict:
    """Return a shallow copy of an alert record for output."""
    member = _members.get(a["member_id"], {})
    return {
        "id": a["id"],
        "member_id": a["member_id"],
        "participant_name": a["participant_name"],
        "country": member.get("country", ""),
        "team_name": _teams.get(member.get("team_id", ""), {}).get("name", ""),
        "leader_name": a["leader_name"],
        "status": a["status"],
        "submitted_at": a["submitted_at"],
        "updated_at": a["updated_at"],
        "location": a["location"],
        "message": a["message"],
    }


def _find_member_by_name(name: str) -> Optional[Dict]:
    """Case-insensitive lookup of a member by participant name."""
    cleaned = (name or "").strip().lower()
    if not cleaned:
        return None
    for m in _members.values():
        if m["name"].strip().lower() == cleaned:
            return m
    return None


def _member_has_active_alert(member_id: str, exclude_alert_id: Optional[str] = None) -> bool:
    """True if the member has any alert still in an active status."""
    for a in _alerts.values():
        if a["member_id"] != member_id:
            continue
        if exclude_alert_id is not None and a["id"] == exclude_alert_id:
            continue
        if a["status"] in ACTIVE_ALERT_STATUSES:
            return True
    return False


# ------------------------------------------------------------------
# Seed data
# ------------------------------------------------------------------

def seed_sample_data(force: bool = False) -> None:
    """
    Populate the store with a sample team, members, and alerts so the UI is
    usable immediately. Idempotent: does nothing if data already exists unless
    force=True.
    """
    global _seeded
    with _lock:
        if _seeded and not force:
            return
        if force:
            _teams.clear()
            _members.clear()
            _alerts.clear()

        now = _now_iso()

        team_id = uuid.uuid4().hex
        _teams[team_id] = {
            "id": team_id,
            "name": "Team Singapore",
            "country": "Singapore",
            "leader_name": DEFAULT_LEADER,
        }

        sample_members = [
            {"name": "Alice Tan", "country": "Singapore", "status": STATUS_SAFE,
             "last_check_in": now, "location": "NUS Campus"},
            {"name": "Bob Lim", "country": "Singapore", "status": STATUS_PENDING,
             "last_check_in": None, "location": None},
            {"name": "Charlie Ng", "country": "Singapore", "status": STATUS_SAFE,
             "last_check_in": now, "location": "Marina Bay Sands"},
            {"name": "Divya Rao", "country": "Singapore", "status": STATUS_PENDING,
             "last_check_in": None, "location": None},
        ]

        member_ids = []
        for sm in sample_members:
            mid = uuid.uuid4().hex
            _members[mid] = {
                "id": mid,
                "name": sm["name"],
                "country": sm["country"],
                "team_id": team_id,
                "status": sm["status"],
                "last_check_in": sm["last_check_in"],
                "location": sm["location"],
            }
            member_ids.append(mid)

        # One resolved historical alert for Alice.
        alert_id = uuid.uuid4().hex
        _alerts[alert_id] = {
            "id": alert_id,
            "member_id": member_ids[0],
            "participant_name": "Alice Tan",
            "leader_name": DEFAULT_LEADER,
            "status": ALERT_RESOLVED,
            "submitted_at": now,
            "updated_at": now,
            "location": "NUS Campus",
            "message": "Felt unwell, now recovered.",
        }

        _seeded = True
    logger.info("Team/Safety sample data seeded (leader=%s).", DEFAULT_LEADER)


def _ensure_seeded() -> None:
    if not _seeded:
        seed_sample_data()


# ------------------------------------------------------------------
# Member queries
# ------------------------------------------------------------------

def list_members(leader_name: Optional[str] = None, status: Optional[str] = None) -> List[Dict]:
    """
    Return members for a Team Leader, optionally filtered by Member_Status.

    Args:
        leader_name: Team Leader to scope to. Defaults to DEFAULT_LEADER.
        status: Optional Member_Status filter. Must be a valid status.
    """
    _ensure_seeded()
    leader = (leader_name or DEFAULT_LEADER).strip()

    if status is not None and status not in MEMBER_STATUSES:
        raise SafetyValidationError(f"Invalid status filter: {status!r}")

    with _lock:
        result = []
        for m in _members.values():
            team = _teams.get(m["team_id"], {})
            if team.get("leader_name", "").strip().lower() != leader.lower():
                continue
            if status is not None and m["status"] != status:
                continue
            result.append(_member_to_dict(m))

    result.sort(key=lambda x: x["name"].lower())
    return result


# ------------------------------------------------------------------
# Alert queries
# ------------------------------------------------------------------

def list_alerts(leader_name: Optional[str] = None, status: Optional[str] = None) -> List[Dict]:
    """
    Return SOS alerts for a Team Leader (most recent first), optionally filtered
    by Alert_Status.
    """
    _ensure_seeded()
    leader = (leader_name or DEFAULT_LEADER).strip()

    if status is not None and status not in ALERT_STATUSES:
        raise SafetyValidationError(f"Invalid alert status filter: {status!r}")

    with _lock:
        result = [
            _alert_to_dict(a)
            for a in _alerts.values()
            if a["leader_name"].strip().lower() == leader.lower()
            and (status is None or a["status"] == status)
        ]

    result.sort(key=lambda x: x["submitted_at"], reverse=True)
    return result


def get_alert(alert_id: str) -> Dict:
    """Return a single alert by id, or raise if not found."""
    _ensure_seeded()
    with _lock:
        a = _alerts.get(alert_id)
        if a is None:
            raise SafetyNotFoundError(f"Alert '{alert_id}' not found.")
        return _alert_to_dict(a)


def alert_history(leader_name: Optional[str] = None) -> List[Dict]:
    """Return only Resolved alerts for a Team Leader (most recent first)."""
    return list_alerts(leader_name=leader_name, status=ALERT_RESOLVED)


# ------------------------------------------------------------------
# Dashboard statistics
# ------------------------------------------------------------------

def get_dashboard(leader_name: Optional[str] = None, recent_limit: int = 5) -> Dict:
    """
    Compute dashboard statistics, recent alerts, and team overview for a leader.
    """
    _ensure_seeded()
    leader = (leader_name or DEFAULT_LEADER).strip()

    members = list_members(leader_name=leader)
    alerts = list_alerts(leader_name=leader)

    total = len(members)
    safe = sum(1 for m in members if m["status"] == STATUS_SAFE)
    attention = sum(
        1 for m in members if m["status"] in (STATUS_PENDING, STATUS_SOS)
    )
    active_sos = sum(1 for a in alerts if a["status"] in ACTIVE_ALERT_STATUSES)

    return {
        "leader_name": leader,
        "stats": {
            "total_members": total,
            "checked_in": safe,
            "requiring_attention": attention,
            "active_sos": active_sos,
        },
        "recent_alerts": alerts[:recent_limit],
        "team_overview": [
            {"name": m["name"], "status": m["status"]} for m in members
        ],
    }


# ------------------------------------------------------------------
# Mutations: check-in
# ------------------------------------------------------------------

def check_in(participant_name: str, location: Optional[str] = None) -> Dict:
    """
    Record a Participant check-in: set status to Safe, stamp the check-in time,
    and store location if provided.

    Raises:
        SafetyValidationError: if the name is missing.
        SafetyNotFoundError: if the participant is not a recognized member.
    """
    _ensure_seeded()
    name = (participant_name or "").strip()
    if not name:
        raise SafetyValidationError("participant_name is required.")

    with _lock:
        member = _find_member_by_name(name)
        if member is None:
            raise SafetyNotFoundError(f"'{name}' is not a recognized team member.")

        member["status"] = STATUS_SAFE
        member["last_check_in"] = _now_iso()
        if location and location.strip():
            member["location"] = location.strip()

        result = _member_to_dict(member)

    logger.info("Check-in recorded for %s", name)
    return result


# ------------------------------------------------------------------
# Mutations: SOS submission
# ------------------------------------------------------------------

def create_sos(
    participant_name: str,
    location: Optional[str] = None,
    message: Optional[str] = None,
) -> Dict:
    """
    Create a new SOS alert (status New) for a recognized member and set that
    member's status to SOS Active.

    Raises:
        SafetyValidationError: if the name is missing.
        SafetyNotFoundError: if the participant is not a recognized member.
    """
    _ensure_seeded()
    name = (participant_name or "").strip()
    if not name:
        raise SafetyValidationError("participant_name is required.")

    with _lock:
        member = _find_member_by_name(name)
        if member is None:
            raise SafetyNotFoundError(f"'{name}' is not a recognized team member.")

        team = _teams.get(member["team_id"], {})
        now = _now_iso()
        alert_id = uuid.uuid4().hex
        loc = location.strip() if location and location.strip() else member.get("location")

        _alerts[alert_id] = {
            "id": alert_id,
            "member_id": member["id"],
            "participant_name": member["name"],
            "leader_name": team.get("leader_name", DEFAULT_LEADER),
            "status": ALERT_NEW,
            "submitted_at": now,
            "updated_at": now,
            "location": loc,
            "message": (message or "").strip() or None,
        }

        # Reflect the emergency on the member's own status.
        member["status"] = STATUS_SOS

        result = _alert_to_dict(_alerts[alert_id])

    logger.info("SOS alert created for %s (id=%s)", name, alert_id)
    return result


# ------------------------------------------------------------------
# Mutations: alert status workflow
# ------------------------------------------------------------------

def update_alert_status(alert_id: str, new_status: str) -> Dict:
    """
    Advance an alert through its lifecycle. When an alert becomes Resolved and
    the member has no other active alert, the member's status moves back to
    Pending Check-in.

    Raises:
        SafetyValidationError: if new_status is invalid.
        SafetyNotFoundError: if the alert id does not exist.
    """
    _ensure_seeded()
    if new_status not in ALERT_STATUSES:
        raise SafetyValidationError(f"Invalid alert status: {new_status!r}")

    with _lock:
        alert = _alerts.get(alert_id)
        if alert is None:
            raise SafetyNotFoundError(f"Alert '{alert_id}' not found.")

        alert["status"] = new_status
        alert["updated_at"] = _now_iso()

        # When resolved, ease the member's status if nothing else is active.
        if new_status == ALERT_RESOLVED:
            member = _members.get(alert["member_id"])
            if member is not None and not _member_has_active_alert(
                member["id"], exclude_alert_id=alert_id
            ):
                if member["status"] == STATUS_SOS:
                    member["status"] = STATUS_PENDING

        result = _alert_to_dict(alert)

    logger.info("Alert %s status -> %s", alert_id, new_status)
    return result


# ------------------------------------------------------------------
# Registration: automatic team creation during onboarding
# ------------------------------------------------------------------

def register_participant(name: str, country: str, role: str) -> Dict:
    """
    Register a participant into their country's delegation team.
    If the team doesn't exist, creates it. If the participant is already
    registered, returns their existing record.

    Team Leaders become the leader of their country's team.
    Students and Observers become members.
    """
    _ensure_seeded()
    clean_name = (name or "").strip()
    clean_country = (country or "").strip()
    clean_role = (role or "").strip()

    if not clean_name:
        raise SafetyValidationError("name is required.")
    if not clean_country:
        raise SafetyValidationError("country is required.")

    with _lock:
        # Check if already registered
        existing = _find_member_by_name(clean_name)
        if existing:
            return _member_to_dict(existing)

        # Find or create the country's team
        team_id = None
        for t in _teams.values():
            if t["country"].strip().lower() == clean_country.lower():
                team_id = t["id"]
                # If registering as Team Leader, update the team's leader
                if clean_role == "Team Leader":
                    t["leader_name"] = clean_name
                break

        if team_id is None:
            team_id = uuid.uuid4().hex
            leader = clean_name if clean_role == "Team Leader" else DEFAULT_LEADER
            _teams[team_id] = {
                "id": team_id,
                "name": f"Team {clean_country}",
                "country": clean_country,
                "leader_name": leader,
            }

        # Create the member record
        mid = uuid.uuid4().hex
        _members[mid] = {
            "id": mid,
            "name": clean_name,
            "country": clean_country,
            "team_id": team_id,
            "status": STATUS_PENDING,
            "last_check_in": None,
            "location": None,
        }

        result = _member_to_dict(_members[mid])

    logger.info("Registered participant: %s (%s, %s)", clean_name, clean_country, clean_role)
    return result


def get_my_team(participant_name: str) -> Dict:
    """
    Return the team roster for a participant (read-only view).
    Returns the team info and all members of the same team.
    """
    _ensure_seeded()
    clean_name = (participant_name or "").strip()
    if not clean_name:
        raise SafetyValidationError("participant_name is required.")

    with _lock:
        member = _find_member_by_name(clean_name)
        if member is None:
            raise SafetyNotFoundError(f"'{clean_name}' is not a registered team member.")

        team = _teams.get(member["team_id"], {})
        teammates = [
            _member_to_dict(m) for m in _members.values()
            if m["team_id"] == member["team_id"]
        ]

    teammates.sort(key=lambda x: x["name"].lower())
    return {
        "team_name": team.get("name", ""),
        "country": team.get("country", ""),
        "leader_name": team.get("leader_name", ""),
        "members": teammates,
    }
