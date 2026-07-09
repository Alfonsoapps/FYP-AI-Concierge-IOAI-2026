"""
Announcement Service Module

Lightweight, module-local persistence and business logic for the Announcements
feature. Uses the Python standard library `sqlite3` so it introduces no new
third-party dependency and survives application restarts (Requirement 11).

Responsibilities:
    - Persist announcements and per-user recipient records (read/acknowledge).
    - Normalize client-supplied roles to fixed Audience_Category values.
    - Provide CRUD, publish, audience-filtered retrieval, tracking, and stats.
    - Seed sample data for testing.

Design notes:
    - There is no server-side auth in the host app; the caller passes the
      participant name and role (from client-side localStorage). Role
      normalization and audience filtering happen here, server-side.
    - A recipient record is created lazily the first time a user reads or
      acknowledges an announcement. "Targeted users" statistics are therefore
      computed from the recipient records that exist for an announcement.
"""

import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

# Fixed audience categories (Requirement: target audiences).
AUDIENCE_CATEGORIES = [
    "Students",
    "Team Leaders",
    "Observers",
    "Volunteers",
    "Organisers",
    "All Users",
]

VALID_PRIORITIES = ["Normal", "Critical"]
VALID_STATUSES = ["draft", "published"]

TITLE_MAX = 200
MESSAGE_MAX = 5000
NAME_MAX = 100

# Storage lives inside the module's data directory so it is self-contained.
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_DB_PATH = os.path.join(_DATA_DIR, "announcements.db")

# Serialize writes (SQLite + FastAPI threadpool safety).
_write_lock = threading.Lock()


# ------------------------------------------------------------------
# Errors
# ------------------------------------------------------------------

class AnnouncementValidationError(ValueError):
    """Raised when an announcement request fails validation."""


class AnnouncementNotFoundError(LookupError):
    """Raised when an announcement identifier does not match any record."""


class AnnouncementStateError(ValueError):
    """Raised when an operation is invalid for the announcement's current state."""


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------

def _now_iso() -> str:
    """Current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def normalize_role(role: Optional[str]) -> str:
    """
    Map a client-supplied role to an Audience_Category (Requirement 4).

    Comparison ignores surrounding whitespace and letter case. Unknown, empty,
    or missing roles map to "All Users".
    """
    if not role or not role.strip():
        return "All Users"

    cleaned = role.strip().lower()

    explicit = {
        "student participant": "Students",
        "student": "Students",
        "students": "Students",
        "team leader": "Team Leaders",
        "team leaders": "Team Leaders",
        "observer": "Observers",
        "observers": "Observers",
        "volunteer": "Volunteers",
        "volunteers": "Volunteers",
        "organiser": "Organisers",
        "organizer": "Organisers",
        "organisers": "Organisers",
        "organizers": "Organisers",
        "all users": "All Users",
    }
    if cleaned in explicit:
        return explicit[cleaned]

    # Direct (case-insensitive) match against a defined category name.
    for category in AUDIENCE_CATEGORIES:
        if cleaned == category.lower():
            return category

    return "All Users"


def is_organiser(role: Optional[str]) -> bool:
    """True when the supplied role resolves to the Organisers audience."""
    return normalize_role(role) == "Organisers"


# ------------------------------------------------------------------
# Database bootstrap
# ------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    os.makedirs(_DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables if they do not exist. Safe to call on every startup."""
    with _write_lock:
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS announcements (
                    id              TEXT PRIMARY KEY,
                    title           TEXT NOT NULL,
                    message         TEXT NOT NULL,
                    category        TEXT NOT NULL,
                    priority        TEXT NOT NULL,
                    target_audience TEXT NOT NULL,
                    ack_required    INTEGER NOT NULL DEFAULT 0,
                    status          TEXT NOT NULL DEFAULT 'draft',
                    created_at      TEXT NOT NULL,
                    published_at    TEXT
                );

                CREATE TABLE IF NOT EXISTS announcement_recipients (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    announcement_id  TEXT NOT NULL,
                    participant_name TEXT NOT NULL,
                    read_at          TEXT,
                    acknowledged_at  TEXT,
                    UNIQUE(announcement_id, participant_name),
                    FOREIGN KEY(announcement_id) REFERENCES announcements(id) ON DELETE CASCADE
                );
                """
            )
            conn.commit()
        finally:
            conn.close()
    logger.info("Announcement DB initialized at %s", _DB_PATH)


# ------------------------------------------------------------------
# Serialization helpers
# ------------------------------------------------------------------

def _row_to_announcement(row: sqlite3.Row) -> Dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "message": row["message"],
        "category": row["category"],
        "priority": row["priority"],
        "target_audience": row["target_audience"],
        "ack_required": bool(row["ack_required"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "published_at": row["published_at"],
    }


def _audience_matches(target: str, user_category: str) -> bool:
    return target == user_category or target == "All Users"


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------

def _validate_fields(
    title: Optional[str],
    message: Optional[str],
    category: Optional[str],
    priority: Optional[str],
    target_audience: Optional[str],
    ack_required,
) -> None:
    if title is None or not title.strip():
        raise AnnouncementValidationError("Title is required.")
    if len(title) > TITLE_MAX:
        raise AnnouncementValidationError(f"Title must be at most {TITLE_MAX} characters.")

    if message is None or not message.strip():
        raise AnnouncementValidationError("Message is required.")
    if len(message) > MESSAGE_MAX:
        raise AnnouncementValidationError(f"Message must be at most {MESSAGE_MAX} characters.")

    if category is None or not category.strip():
        raise AnnouncementValidationError("Category is required.")

    if priority not in VALID_PRIORITIES:
        raise AnnouncementValidationError("Priority must be 'Normal' or 'Critical'.")

    if target_audience not in AUDIENCE_CATEGORIES:
        raise AnnouncementValidationError("Invalid target audience.")

    if not isinstance(ack_required, bool):
        raise AnnouncementValidationError("Acknowledgement-required flag must be a boolean.")


# ------------------------------------------------------------------
# CRUD + publish
# ------------------------------------------------------------------

def create_announcement(
    title: str,
    message: str,
    category: str,
    priority: str,
    target_audience: str,
    ack_required: bool,
) -> Dict:
    """Create a new draft announcement (Requirement 1)."""
    _validate_fields(title, message, category, priority, target_audience, ack_required)

    ann_id = uuid.uuid4().hex
    created_at = _now_iso()

    with _write_lock:
        conn = _connect()
        try:
            conn.execute(
                """INSERT INTO announcements
                   (id, title, message, category, priority, target_audience,
                    ack_required, status, created_at, published_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, NULL)""",
                (
                    ann_id, title.strip(), message.strip(), category.strip(),
                    priority, target_audience, 1 if ack_required else 0, created_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    logger.info("Created announcement %s (audience=%s)", ann_id, target_audience)
    return get_announcement(ann_id)


def list_all_announcements() -> List[Dict]:
    """Return all announcements, drafts included (Requirement 2)."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM announcements ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_announcement(r) for r in rows]


def get_announcement(announcement_id: str) -> Dict:
    """Return a single announcement by id, or raise if not found."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM announcements WHERE id = ?", (announcement_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise AnnouncementNotFoundError(f"Announcement '{announcement_id}' not found.")
    return _row_to_announcement(row)


def update_announcement(
    announcement_id: str,
    title: str,
    message: str,
    category: str,
    priority: str,
    target_audience: str,
    ack_required: bool,
) -> Dict:
    """Update an existing announcement's fields (Requirement 2)."""
    existing = get_announcement(announcement_id)  # raises if missing
    _validate_fields(title, message, category, priority, target_audience, ack_required)

    with _write_lock:
        conn = _connect()
        try:
            conn.execute(
                """UPDATE announcements
                   SET title = ?, message = ?, category = ?, priority = ?,
                       target_audience = ?, ack_required = ?
                   WHERE id = ?""",
                (
                    title.strip(), message.strip(), category.strip(), priority,
                    target_audience, 1 if ack_required else 0, announcement_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    logger.info("Updated announcement %s", announcement_id)
    return get_announcement(announcement_id)


def delete_announcement(announcement_id: str) -> None:
    """Delete an announcement and its recipient records (Requirement 2)."""
    get_announcement(announcement_id)  # raises if missing
    with _write_lock:
        conn = _connect()
        try:
            # ON DELETE CASCADE removes recipient records atomically.
            conn.execute("DELETE FROM announcements WHERE id = ?", (announcement_id,))
            conn.commit()
        finally:
            conn.close()
    logger.info("Deleted announcement %s", announcement_id)


def publish_announcement(announcement_id: str) -> Dict:
    """Publish a draft announcement (Requirement 3)."""
    existing = get_announcement(announcement_id)  # raises if missing
    if existing["status"] != "draft":
        raise AnnouncementStateError("Only draft announcements can be published.")

    published_at = _now_iso()
    with _write_lock:
        conn = _connect()
        try:
            conn.execute(
                "UPDATE announcements SET status = 'published', published_at = ? WHERE id = ?",
                (published_at, announcement_id),
            )
            conn.commit()
        finally:
            conn.close()
    logger.info("Published announcement %s", announcement_id)
    return get_announcement(announcement_id)


# ------------------------------------------------------------------
# Audience-filtered retrieval + tracking
# ------------------------------------------------------------------

def _published_for_audience(conn: sqlite3.Connection, user_category: str) -> List[sqlite3.Row]:
    rows = conn.execute(
        """SELECT * FROM announcements
           WHERE status = 'published'
             AND (target_audience = ? OR target_audience = 'All Users')
           ORDER BY published_at DESC""",
        (user_category,),
    ).fetchall()
    return rows


def list_for_user(role: Optional[str], participant_name: Optional[str]) -> List[Dict]:
    """
    Return published announcements targeted to the user's resolved audience,
    annotated with this user's read/acknowledged state (Requirements 4, 5, 7).
    """
    user_category = normalize_role(role)
    name = (participant_name or "").strip()

    conn = _connect()
    try:
        rows = _published_for_audience(conn, user_category)

        # Fetch this user's recipient records in one pass.
        recipient_map = {}
        if name:
            rec_rows = conn.execute(
                "SELECT * FROM announcement_recipients WHERE participant_name = ?",
                (name,),
            ).fetchall()
            recipient_map = {r["announcement_id"]: r for r in rec_rows}
    finally:
        conn.close()

    result = []
    for row in rows:
        ann = _row_to_announcement(row)
        rec = recipient_map.get(ann["id"])
        ann["read_at"] = rec["read_at"] if rec else None
        ann["acknowledged_at"] = rec["acknowledged_at"] if rec else None
        result.append(ann)
    return result[:100]


def mark_read(announcement_id: str, participant_name: Optional[str]) -> Dict:
    """
    Record a read timestamp for the user/announcement (Requirement 6).
    Only applies when the announcement is published. Idempotent: keeps the
    original read timestamp if one already exists.
    """
    name = (participant_name or "").strip()
    if not name or len(name) > NAME_MAX:
        raise AnnouncementValidationError("A valid participant_name is required.")

    ann = get_announcement(announcement_id)  # raises if missing
    if ann["status"] != "published":
        raise AnnouncementStateError("Cannot track reads on a non-published announcement.")

    now = _now_iso()
    with _write_lock:
        conn = _connect()
        try:
            existing = conn.execute(
                "SELECT * FROM announcement_recipients WHERE announcement_id = ? AND participant_name = ?",
                (announcement_id, name),
            ).fetchone()

            if existing is None:
                conn.execute(
                    """INSERT INTO announcement_recipients
                       (announcement_id, participant_name, read_at, acknowledged_at)
                       VALUES (?, ?, ?, NULL)""",
                    (announcement_id, name, now),
                )
            elif existing["read_at"] is None:
                conn.execute(
                    "UPDATE announcement_recipients SET read_at = ? WHERE id = ?",
                    (now, existing["id"]),
                )
            # else: retain original read timestamp.
            conn.commit()
        finally:
            conn.close()
    return {"announcement_id": announcement_id, "participant_name": name, "read": True}


def acknowledge(announcement_id: str, participant_name: Optional[str]) -> Dict:
    """
    Record an acknowledged timestamp for a critical announcement (Requirement 7).
    """
    name = (participant_name or "").strip()
    if not name or len(name) > NAME_MAX:
        raise AnnouncementValidationError("A valid participant_name is required.")

    ann = get_announcement(announcement_id)  # raises if missing
    if not ann["ack_required"]:
        raise AnnouncementValidationError("This announcement does not require acknowledgement.")

    now = _now_iso()
    already = False
    with _write_lock:
        conn = _connect()
        try:
            existing = conn.execute(
                "SELECT * FROM announcement_recipients WHERE announcement_id = ? AND participant_name = ?",
                (announcement_id, name),
            ).fetchone()

            if existing is None:
                conn.execute(
                    """INSERT INTO announcement_recipients
                       (announcement_id, participant_name, read_at, acknowledged_at)
                       VALUES (?, ?, ?, ?)""",
                    (announcement_id, name, now, now),
                )
            elif existing["acknowledged_at"] is None:
                # Ensure read is set too, then acknowledge.
                read_at = existing["read_at"] or now
                conn.execute(
                    "UPDATE announcement_recipients SET read_at = ?, acknowledged_at = ? WHERE id = ?",
                    (read_at, now, existing["id"]),
                )
            else:
                already = True
            conn.commit()

            final = conn.execute(
                "SELECT acknowledged_at FROM announcement_recipients WHERE announcement_id = ? AND participant_name = ?",
                (announcement_id, name),
            ).fetchone()
        finally:
            conn.close()

    return {
        "announcement_id": announcement_id,
        "participant_name": name,
        "acknowledged_at": final["acknowledged_at"] if final else now,
        "already_acknowledged": already,
    }


def unread_count(role: Optional[str], participant_name: Optional[str]) -> int:
    """Count published targeted announcements the user has not read (Requirement 8)."""
    user_category = normalize_role(role)
    name = (participant_name or "").strip()

    conn = _connect()
    try:
        rows = _published_for_audience(conn, user_category)
        if not name:
            return len(rows)
        rec_rows = conn.execute(
            "SELECT announcement_id, read_at FROM announcement_recipients WHERE participant_name = ?",
            (name,),
        ).fetchall()
        read_ids = {r["announcement_id"] for r in rec_rows if r["read_at"] is not None}
    finally:
        conn.close()

    return sum(1 for row in rows if row["id"] not in read_ids)


# ------------------------------------------------------------------
# Latest (AI concierge) + statistics
# ------------------------------------------------------------------

def latest_published(audience: Optional[str] = None, limit: int = 20) -> List[Dict]:
    """
    Return up to `limit` recent published announcements, optionally filtered by
    an Audience_Category (Requirement 10). Pass the resolved category.
    """
    if audience is not None and audience not in AUDIENCE_CATEGORIES:
        raise AnnouncementValidationError("Invalid audience category.")

    conn = _connect()
    try:
        if audience:
            rows = conn.execute(
                """SELECT * FROM announcements
                   WHERE status = 'published'
                     AND (target_audience = ? OR target_audience = 'All Users')
                   ORDER BY published_at DESC LIMIT ?""",
                (audience, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM announcements
                   WHERE status = 'published'
                   ORDER BY published_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
    finally:
        conn.close()
    return [_row_to_announcement(r) for r in rows]


def get_statistics(announcement_id: str) -> Dict:
    """Compute read/acknowledge statistics for an announcement (Requirement 9)."""
    ann = get_announcement(announcement_id)  # raises if missing

    conn = _connect()
    try:
        recs = conn.execute(
            "SELECT participant_name, read_at, acknowledged_at FROM announcement_recipients WHERE announcement_id = ?",
            (announcement_id,),
        ).fetchall()
    finally:
        conn.close()

    targeted = len(recs)
    read_count = sum(1 for r in recs if r["read_at"] is not None)
    ack_count = sum(1 for r in recs if r["acknowledged_at"] is not None)
    not_acknowledged = [
        r["participant_name"] for r in recs if r["acknowledged_at"] is None
    ] if ann["ack_required"] else []

    return {
        "announcement_id": announcement_id,
        "title": ann["title"],
        "ack_required": ann["ack_required"],
        "targeted_users": targeted,
        "read_count": read_count,
        "acknowledged_count": ack_count,
        "not_acknowledged_users": not_acknowledged,
    }


# ------------------------------------------------------------------
# Sample data (Requirement 11)
# ------------------------------------------------------------------

def seed_sample_data(force: bool = False) -> int:
    """
    Load sample announcements + recipient records when storage is empty.
    Returns the number of announcements created (0 if skipped).
    """
    existing = list_all_announcements()
    if existing and not force:
        logger.info("Sample data skipped: storage already contains announcements.")
        return 0

    now = _now_iso()
    samples = [
        {
            "title": "Welcome to IOAI 2027!",
            "message": "Welcome to Singapore! Check the schedule page for your opening ceremony details.",
            "category": "General",
            "priority": "Normal",
            "target_audience": "All Users",
            "ack_required": False,
        },
        {
            "title": "Mandatory Safety Briefing",
            "message": "All students must attend the safety briefing at 8:00 AM on Day 1. Please acknowledge you have read this.",
            "category": "Emergency",
            "priority": "Critical",
            "target_audience": "Students",
            "ack_required": True,
        },
        {
            "title": "Team Leader Coordination Meeting",
            "message": "Team leaders, please gather in Room 3B at 7:30 AM before the competition begins.",
            "category": "Logistics",
            "priority": "Normal",
            "target_audience": "Team Leaders",
            "ack_required": False,
        },
        {
            "title": "Observer Lab Tour Rescheduled",
            "message": "The observer lab tour has moved to 10:00 AM on Day 2. Meet at the main lobby.",
            "category": "Schedule",
            "priority": "Normal",
            "target_audience": "Observers",
            "ack_required": False,
        },
        {
            "title": "URGENT: Venue Change for Closing Ceremony",
            "message": "The closing ceremony has moved to Marina Bay Sands Hall A. Please acknowledge this critical update.",
            "category": "Emergency",
            "priority": "Critical",
            "target_audience": "All Users",
            "ack_required": True,
        },
    ]

    created_ids = []
    with _write_lock:
        conn = _connect()
        try:
            for s in samples:
                ann_id = uuid.uuid4().hex
                conn.execute(
                    """INSERT INTO announcements
                       (id, title, message, category, priority, target_audience,
                        ack_required, status, created_at, published_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'published', ?, ?)""",
                    (
                        ann_id, s["title"], s["message"], s["category"], s["priority"],
                        s["target_audience"], 1 if s["ack_required"] else 0, now, now,
                    ),
                )
                created_ids.append(ann_id)

            # Seed recipient records: one read, one unread, one acknowledged.
            first = created_ids[0]
            second = created_ids[1]
            conn.execute(
                """INSERT INTO announcement_recipients
                   (announcement_id, participant_name, read_at, acknowledged_at)
                   VALUES (?, ?, ?, NULL)""",
                (first, "Alice Tan", now),
            )
            conn.execute(
                """INSERT INTO announcement_recipients
                   (announcement_id, participant_name, read_at, acknowledged_at)
                   VALUES (?, ?, ?, ?)""",
                (second, "Alice Tan", now, now),
            )
            conn.execute(
                """INSERT INTO announcement_recipients
                   (announcement_id, participant_name, read_at, acknowledged_at)
                   VALUES (?, ?, NULL, NULL)""",
                (first, "Bob Lim"),
            )
            conn.commit()
        finally:
            conn.close()

    logger.info("Seeded %d sample announcements.", len(created_ids))
    return len(created_ids)
