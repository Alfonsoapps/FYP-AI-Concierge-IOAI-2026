"""
Chat Router

Handles the POST /chat endpoint for AI concierge interactions.
This is the main entry point for user messages.

Workflow:
    User sends POST /chat with a message
    → This router validates the input
    → Calls the NVIDIA service to get an AI response
    → Returns the response as JSON
"""

import hashlib
import logging
import re
import sqlite3
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect

from app.models.schemas import ActivityRequest, ChatRequest, ChatResponse
from app.services.ai_service import chat_pipeline

ACTIVE_USER_TTL_SECONDS = 90.0
ANALYTICS_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "analytics.db"
_ANALYTICS_LOCK = threading.Lock()

# Set up a logger for this module
logger = logging.getLogger(__name__)

# Create a router with the "chat" tag (groups endpoints in Swagger docs)
router = APIRouter(tags=["chat"])


def _analytics_connection() -> sqlite3.Connection:
    """Open the small local analytics database used across app reloads."""
    ANALYTICS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(ANALYTICS_DB_PATH, timeout=10)


def _initialize_analytics() -> None:
    """Create persistent counters and active-user storage when first imported."""
    with _ANALYTICS_LOCK, _analytics_connection() as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS metrics "
            "(key TEXT PRIMARY KEY, value INTEGER NOT NULL)"
        )
        connection.execute(
            "INSERT OR IGNORE INTO metrics (key, value) VALUES ('total_queries', 0)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS active_users "
            "(user_id TEXT PRIMARY KEY, last_seen REAL NOT NULL)"
        )
        # Earlier builds stored raw header values (including the shared
        # fallback 'anonymous'). They cannot be safely matched to hashed IDs
        # and would briefly double-count after deployment, so discard them.
        connection.execute(
            "DELETE FROM active_users WHERE user_id NOT LIKE 'sha256:%'"
        )


def get_total_queries() -> int:
    """Read the durable total so analytics works across reloads and workers."""
    with _ANALYTICS_LOCK, _analytics_connection() as connection:
        row = connection.execute(
            "SELECT value FROM metrics WHERE key = 'total_queries'"
        ).fetchone()
    return int(row[0]) if row else 0


def _increment_total_queries() -> int:
    """Atomically increment and return the durable query counter."""
    global TOTAL_QUERIES
    with _ANALYTICS_LOCK, _analytics_connection() as connection:
        connection.execute(
            "UPDATE metrics SET value = value + 1 WHERE key = 'total_queries'"
        )
        row = connection.execute(
            "SELECT value FROM metrics WHERE key = 'total_queries'"
        ).fetchone()
    TOTAL_QUERIES = int(row[0]) if row else 0
    return TOTAL_QUERIES


_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")


def _session_hash(session_id: str) -> str:
    """Validate and irreversibly pseudonymize a random browser identifier."""
    normalized = session_id.strip()
    if not _SESSION_ID_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid anonymous session identifier")
    return f"sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def record_user_activity(session_id: str, *, now: float | None = None) -> None:
    """Upsert one session heartbeat and purge sessions beyond the rolling TTL."""
    session_hash = _session_hash(session_id)
    heartbeat_time = time.time() if now is None else now
    cutoff = heartbeat_time - ACTIVE_USER_TTL_SECONDS
    with _ANALYTICS_LOCK, _analytics_connection() as connection:
        connection.execute("DELETE FROM active_users WHERE last_seen < ?", (cutoff,))
        connection.execute(
            "INSERT INTO active_users (user_id, last_seen) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET last_seen = excluded.last_seen",
            (session_hash, heartbeat_time),
        )


def get_active_user_count(*, now: float | None = None) -> int:
    """Count distinct non-expired heartbeats and currently open sockets."""
    current_time = time.time() if now is None else now
    cutoff = current_time - ACTIVE_USER_TTL_SECONDS
    with _ANALYTICS_LOCK, _analytics_connection() as connection:
        connection.execute("DELETE FROM active_users WHERE last_seen < ?", (cutoff,))
        rows = connection.execute("SELECT user_id FROM active_users").fetchall()
    session_hashes = {str(row[0]) for row in rows}
    session_hashes.update(manager.active_connections)
    return len(session_hashes)


_initialize_analytics()
# Compatibility export used by existing code; analytics reads the DB directly.
TOTAL_QUERIES = get_total_queries()


@router.post("/chat/activity")
async def chat_activity(payload: ActivityRequest) -> dict[str, str]:
    """Receive a validated anonymous heartbeat without counting a query."""
    record_user_activity(payload.session_id)
    return {"status": "active"}


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    x_user_id: str | None = Header(default=None),
) -> ChatResponse:
    """Answer the browser's REST chat request using the shared RAG pipeline."""
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    _increment_total_queries()
    if x_user_id:
        try:
            record_user_activity(x_user_id)
        except ValueError:
            # Analytics is best-effort for legacy/non-browser chat clients.
            logger.debug("Ignoring invalid anonymous session header")
    logger.info("Received RAG chat message: %s", user_message[:100])

    try:
        # Admin ingestion and browser chat now share this exact RAG instance.
        reply = await chat_pipeline.generate_reply(user_message)
    except ValueError as exc:
        logger.error("Invalid chat request: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("RAG chat failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected RAG chat failure")
        raise HTTPException(
            status_code=502,
            detail="Failed to get a verified response from the AI service.",
        ) from exc

    logger.info("Grounded AI reply generated (%d chars)", len(reply))
    return ChatResponse(reply=reply)


# ---------------------------------------------------------------------------
# Real-time WebSocket chat. The existing POST /chat endpoint above is retained
# for teammate clients that still use request/response messaging.
# ---------------------------------------------------------------------------
class ConnectionManager:
    """Track sockets by pseudonymous session while deduplicating browser tabs."""

    def __init__(self) -> None:
        self.active_connections: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_hash: str) -> None:
        """Accept and register one socket under its browser session."""
        await websocket.accept()
        self.active_connections.setdefault(session_hash, set()).add(websocket)

    def disconnect(self, session_hash: str, websocket: WebSocket) -> None:
        """Remove only the closing tab, retaining any sibling tab sockets."""
        sockets = self.active_connections.get(session_hash)
        if not sockets:
            return
        sockets.discard(websocket)
        if not sockets:
            self.active_connections.pop(session_hash, None)


manager = ConnectionManager()


@router.websocket("/ws/{user_id}")
async def websocket_chat(websocket: WebSocket, user_id: str) -> None:
    """Stream guarded RAG replies for a validated anonymous session."""
    try:
        session_hash = _session_hash(user_id)
    except ValueError:
        await websocket.close(code=1008, reason="Invalid anonymous session identifier")
        return

    await manager.connect(websocket, session_hash)
    record_user_activity(user_id)
    logger.info("WebSocket connected for anonymous session")

    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                await websocket.send_json(
                    {
                        "role": "system",
                        "content": "The WebSocket message must be a JSON object.",
                        "audio": None,
                    }
                )
                continue

            payload = data.get("payload")

            if payload and str(payload).strip():
                _increment_total_queries()

            if payload is None or not str(payload).strip():
                await websocket.send_json(
                    {
                        "role": "system",
                        "content": "The payload must contain a non-empty message.",
                        "audio": None,
                    }
                )
                continue

            user_text = str(payload).strip()
            reply = await chat_pipeline.generate_reply(user_text)
            audio_data = await chat_pipeline.generate_audio(reply)
            await websocket.send_json(
                {
                    "role": "ai",
                    "content": reply,
                    "audio": audio_data["audio_base64"],
                }
            )
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for anonymous session")
    except Exception as exc:
        logger.exception("WebSocket chat failed: %s", exc)
        try:
            await websocket.send_json(
                {
                    "role": "system",
                    "content": "The concierge could not process that message.",
                    "audio": None,
                }
            )
        except Exception:
            logger.debug(
                "Unable to send WebSocket error response",
                exc_info=True,
            )
    finally:
        manager.disconnect(session_hash, websocket)
        logger.info("WebSocket state cleaned up for anonymous session")
