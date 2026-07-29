from pydantic import BaseModel, ConfigDict, Field


class ActivityRequest(BaseModel):
    """Anonymous browser-session heartbeat; never contains participant PII."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    session_id: str = Field(
        ...,
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]+$",
        description="Random identifier persisted by the browser",
    )


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
