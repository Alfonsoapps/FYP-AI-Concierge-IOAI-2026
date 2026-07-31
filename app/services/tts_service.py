"""
Text-to-Speech Service Module

Converts text into speech audio using Edge-TTS (Microsoft Edge's TTS engine).
Edge-TTS is free, requires no API key, and produces natural-sounding speech.

Includes a Singapore pronunciation preprocessing layer that converts local
place names into phonetic hints for the TTS engine.

Architecture note:
    This module is async (uses edge-tts which is natively async).
    It generates MP3 audio bytes that can be streamed to the frontend.
    The TTS provider is abstracted so it can be swapped for alternatives.
"""

import logging
import io
import re
import edge_tts

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------
# TTS Configuration
# -----------------------------------------------------------------
DEFAULT_VOICE = "en-SG-LunaNeural"  # Singaporean English for IOAI context
DEFAULT_RATE = "+5%"
DEFAULT_PITCH = "+8Hz"

# -----------------------------------------------------------------
# Singapore Pronunciation Dictionary
# Maps place names to phonetic-friendly spellings that the TTS engine
# pronounces more naturally for Singapore English speakers.
# -----------------------------------------------------------------
PRONUNCIATION_MAP = {
    "Suntec": "Sun-tek",
    "SUNTEC": "Sun-tek",
    "NUS": "N.U.S.",
    "NTU": "N.T.U.",
    "SUTD": "S.U.T.D.",
    "SMU": "S.M.U.",
    "Changi": "Chahng-ee",
    "Ang Mo Kio": "Ahng Mo Kee-oh",
    "Toa Payoh": "Toh-ah Pie-oh",
    "Bukit": "Boo-kit",
    "Jurong": "Joo-rong",
    "Bedok": "Beh-dok",
    "Tampines": "Tam-pi-neez",
    "Hougang": "Hoe-gahng",
    "Yishun": "Yee-shun",
    "Bishan": "Bee-shan",
    "Orchard": "Or-chard",
    "Raffles": "Rah-fuls",
    "Sentosa": "Sen-toh-sah",
    "Chinatown": "China-town",
    "MBS": "Marina Bay Sands",
    "MRT": "M.R.T.",
    "EZ-Link": "Easy-Link",
    "Hawker": "Haw-ker",
    "Laksa": "Lak-sah",
    "Char Kway Teow": "Char Kway Tee-ow",
    "Hainanese": "High-nah-neez",
    "Kopi": "Ko-pee",
    "Nasi Lemak": "Nah-see Leh-mak",
    "Roti Prata": "Roh-tee Prah-tah",
    "IOAI": "I.O.A.I.",
    "SGD": "Singapore dollars",
    "HDB": "H.D.B.",
    "CBD": "C.B.D.",
    "Joo Chiat": "Joo Chee-at",
    "Geylang": "Gay-lahng",
    "Katong": "Kah-tong",
    "Clementi": "Cleh-men-tee",
}

# Compile a regex for efficient replacement (longest match first)
_PRONUNCIATION_PATTERN = re.compile(
    "|".join(re.escape(k) for k in sorted(PRONUNCIATION_MAP.keys(), key=len, reverse=True)),
    re.IGNORECASE,
)


def preprocess_text_for_tts(text: str) -> str:
    """
    Apply the Singapore pronunciation dictionary to text before TTS.
    Replaces known place names with phonetic-friendly alternatives.
    """
    def _replace(match):
        original = match.group(0)
        # Try exact case match first, then case-insensitive
        return PRONUNCIATION_MAP.get(original, PRONUNCIATION_MAP.get(original.title(), original))

    return _PRONUNCIATION_PATTERN.sub(_replace, text)


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

    # Apply pronunciation preprocessing
    processed_text = preprocess_text_for_tts(text)
    selected_voice = voice or DEFAULT_VOICE

    logger.info(
        "Generating TTS: voice=%s, text_length=%d chars",
        selected_voice,
        len(processed_text),
    )

    try:
        communicate = edge_tts.Communicate(
            text=processed_text,
            voice=selected_voice,
            rate=DEFAULT_RATE,
            pitch=DEFAULT_PITCH,
        )

        audio_buffer = io.BytesIO()

        async for chunk in communicate.stream():
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
