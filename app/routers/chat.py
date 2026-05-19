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

import logging
from fastapi import APIRouter, HTTPException

from app.models.schemas import ChatRequest, ChatResponse
from app.services.nvidia_service import generate_response

# Set up a logger for this module
logger = logging.getLogger(__name__)

# Create a router with the "chat" tag (groups endpoints in Swagger docs)
router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Process a user message and return an AI-generated response.

    Steps:
        1. Validates the incoming message (handled by Pydantic schema)
        2. Sends it to the NVIDIA LLM API via the service layer
        3. Returns the generated reply as JSON

    Request body:
        - message (str): The user's question or message (1-2000 characters)

    Returns:
        - reply (str): The AI-generated response

    Error codes:
        - 400: Empty or invalid message
        - 500: API key not configured
        - 502: NVIDIA API call failed
        - 504: NVIDIA API timed out
    """
    # Strip whitespace from the message
    user_message = request.message.strip()

    # Double-check the message isn't empty after stripping
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    logger.info("Received user message: %s", user_message[:100])

    try:
        # Call the NVIDIA service to generate an AI response
        # This is a synchronous call (uses requests library)
        reply = generate_response(user_message)

    except ValueError as e:
        # Configuration errors (missing API key, invalid key, etc.)
        logger.error("Configuration error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    except TimeoutError as e:
        # The NVIDIA API took too long to respond
        logger.error("Timeout error: %s", e)
        raise HTTPException(status_code=504, detail=str(e))

    except ConnectionError as e:
        # Network connectivity issues
        logger.error("Connection error: %s", e)
        raise HTTPException(
            status_code=502, detail="Could not connect to the AI service."
        )

    except RuntimeError as e:
        # Any other API errors (bad response, empty response, etc.)
        logger.error("Runtime error: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error("Unexpected error: %s", e)
        raise HTTPException(
            status_code=502, detail="Failed to get response from AI service."
        )

    logger.info("AI reply generated (%d chars)", len(reply))

    # Return the response as JSON (Pydantic handles serialization)
    return ChatResponse(reply=reply)
