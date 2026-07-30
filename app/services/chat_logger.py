"""
Chat Logger Service

Logs every participant ↔ AI conversation turn to a SQLite database
for admin monitoring. Includes content flagging for inappropriate messages
and detection of unanswered questions.
"""

import logging
import re
import sqlite3
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "chat_logs.db"
_LOCK = threading.Lock()

# Keyword-based content filter for flagging inappropriate messages
_INAPPROPRIATE_PATTERNS = [
    r'\b(fuck|shit|ass|bitch|damn|crap|dick|cock|pussy|bastard|whore|slut)\w*\b',
    r'\b(nigger|nigga|faggot|retard)\w*\b',
    r'\b(kill|murder|stab|shoot|bomb|attack|hurt)\s+(you|him|her|them|people|someone)\b',
    r'\b(i\s+will|gonna|going\s+to)\s+(kill|hurt|attack|bomb)\b',
    r'\b(sex|porn|nude|naked|orgasm|masturbat)\w*\b',
    r'ignore\s+(all\s+)?previous\s+instructions',
    r'you\s+are\s+now\s+a\s+different',
    r'pretend\s+(to\s+be|you\s+are)',
    r'forget\s+(your|all)\s+(rules|instructions)',
    r'system\s*prompt',
    r'\b(cocaine|heroin|meth|weed|marijuana|drugs)\b',
]
_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _INAPPROPRIATE_PATTERNS]

# Phrases indicating the AI couldn't answer the question
_UNANSWERED_PHRASES = [
    "i do not have that specific event information",
    "i'm sorry, i am having trouble connecting",
    "i don't have enough information",
    "i couldn't find",
    "please check the schedule tab",
]


def check_content_flag(message: str) -> bool:
    """Return True if the message contains inappropriate content."""
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(message):
            return True
    return False


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
                flagged INTEGER DEFAULT 0,
                flag_reason TEXT,
                unanswered INTEGER DEFAULT 0,
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
    """Record one conversation turn. Auto-flags inappropriate content and unanswered queries."""
    flagged = check_content_flag(user_message)
    flag_reason = None
    if flagged:
        for pattern in _COMPILED_PATTERNS:
            match = pattern.search(user_message)
            if match:
                flag_reason = f"Pattern match: '{match.group()}'"
                break
        logger.warning("FLAGGED message from session %s: %s", session_id[:12], user_message[:80])

    # Detect unanswered questions
    unanswered = 0
    response_lower = ai_response.lower()
    if any(phrase in response_lower for phrase in _UNANSWERED_PHRASES):
        unanswered = 1

    with _LOCK, _connection() as conn:
        conn.execute(
            """INSERT INTO chat_logs
               (session_id, user_message, ai_response, response_time_ms, has_file, filename, flagged, flag_reason, unanswered)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                user_message[:2000],
                ai_response[:5000],
                response_time_ms,
                1 if filename else 0,
                filename,
                1 if flagged else 0,
                flag_reason,
                unanswered,
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
        flagged = conn.execute("SELECT COUNT(*) FROM chat_logs WHERE flagged = 1").fetchone()[0]
        unanswered = conn.execute("SELECT COUNT(*) FROM chat_logs WHERE unanswered = 1").fetchone()[0]
        today = conn.execute(
            "SELECT COUNT(*) FROM chat_logs WHERE date(timestamp) = date('now')"
        ).fetchone()[0]
    return {
        "total_conversations": total,
        "unique_sessions": unique_sessions,
        "with_files": with_files,
        "flagged": flagged,
        "unanswered": unanswered,
        "today": today,
    }


def get_top_questions(limit: int = 10) -> list[dict]:
    """Return the most frequently asked questions (grouped by similarity)."""
    with _LOCK, _connection() as conn:
        # Simple approach: group exact messages and count
        rows = conn.execute(
            """SELECT user_message, COUNT(*) as count
               FROM chat_logs
               GROUP BY LOWER(TRIM(user_message))
               ORDER BY count DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [{"question": row[0], "count": row[1]} for row in rows]


def get_unanswered_questions(limit: int = 20) -> list[dict]:
    """Return questions the AI could not answer."""
    with _LOCK, _connection() as conn:
        rows = conn.execute(
            """SELECT user_message, ai_response, timestamp, session_id
               FROM chat_logs
               WHERE unanswered = 1
               ORDER BY timestamp DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_engagement_metrics() -> dict:
    """Return engagement metrics for the dashboard."""
    with _LOCK, _connection() as conn:
        # Messages per day (last 7 days)
        daily = conn.execute(
            """SELECT date(timestamp) as day, COUNT(*) as count
               FROM chat_logs
               WHERE timestamp >= datetime('now', '-7 days')
               GROUP BY date(timestamp)
               ORDER BY day"""
        ).fetchall()

        # Peak hour
        hourly = conn.execute(
            """SELECT strftime('%H', timestamp) as hour, COUNT(*) as count
               FROM chat_logs
               GROUP BY hour
               ORDER BY count DESC
               LIMIT 1"""
        ).fetchone()

        # Avg response time
        avg_time = conn.execute(
            "SELECT AVG(response_time_ms) FROM chat_logs WHERE response_time_ms > 0"
        ).fetchone()[0]

        # Sessions with multiple messages (engaged users)
        engaged = conn.execute(
            """SELECT COUNT(*) FROM (
                SELECT session_id FROM chat_logs
                GROUP BY session_id HAVING COUNT(*) >= 3
            )"""
        ).fetchone()[0]

    return {
        "daily_activity": [{"day": row[0], "count": row[1]} for row in daily],
        "peak_hour": f"{hourly[0]}:00" if hourly else "N/A",
        "avg_response_ms": int(avg_time) if avg_time else 0,
        "engaged_users": engaged,
    }
