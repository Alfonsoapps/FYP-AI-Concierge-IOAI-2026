"""
Safety & Emergency Service

Provides emergency contact info, medical facilities near venues,
and a lost-participant reporting workflow.
"""

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()

# ------------------------------------------------------------------
# Static data
# ------------------------------------------------------------------

EMERGENCY_CONTACTS = [
    {"name": "Singapore Police", "number": "999", "type": "emergency", "description": "For crime, accidents, or life-threatening emergencies"},
    {"name": "SCDF (Ambulance / Fire)", "number": "995", "type": "emergency", "description": "For medical emergencies, fires, or rescue"},
    {"name": "Non-Emergency Police", "number": "1800-255-0000", "type": "non-emergency", "description": "For non-urgent police matters"},
    {"name": "IOAI Safety Desk", "number": "+65 6000-0999", "type": "organiser", "description": "24/7 event safety hotline — available during IOAI 2027"},
    {"name": "IOAI Medical Team", "number": "+65 6000-0998", "type": "organiser", "description": "On-site medical team at all venues"},
]

MEDICAL_FACILITIES = [
    {"name": "Singapore General Hospital", "address": "Outram Road", "distance": "15 min from Marina Bay Sands", "type": "hospital", "phone": "+65 6222-3322", "hours": "24/7 Emergency"},
    {"name": "Raffles Medical (Marina Bay)", "address": "Marina Bay Financial Centre", "distance": "5 min walk from MBS", "type": "clinic", "phone": "+65 6221-1188", "hours": "Mon-Fri 8:30am-6pm"},
    {"name": "NUS University Health Centre", "address": "NUS Campus", "distance": "On-site at workshop venue", "type": "clinic", "phone": "+65 6516-7531", "hours": "Mon-Fri 8:30am-5:30pm"},
    {"name": "Changi General Hospital", "address": "2 Simei Street 3", "distance": "10 min from SUTD", "type": "hospital", "phone": "+65 6788-8833", "hours": "24/7 Emergency"},
    {"name": "Guardian Pharmacy (MBS)", "address": "Marina Bay Sands B2", "distance": "Inside main venue", "type": "pharmacy", "phone": "+65 6688-7033", "hours": "10am-10pm daily"},
]

# ------------------------------------------------------------------
# Lost participant reports (in-memory store)
# ------------------------------------------------------------------

REPORT_STATUSES = ["Reported", "Searching", "Found"]

_lost_reports: Dict[str, Dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_emergency_contacts() -> List[Dict]:
    """Return all emergency contacts."""
    return EMERGENCY_CONTACTS


def get_medical_facilities() -> List[Dict]:
    """Return medical facilities near event venues."""
    return MEDICAL_FACILITIES


def create_lost_report(
    reporter_name: str,
    missing_name: str,
    last_seen_location: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict:
    """Create a lost-participant report."""
    if not reporter_name or not reporter_name.strip():
        raise ValueError("reporter_name is required.")
    if not missing_name or not missing_name.strip():
        raise ValueError("missing_name is required.")

    report_id = uuid.uuid4().hex[:12]
    now = _now_iso()

    report = {
        "id": report_id,
        "reporter_name": reporter_name.strip(),
        "missing_name": missing_name.strip(),
        "last_seen_location": (last_seen_location or "").strip() or None,
        "description": (description or "").strip() or None,
        "status": "Reported",
        "created_at": now,
        "updated_at": now,
    }

    with _lock:
        _lost_reports[report_id] = report

    logger.info("Lost report created: %s (missing: %s)", report_id, missing_name)
    return report


def get_lost_reports(status: Optional[str] = None) -> List[Dict]:
    """Return all lost reports, optionally filtered by status."""
    if status and status not in REPORT_STATUSES:
        raise ValueError(f"Invalid status: {status}")

    with _lock:
        reports = list(_lost_reports.values())

    if status:
        reports = [r for r in reports if r["status"] == status]

    reports.sort(key=lambda r: r["created_at"], reverse=True)
    return reports


def update_lost_report_status(report_id: str, new_status: str) -> Dict:
    """Update the status of a lost report."""
    if new_status not in REPORT_STATUSES:
        raise ValueError(f"Invalid status: {new_status}")

    with _lock:
        report = _lost_reports.get(report_id)
        if not report:
            raise LookupError(f"Report '{report_id}' not found.")
        report["status"] = new_status
        report["updated_at"] = _now_iso()
        return dict(report)
