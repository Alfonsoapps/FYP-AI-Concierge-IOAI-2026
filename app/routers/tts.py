"""
TTS Router

Handles the POST /tts endpoint for text-to-speech conversion.
Accepts text and returns MP3 audio that the frontend can play.

Workflow:
    Frontend sends POST /tts with text
    → This router validates the input
    → Calls the TTS service to generate speech audio
    → Returns MP3 audio bytes as a streaming response
"""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.tts_service import generate_speech

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tts"])


# --- Request schema ---
class TTSRequest(BaseModel):
    """Request body for text-to-speech conversion."""
    text: str = Field(..., min_length=1, max_length=5000, description="Text to convert to speech")
    voice: str = Field(default=None, description="Optional voice name override")


@router.post("/tts")
async def text_to_speech(request: TTSRequest):
    """
    Convert text to speech audio (MP3).

    Request body:
        - text (str): The text to speak (1-5000 characters)
        - voice (str, optional): Voice name override

    Returns:
        MP3 audio file as binary response

    Error codes:
        - 400: Empty or invalid text
        - 500: TTS generation failed
    """
    text = request.text.strip()

    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    logger.info("TTS request: %d chars", len(text))

    try:
        # Generate speech audio (async)
        audio_bytes = await generate_speech(text, voice=request.voice)

    except ValueError as e:
        logger.error("TTS validation error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

    except RuntimeError as e:
        logger.error("TTS generation error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        logger.error("Unexpected TTS error: %s", e)
        raise HTTPException(status_code=500, detail="Speech generation failed.")

    # Return the audio as an MP3 response
    # The frontend will play this using HTML5 Audio
    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "no-cache",
        },
    )
