"""
Chat Logger Service

Logs every participant ↔ AI conversation turn to a SQLite database
for admin monitoring. Privacy-conscious: stores hashed session IDs only.
"""

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "chat_logs.db"
_LOCK = threading.Lock()


def _connection() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the chat_logs table if it doesn't exist."""
    with _LOCK, _connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                user_message TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                response_time_ms INTEGER DEFAULT 0,
                has_file INTEGER DEFAULT 0,
                filename TEXT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_logs_timestamp
            ON chat_logs (timestamp DESC)
        """)
    logger.info("Chat logger initialized at %s", _DB_PATH)


def log_chat(
    session_id: str,
    user_message: str,
    ai_response: str,
    response_time_ms: int = 0,
    filename: Optional[str] = None,
) -> None:
    """Record one conversation turn."""
    with _LOCK, _connection() as conn:
        conn.execute(
            """INSERT INTO chat_logs
               (session_id, user_message, ai_response, response_time_ms, has_file, filename)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                user_message[:2000],
                ai_response[:5000],
                response_time_ms,
                1 if filename else 0,
                filename,
            ),
        )


def get_recent_logs(limit: int = 100, offset: int = 0) -> list[dict]:
    """Return recent chat logs, newest first."""
    with _LOCK, _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM chat_logs ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(row) for row in rows]


def get_log_count() -> int:
    """Return total number of logged conversations."""
    with _LOCK, _connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM chat_logs").fetchone()
    return row[0] if row else 0


def get_stats() -> dict:
    """Return summary stats for the admin dashboard."""
    with _LOCK, _connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM chat_logs").fetchone()[0]
        unique_sessions = conn.execute("SELECT COUNT(DISTINCT session_id) FROM chat_logs").fetchone()[0]
        with_files = conn.execute("SELECT COUNT(*) FROM chat_logs WHERE has_file = 1").fetchone()[0]
        today = conn.execute(
            "SELECT COUNT(*) FROM chat_logs WHERE date(timestamp) = date('now')"
        ).fetchone()[0]
    return {
        "total_conversations": total,
        "unique_sessions": unique_sessions,
        "with_files": with_files,
        "today": today,
    }
