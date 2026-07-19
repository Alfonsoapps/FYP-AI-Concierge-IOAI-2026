from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.ai_service import chat_pipeline

router = APIRouter()


@router.websocket("/{user_id}")
async def websocket_chat(websocket: WebSocket, user_id: str) -> None:
    """WebSocket endpoint for real-time chat with the AI concierge."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            payload = data.get("payload", "")

            reply = await chat_pipeline.generate_reply(payload)
            audio_data = await chat_pipeline.generate_audio_and_visemes(reply)

            await websocket.send_json({
                "role": "ai",
                "content": reply,
                "audio": audio_data["audio_base64"],
            })
    except WebSocketDisconnect:
        pass
    except Exception:
        await websocket.close(code=1011, reason="Internal server error")
