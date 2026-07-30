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
    service pattern (see announcement_service / rag_service).

    Because storage is in-memory, data resets when the server restarts. The
    module is written so it can later be swapped for a persistent backend
    (SQLite/JSON) without changing the router or templates.

Real rosters vs. fixture data:
    Production no longer seeds fake team members. Delegation teams and their
    rosters are populated from real onboarded participants via
    `register_participant`, called when someone completes onboarding (or
    revisits a Team page) with a name, role, and country. A Team Leader's
    registration creates/claims the delegation team for their country; any
    other role joins that country's roster as a member. `seed_sample_data`
    still exists so automated tests have deterministic fixture data, but it
    is no longer invoked automatically on application startup.
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

# Lost_Report_Status values (F6R5: lost participant reporting workflow).
LOST_REPORTED = "Reported"
LOST_SEARCHING = "Searching"
LOST_FOUND = "Found"
LOST_REPORT_STATUSES = [LOST_REPORTED, LOST_SEARCHING, LOST_FOUND]
ACTIVE_LOST_REPORT_STATUSES = {LOST_REPORTED, LOST_SEARCHING}

# Emergency contact directory (F6R1). Static reference data for the event in
# Singapore; organisers can extend this list as the event's contacts change.
EMERGENCY_CONTACTS = [
    {"label": "Singapore Police", "phone": "999", "category": "Police", "notes": "Life-threatening emergencies and crime."},
    {"label": "Singapore Civil Defence Force (Ambulance / Fire)", "phone": "995", "category": "Medical/Fire", "notes": "Medical emergencies, fire, and rescue."},
    {"label": "Non-Emergency Ambulance", "phone": "1777", "category": "Medical", "notes": "Non-urgent medical transport."},
    {"label": "IOAI 2027 Organiser Hotline", "phone": "+65 6000 2027", "category": "Event", "notes": "24/7 hotline for participant emergencies and urgent event issues."},
    {"label": "Your Team Leader", "phone": "See Team tab", "category": "Event", "notes": "First point of contact for check-ins, SOS, and day-to-day issues."},
]

# Nearby medical facility directory (F6R6). Static reference data the AI
# concierge can recommend from when a user describes a medical concern.
MEDICAL_FACILITIES = [
    {"name": "National University Hospital", "address": "5 Lower Kent Ridge Rd, Singapore 119074", "phone": "+65 6779 5555", "category": "Hospital (24hr Emergency)", "near": "National University of Singapore"},
    {"name": "Singapore General Hospital", "address": "Outram Rd, Singapore 169608", "phone": "+65 6222 3322", "category": "Hospital (24hr Emergency)", "near": "Outram / City area"},
    {"name": "Raffles Hospital", "address": "585 North Bridge Rd, Singapore 188770", "phone": "+65 6311 1111", "category": "Hospital (24hr Emergency)", "near": "Marina Bay Sands / City area"},
    {"name": "SUTD Student Health Clinic", "address": "8 Somapah Rd, Singapore 487372", "phone": "+65 6303 6600", "category": "Clinic", "near": "Singapore University of Technology and Design"},
    {"name": "NUS University Health Centre", "address": "21 Lower Kent Ridge Rd, Singapore 119077", "phone": "+65 6516 2222", "category": "Clinic", "near": "National University of Singapore"},
]

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
# id -> lost participant report dict
_lost_reports: Dict[str, Dict] = {}


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
        # Audience_Category of this delegation member, so a Team Leader's
        # dashboard can look up their delegation's schedule and announcement
        # acknowledgement status (Requirements F7R1, F7R3).
        "audience_category": m.get("audience_category", "Students"),
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


def _normalize_country_key(country: str) -> str:
    """Case/whitespace-insensitive key used to group members into one team."""
    return country.strip().lower()


def _find_team_by_country(country_key: str) -> Optional[Dict]:
    """Case-insensitive lookup of a delegation team by its country key."""
    for t in _teams.values():
        if _normalize_country_key(t["country"]) == country_key:
            return t
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


def _lost_report_to_dict(r: Dict) -> Dict:
    """Return a shallow copy of a lost-participant report record for output."""
    return {
        "id": r["id"],
        "participant_name": r["participant_name"],
        "reported_by": r["reported_by"],
        "leader_name": r["leader_name"],
        "status": r["status"],
        "last_known_location": r["last_known_location"],
        "description": r["description"],
        "reported_at": r["reported_at"],
        "updated_at": r["updated_at"],
    }


# ------------------------------------------------------------------
# Seed data
# ------------------------------------------------------------------

def seed_sample_data(force: bool = False) -> None:
    """
    Populate the store with a sample team, members, and alerts. Used only by
    automated tests that need deterministic fixture data; production no
    longer calls this on startup (real rosters come from `register_participant`
    via onboarding). Idempotent: does nothing if data already exists unless
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
            _lost_reports.clear()

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
             "last_check_in": now, "location": "NUS Campus", "audience_category": "Students"},
            {"name": "Bob Lim", "country": "Singapore", "status": STATUS_PENDING,
             "last_check_in": None, "location": None, "audience_category": "Students"},
            {"name": "Charlie Ng", "country": "Singapore", "status": STATUS_SAFE,
             "last_check_in": now, "location": "Marina Bay Sands", "audience_category": "Students"},
            {"name": "Divya Rao", "country": "Singapore", "status": STATUS_PENDING,
             "last_check_in": None, "location": None, "audience_category": "Students"},
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
                "audience_category": sm["audience_category"],
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
    """
    No-op guard retained so query functions do not error before any
    participant has registered. Production rosters build up organically via
    `register_participant`; this no longer auto-seeds fake data.
    """
    return


# ------------------------------------------------------------------
# Real participant registration (replaces fixture rostering in production)
# ------------------------------------------------------------------

def register_participant(
    participant_name: str,
    role: str,
    country: str,
    audience_category: Optional[str] = None,
) -> Dict:
    """
    Register a real, onboarded participant into their country's delegation
    team roster.

    - If `role` is "Team Leader": creates the delegation team for `country`
      if it doesn't exist yet, and sets/claims this participant as its leader.
    - Otherwise: joins (or updates) this participant as a member of that
      country's delegation team. If the team does not exist yet (no leader
      has registered), a placeholder team is created using DEFAULT_LEADER so
      the member still has somewhere to belong; the team leader name is
      corrected automatically once a real Team Leader registers for that
      country.

    Idempotent: calling this again for the same name updates their role/team
    assignment rather than creating a duplicate.

    Raises:
        SafetyValidationError: if participant_name, role, or country is missing.
    """
    name = (participant_name or "").strip()
    clean_role = (role or "").strip()
    clean_country = (country or "").strip()
    if not name:
        raise SafetyValidationError("participant_name is required.")
    if not clean_role:
        raise SafetyValidationError("role is required.")
    if not clean_country:
        raise SafetyValidationError("country is required.")

    country_key = _normalize_country_key(clean_country)
    is_leader = clean_role.lower() == "team leader"

    with _lock:
        team = _find_team_by_country(country_key)
        if team is None:
            team_id = uuid.uuid4().hex
            team = {
                "id": team_id,
                "name": f"Team {clean_country}",
                "country": clean_country,
                # Distinct per-country placeholder until a real Team Leader
                # registers, so unclaimed delegations from different
                # countries never collide under one shared leader name.
                "leader_name": name if is_leader else f"(unassigned leader — {clean_country})",
            }
            _teams[team_id] = team
        elif is_leader:
            # A real Team Leader registering claims/updates leadership of
            # their country's delegation.
            team["leader_name"] = name

        existing = _find_member_by_name(name)
        if existing is not None:
            existing["team_id"] = team["id"]
            existing["country"] = clean_country
            if audience_category:
                existing["audience_category"] = audience_category
            result = _member_to_dict(existing)
        else:
            mid = uuid.uuid4().hex
            _members[mid] = {
                "id": mid,
                "name": name,
                "country": clean_country,
                "team_id": team["id"],
                "status": STATUS_PENDING,
                "last_check_in": None,
                "location": None,
                "audience_category": audience_category or (
                    "Team Leaders" if is_leader else "Students"
                ),
            }
            result = _member_to_dict(_members[mid])

    logger.info("Registered participant %s (role=%s, country=%s)", name, clean_role, clean_country)
    return result


def get_team_for_member(participant_name: str) -> Optional[Dict]:
    """
    Return the delegation team (with roster) that a given participant
    belongs to, or None if they have not registered / have no team yet.
    Used by non-leader participants to see their own team on the Team page.
    """
    member = _find_member_by_name(participant_name)
    if member is None:
        return None
    team = _teams.get(member["team_id"])
    if team is None:
        return None
    return {
        "id": team["id"],
        "name": team["name"],
        "country": team["country"],
        "leader_name": team["leader_name"],
        "members": list_members(leader_name=team["leader_name"]),
    }


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
    Compute dashboard statistics, recent alerts, welfare alerts, and team
    overview for a leader (Requirements F7R4, F7R5: delegation summary
    dashboard including welfare-related alerts).
    """
    _ensure_seeded()
    leader = (leader_name or DEFAULT_LEADER).strip()

    members = list_members(leader_name=leader)
    alerts = list_alerts(leader_name=leader)
    lost_reports = list_lost_reports(leader_name=leader)

    total = len(members)
    safe = sum(1 for m in members if m["status"] == STATUS_SAFE)
    attention = sum(
        1 for m in members if m["status"] in (STATUS_PENDING, STATUS_SOS)
    )
    active_sos = sum(1 for a in alerts if a["status"] in ACTIVE_ALERT_STATUSES)
    active_lost_reports = sum(
        1 for r in lost_reports if r["status"] in ACTIVE_LOST_REPORT_STATUSES
    )

    # Welfare alerts: SOS alerts and lost-participant reports still active,
    # merged and sorted by most recent first, so a leader sees every
    # welfare-related signal for their delegation in one place (F7R4).
    welfare_alerts = [
        {
            "kind": "sos",
            "participant_name": a["participant_name"],
            "status": a["status"],
            "timestamp": a["submitted_at"],
            "location": a["location"],
            "message": a["message"],
        }
        for a in alerts
        if a["status"] in ACTIVE_ALERT_STATUSES
    ] + [
        {
            "kind": "lost_report",
            "participant_name": r["participant_name"],
            "status": r["status"],
            "timestamp": r["reported_at"],
            "location": r["last_known_location"],
            "message": r["description"],
        }
        for r in lost_reports
        if r["status"] in ACTIVE_LOST_REPORT_STATUSES
    ]
    welfare_alerts.sort(key=lambda x: x["timestamp"], reverse=True)

    return {
        "leader_name": leader,
        "stats": {
            "total_members": total,
            "checked_in": safe,
            "requiring_attention": attention,
            "active_sos": active_sos,
            "active_lost_reports": active_lost_reports,
        },
        "recent_alerts": alerts[:recent_limit],
        "welfare_alerts": welfare_alerts[:recent_limit],
        "team_overview": [
            {"name": m["name"], "status": m["status"]} for m in members
        ],
    }


def get_delegation_audience_categories(leader_name: Optional[str] = None) -> List[str]:
    """
    Return the distinct Audience_Category values present in a Team Leader's
    delegation, so the caller can filter announcements/schedules to exactly
    the audiences that delegation belongs to (Requirements F7R1, F7R2).
    """
    members = list_members(leader_name=leader_name)
    categories = {m["audience_category"] for m in members}
    return sorted(categories) or ["Students"]


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
# Lost participant reporting (Requirement F6R5)
# ------------------------------------------------------------------

def create_lost_report(
    participant_name: str,
    reported_by: str,
    last_known_location: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict:
    """
    Report a participant as lost/missing. Does not require the reported
    participant to be a recognized team member, since the reporter (a
    teammate, volunteer, or team leader) may not know their exact roster id.

    Raises:
        SafetyValidationError: if participant_name or reported_by is missing.
    """
    _ensure_seeded()
    name = (participant_name or "").strip()
    reporter = (reported_by or "").strip()
    if not name:
        raise SafetyValidationError("participant_name is required.")
    if not reporter:
        raise SafetyValidationError("reported_by is required.")

    with _lock:
        member = _find_member_by_name(name)
        leader = DEFAULT_LEADER
        if member is not None:
            team = _teams.get(member["team_id"], {})
            leader = team.get("leader_name", DEFAULT_LEADER)

        now = _now_iso()
        report_id = uuid.uuid4().hex
        _lost_reports[report_id] = {
            "id": report_id,
            "participant_name": name,
            "reported_by": reporter,
            "leader_name": leader,
            "status": LOST_REPORTED,
            "last_known_location": (last_known_location or "").strip() or None,
            "description": (description or "").strip() or None,
            "reported_at": now,
            "updated_at": now,
        }

        # Reflect the situation on the member's own status, mirroring SOS.
        if member is not None:
            member["status"] = STATUS_SOS

        result = _lost_report_to_dict(_lost_reports[report_id])

    logger.info("Lost participant report created for %s (id=%s)", name, report_id)
    return result


def list_lost_reports(leader_name: Optional[str] = None, status: Optional[str] = None) -> List[Dict]:
    """Return lost-participant reports for a Team Leader (most recent first)."""
    _ensure_seeded()
    leader = (leader_name or DEFAULT_LEADER).strip()

    if status is not None and status not in LOST_REPORT_STATUSES:
        raise SafetyValidationError(f"Invalid lost-report status filter: {status!r}")

    with _lock:
        result = [
            _lost_report_to_dict(r)
            for r in _lost_reports.values()
            if r["leader_name"].strip().lower() == leader.lower()
            and (status is None or r["status"] == status)
        ]

    result.sort(key=lambda x: x["reported_at"], reverse=True)
    return result


def update_lost_report_status(report_id: str, new_status: str) -> Dict:
    """
    Advance a lost-participant report through Reported -> Searching -> Found.
    When a report becomes Found and the participant is a recognized member
    with no other active alert, their status returns to Pending Check-in.

    Raises:
        SafetyValidationError: if new_status is invalid.
        SafetyNotFoundError: if the report id does not exist.
    """
    _ensure_seeded()
    if new_status not in LOST_REPORT_STATUSES:
        raise SafetyValidationError(f"Invalid lost-report status: {new_status!r}")

    with _lock:
        report = _lost_reports.get(report_id)
        if report is None:
            raise SafetyNotFoundError(f"Lost report '{report_id}' not found.")

        report["status"] = new_status
        report["updated_at"] = _now_iso()

        if new_status == LOST_FOUND:
            member = _find_member_by_name(report["participant_name"])
            if member is not None and not _member_has_active_alert(member["id"]):
                if member["status"] == STATUS_SOS:
                    member["status"] = STATUS_PENDING

        result = _lost_report_to_dict(report)

    logger.info("Lost report %s status -> %s", report_id, new_status)
    return result


# ------------------------------------------------------------------
# Emergency contacts + nearby medical facilities (Requirements F6R1, F6R6)
# ------------------------------------------------------------------

def get_emergency_contacts() -> List[Dict]:
    """Return the static emergency contact directory."""
    return list(EMERGENCY_CONTACTS)


def get_medical_facilities(near: Optional[str] = None) -> List[Dict]:
    """
    Return nearby medical facilities, optionally filtered to those tagged
    for a given venue (case-insensitive substring match on `near`).
    """
    if near is None or not near.strip():
        return list(MEDICAL_FACILITIES)
    needle = near.strip().lower()
    return [f for f in MEDICAL_FACILITIES if needle in f["near"].lower()]
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
