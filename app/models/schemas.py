from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming chat message from the user."""

    message: str = Field(..., min_length=1, max_length=2000, description="User message")


class ChatResponse(BaseModel):
    """Response returned to the client."""

    reply: str = Field(..., description="AI-generated response")


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
