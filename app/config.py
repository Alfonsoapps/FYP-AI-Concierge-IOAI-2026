"""
Application Configuration

Loads environment variables from .env using pydantic-settings.
All NVIDIA API settings are configurable via environment variables.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Environment variables:
        NVIDIA_API_KEY: Your NVIDIA API key (required for AI responses)
        NVIDIA_BASE_URL: Base URL for the NVIDIA API (default: https://integrate.api.nvidia.com/v1)
        NVIDIA_MODEL: The NVIDIA model to use (default: meta/llama-3.1-8b-instruct)
    """

    # NVIDIA API configuration
    nvidia_api_key: str = ""  # Loaded from NVIDIA_API_KEY in .env
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"  # Base URL (without /chat/completions)
    nvidia_model: str = "meta/llama-3.1-8b-instruct"  # Chat model identifier
    # Pin both the embedding model and its Matryoshka output size. Chroma
    # collections permanently adopt the dimension of their first embedding.
    nvidia_embedding_model: str = "nvidia/llama-nemotron-embed-1b-v2"
    nvidia_embedding_dimensions: int = 2048

    # App settings
    app_name: str = "AI Concierge"
    debug: bool = False

    # Telegram Bot (optional — for announcement notifications)
    telegram_bot_token: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.
    Uses lru_cache so the .env file is only read once (not on every request).
    """
    return Settings()
