"""
NVIDIA API Service Module

Handles all communication with the NVIDIA LLM Chat Completions API.
Uses the 'requests' library for simplicity and beginner-friendliness.

Architecture note:
    This module is intentionally kept simple and modular so it can be
    swapped out for a LangChain-based implementation in the future.

Workflow:
    User Message → generate_response() → NVIDIA API → AI Response
"""

import logging
import requests  # Simple HTTP library for calling the NVIDIA API

from app.config import get_settings

# Set up a logger for this module
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------
# System prompt: defines the AI assistant's personality and role.
# This is sent with every request so the model knows how to behave.
# -----------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a friendly AI concierge for international students attending "
    "IOAI 2027 in Singapore. You provide helpful, culturally sensitive, "
    "youth-friendly, and concise guidance."
)


def _announcement_context(role=None) -> str:
    """
    Build a short, plain-text summary of the latest published announcements so
    the concierge can answer questions like "What announcements have I missed?"
    or "Are there any urgent updates?".

    Fails soft: returns an empty string if the announcement store is unavailable.
    """
    try:
        # Imported lazily to avoid a hard dependency during unrelated chats.
        from app.services import announcement_service as ann_svc

        audience = ann_svc.normalize_role(role) if role else None
        items = ann_svc.latest_published(audience=audience, limit=10)
        if not items:
            return ""

        lines = []
        for a in items:
            urgent = " [CRITICAL]" if a.get("priority") == "Critical" else ""
            ack = " (acknowledgement required)" if a.get("ack_required") else ""
            lines.append(f"- {a['title']}{urgent}{ack}: {a['message']}")

        return (
            "\n\nHere are the latest published announcements relevant to this user. "
            "Use them to answer any questions about announcements, missed updates, "
            "or urgent notices:\n" + "\n".join(lines)
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Could not load announcement context: %s", e)
        return ""


def generate_response(user_message: str, role=None) -> str:
    """
    Send a user message to the NVIDIA Chat Completions API and return the AI response.

    Args:
        user_message: The text message from the user.
        role: Optional participant role used to include role-relevant
            announcements as extra context for the model.

    Returns:
        A string containing the AI-generated reply.

    Raises:
        ValueError: If the NVIDIA API key is not configured.
        ConnectionError: If the API request fails due to network issues.
        TimeoutError: If the API request times out.
        RuntimeError: If the API returns an invalid or empty response.
    """
    # Load settings (cached, so this is fast)
    settings = get_settings()

    # --- Guard: make sure the API key is set ---
    if not settings.nvidia_api_key:
        logger.error("NVIDIA_API_KEY is not set in .env")
        raise ValueError(
            "NVIDIA_API_KEY is not configured. "
            "Please add it to your .env file."
        )

    # --- Build the request headers ---
    # The Authorization header uses a Bearer token (your NVIDIA API key)
    headers = {
        "Authorization": f"Bearer {settings.nvidia_api_key}",
        "Content-Type": "application/json",
    }

    # --- Build the request payload ---
    # This follows the OpenAI-compatible chat completions format
    system_content = SYSTEM_PROMPT + _announcement_context(role)

    payload = {
        "model": settings.nvidia_model,
        "messages": [
            {"role": "system", "content": system_content},  # Behavior + announcement context
            {"role": "user", "content": user_message},       # The user's actual question
        ],
        "temperature": 0.7,   # Controls randomness (0 = deterministic, 1 = creative)
        "max_tokens": 1024,   # Maximum length of the AI response
    }

    # --- Construct the full API endpoint URL ---
    # Base URL + /chat/completions (standard OpenAI-compatible endpoint)
    url = f"{settings.nvidia_base_url}/chat/completions"

    # --- Make the API call with error handling ---
    try:
        logger.info("Calling NVIDIA API at %s with model %s", url, settings.nvidia_model)

        # Send POST request to NVIDIA API with a 30-second timeout
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30,  # Timeout in seconds to avoid hanging forever
        )

    except requests.exceptions.Timeout:
        # The API took too long to respond
        logger.error("NVIDIA API request timed out")
        raise TimeoutError(
            "The AI service took too long to respond. Please try again."
        )

    except requests.exceptions.ConnectionError:
        # Network issue (no internet, DNS failure, etc.)
        logger.error("Failed to connect to NVIDIA API")
        raise ConnectionError(
            "Could not connect to the AI service. Please check your internet connection."
        )

    except requests.exceptions.RequestException as e:
        # Catch-all for any other request errors
        logger.error("NVIDIA API request failed: %s", str(e))
        raise RuntimeError(f"AI service request failed: {str(e)}")

    # --- Handle HTTP error responses ---
    if response.status_code == 401:
        # Invalid or expired API key
        logger.error("NVIDIA API returned 401 Unauthorized")
        raise ValueError(
            "Invalid NVIDIA API key. Please check your NVIDIA_API_KEY in .env."
        )

    if response.status_code == 403:
        # API key doesn't have permission for this model
        logger.error("NVIDIA API returned 403 Forbidden")
        raise ValueError(
            "Your API key does not have access to this model. "
            "Please check your NVIDIA account permissions."
        )

    if response.status_code != 200:
        # Any other non-success status code
        logger.error(
            "NVIDIA API returned status %d: %s",
            response.status_code,
            response.text[:200],
        )
        raise RuntimeError(
            f"AI service returned an error (status {response.status_code}). "
            "Please try again later."
        )

    # --- Parse the JSON response ---
    try:
        data = response.json()
    except ValueError:
        logger.error("NVIDIA API returned invalid JSON")
        raise RuntimeError("AI service returned an invalid response.")

    # --- Extract the AI's reply from the response ---
    # The response follows OpenAI format: data["choices"][0]["message"]["content"]
    try:
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("AI service returned an empty response.")

        ai_reply = choices[0]["message"]["content"]

        # Make sure the reply isn't empty or just whitespace
        if not ai_reply or not ai_reply.strip():
            raise RuntimeError("AI service returned an empty message.")

        logger.info("Successfully received AI response (%d chars)", len(ai_reply))
        return ai_reply.strip()

    except (KeyError, IndexError, TypeError) as e:
        # The response JSON didn't have the expected structure
        logger.error("Unexpected NVIDIA API response format: %s", str(e))
        raise RuntimeError(
            "AI service returned an unexpected response format."
        )
