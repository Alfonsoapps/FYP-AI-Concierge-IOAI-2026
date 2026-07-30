"""
Document Registry Service

Tracks which documents have been uploaded and embedded into ChromaDB.
Uses a lightweight SQLite database so the list persists across restarts.
"""

import logging
import sqlite3
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "documents.db"
_LOCK = threading.Lock()


def _connection() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the documents table if it doesn't exist."""
    with _LOCK, _connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                size_display TEXT NOT NULL,
                chunks INTEGER DEFAULT 0,
                chars INTEGER DEFAULT 0,
                uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
                status TEXT NOT NULL DEFAULT 'embedded'
            )
        """)
    logger.info("Document registry initialized at %s", _DB_PATH)


def add_document(filename: str, file_type: str, size_display: str, chunks: int = 0, chars: int = 0, status: str = "embedded") -> int:
    """Record a successfully uploaded document. Returns the new row ID."""
    with _LOCK, _connection() as conn:
        cursor = conn.execute(
            "INSERT INTO documents (filename, file_type, size_display, chunks, chars, status) VALUES (?, ?, ?, ?, ?, ?)",
            (filename, file_type, size_display, chunks, chars, status),
        )
        return cursor.lastrowid


def get_all_documents() -> list[dict]:
    """Return all registered documents, newest first."""
    with _LOCK, _connection() as conn:
        rows = conn.execute("SELECT * FROM documents ORDER BY uploaded_at DESC").fetchall()
    return [dict(row) for row in rows]


def delete_document(doc_id: int) -> bool:
    """Delete a document record by ID."""
    with _LOCK, _connection() as conn:
        cursor = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        return cursor.rowcount > 0
