"""
Text-to-Speech Service Module

Converts text into speech audio using Edge-TTS (Microsoft Edge's TTS engine).
Edge-TTS is free, requires no API key, and produces natural-sounding speech.

Architecture note:
    This module is async (uses edge-tts which is natively async).
    It generates MP3 audio bytes that can be streamed to the frontend.
"""

import logging
import io
import edge_tts

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------
# TTS Configuration
# -----------------------------------------------------------------
# Voice options for Edge-TTS (Microsoft Neural voices)
# Full list: run `edge-tts --list-voices` in terminal
# Good options for a friendly concierge:
#   - en-SG-LunaNeural (Singaporean English, female)
#   - en-US-AriaNeural (US English, female, friendly)
#   - en-US-GuyNeural (US English, male)
#   - en-GB-SoniaNeural (British English, female)
DEFAULT_VOICE = "en-SG-LunaNeural"  # Singaporean English for IOAI context

# Speech rate adjustment (e.g., "+10%" for faster, "-10%" for slower)
DEFAULT_RATE = "+0%"

# Speech pitch adjustment
DEFAULT_PITCH = "+0Hz"


async def generate_speech(text: str, voice: str = None) -> bytes:
    """
    Convert text to speech audio (MP3 format) using Edge-TTS.

    Args:
        text: The text to convert to speech.
        voice: Optional voice name override. Defaults to DEFAULT_VOICE.

    Returns:
        MP3 audio data as bytes.

    Raises:
        RuntimeError: If TTS generation fails.
    """
    if not text or not text.strip():
        raise ValueError("Cannot generate speech from empty text.")

    selected_voice = voice or DEFAULT_VOICE

    logger.info(
        "Generating TTS: voice=%s, text_length=%d chars",
        selected_voice,
        len(text),
    )

    try:
        # Create the Edge-TTS communicator
        communicate = edge_tts.Communicate(
            text=text,
            voice=selected_voice,
            rate=DEFAULT_RATE,
            pitch=DEFAULT_PITCH,
        )

        # Collect audio chunks into a buffer
        audio_buffer = io.BytesIO()

        async for chunk in communicate.stream():
            # Edge-TTS streams both audio and metadata chunks
            # We only want the audio data
            if chunk["type"] == "audio":
                audio_buffer.write(chunk["data"])

        audio_bytes = audio_buffer.getvalue()

        if not audio_bytes:
            raise RuntimeError("TTS produced empty audio output.")

        logger.info("TTS generated successfully: %d bytes", len(audio_bytes))
        return audio_bytes

    except Exception as e:
        logger.error("TTS generation failed: %s", str(e))
        raise RuntimeError(f"Speech generation failed: {str(e)}")
