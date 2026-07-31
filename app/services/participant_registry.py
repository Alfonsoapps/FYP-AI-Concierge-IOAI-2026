"""
Participant Registry Service

Stores all registered participants in a SQLite database so admins
can see who has signed up for the event.
"""

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "participants.db"
_LOCK = threading.Lock()


def _connection() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the participants table if it doesn't exist."""
    with _LOCK, _connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                country TEXT DEFAULT '',
                language TEXT DEFAULT 'English',
                registered_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_participants_name
            ON participants (name)
        """)
    logger.info("Participant registry initialized at %s", _DB_PATH)


def register_participant(
    name: str,
    role: str,
    country: str = "",
    language: str = "English",
) -> int:
    """Register a new participant. Returns the new row ID."""
    with _LOCK, _connection() as conn:
        # Check if already registered (by name + role to avoid duplicates)
        existing = conn.execute(
            "SELECT id FROM participants WHERE LOWER(name) = LOWER(?) AND role = ?",
            (name.strip(), role),
        ).fetchone()
        if existing:
            # Update their info instead of duplicating
            conn.execute(
                "UPDATE participants SET country = ?, language = ?, registered_at = datetime('now') WHERE id = ?",
                (country, language, existing[0]),
            )
            return existing[0]

        cursor = conn.execute(
            "INSERT INTO participants (name, role, country, language) VALUES (?, ?, ?, ?)",
            (name.strip(), role, country, language),
        )
        logger.info("New participant registered: %s (%s, %s)", name, role, country)
        return cursor.lastrowid


def get_all_participants() -> list[dict]:
    """Return all registered participants, newest first."""
    with _LOCK, _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM participants ORDER BY registered_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_participant_count() -> int:
    """Return total number of registered participants."""
    with _LOCK, _connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM participants").fetchone()
    return row[0] if row else 0


def get_stats() -> dict:
    """Return participant registration stats."""
    with _LOCK, _connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM participants").fetchone()[0]
        by_role = conn.execute(
            "SELECT role, COUNT(*) as count FROM participants GROUP BY role ORDER BY count DESC"
        ).fetchall()
        by_country = conn.execute(
            "SELECT country, COUNT(*) as count FROM participants WHERE country != '' GROUP BY country ORDER BY count DESC"
        ).fetchall()
    return {
        "total": total,
        "by_role": [{"role": r[0], "count": r[1]} for r in by_role],
        "by_country": [{"country": r[0], "count": r[1]} for r in by_country],
    }
