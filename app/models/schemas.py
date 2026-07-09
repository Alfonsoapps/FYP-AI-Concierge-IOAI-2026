from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming chat message from the user."""

    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    role: str | None = Field(
        default=None, max_length=100, description="Optional participant role (for announcement context)"
    )


class ChatResponse(BaseModel):
    """Response returned to the client."""

    reply: str = Field(..., description="AI-generated response")


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
