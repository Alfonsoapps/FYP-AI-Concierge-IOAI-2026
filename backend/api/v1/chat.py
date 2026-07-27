from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.ai_service import chat_pipeline


class ConnectionManager:
    """Track active WebSocket clients grouped by stable user ID."""

    def __init__(self) -> None:
        self.active_connections: dict[str, set[WebSocket]] = {}

    @property
    def active_user_count(self) -> int:
        """Return the number of unique users with at least one open socket."""
        return len(self.active_connections)

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        await websocket.accept()
        self.active_connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        user_connections = self.active_connections.get(user_id)
        if user_connections is None:
            return

        user_connections.discard(websocket)
        if not user_connections:
            self.active_connections.pop(user_id, None)


manager = ConnectionManager()
TOTAL_QUERIES = 0

router = APIRouter()


@router.websocket("/{user_id}")
async def websocket_chat(websocket: WebSocket, user_id: str) -> None:
    """WebSocket endpoint for real-time chat with the AI concierge."""
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_json()
            user_text = data.get("payload", "")
            global TOTAL_QUERIES
            TOTAL_QUERIES += 1

            reply = await chat_pipeline.generate_reply(user_text)
            audio_data = await chat_pipeline.generate_audio_and_visemes(reply)

            await websocket.send_json({
                "role": "ai",
                "content": reply,
                "audio": audio_data["audio_base64"],
            })
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except RuntimeError:
            pass
    finally:
        manager.disconnect(websocket, user_id)
