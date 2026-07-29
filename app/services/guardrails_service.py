"""
NeMo Guardrails Service

Wraps NeMo Guardrails LLMRails to screen and route every chat message through
the configured Colang 2.x flows before the response is returned to the user.

Design notes:
- Lazy-initialised: LLMRails is expensive to load, so it is created once on
  the first call and cached in a module-level variable.
- Fail-open: if guardrails are unavailable (import error, config error, missing
  API key) the service logs a warning and returns None, letting the caller fall
  back to the plain NVIDIA service. This keeps the app usable in dev without a
  key.
- Blocking calls are run synchronously (nemoguardrails' generate() is sync) via
  the standard pattern used across this codebase (requests library, no asyncio).
- The module follows the existing service pattern: plain module-level functions,
  module-level singleton, logging via logging.getLogger(__name__).
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level singleton — None until first use.
_rails = None
_rails_init_attempted = False

# Absolute path to the guardrails config directory.
_CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "guardrails_config",
)


def _init_rails() -> Optional[object]:
    """
    Initialise LLMRails from the guardrails_config directory.
    Returns the LLMRails instance, or None if initialisation fails.
    """
    global _rails, _rails_init_attempted
    if _rails_init_attempted:
        return _rails

    _rails_init_attempted = True

    # Verify the API key is available before attempting to load — NeMo
    # Guardrails resolves the NIM engine from NVIDIA_API_KEY at construction
    # time and will fail loudly if it is missing.
    from app.config import get_settings
    settings = get_settings()
    if not settings.nvidia_api_key:
        logger.warning(
            "NeMo Guardrails disabled: NVIDIA_API_KEY is not set. "
            "Chat will fall back to the plain NVIDIA service."
        )
        return None

    # Set the environment variable that the NIM engine reads.
    os.environ.setdefault("NVIDIA_API_KEY", settings.nvidia_api_key)

    try:
        # Imported inside the function so the heavy nemoguardrails package is
        # never loaded at module import time (keeps app startup fast).
        from nemoguardrails import LLMRails, RailsConfig  # type: ignore

        if not os.path.isdir(_CONFIG_DIR):
            logger.warning(
                "NeMo Guardrails disabled: config directory not found at %s",
                _CONFIG_DIR,
            )
            return None

        logger.info("Loading NeMo Guardrails config from %s …", _CONFIG_DIR)
        config = RailsConfig.from_path(_CONFIG_DIR)
        _rails = LLMRails(config)
        logger.info("✓ NeMo Guardrails initialised (Colang 2.x, input rails active)")
        return _rails

    except Exception as exc:
        logger.warning(
            "NeMo Guardrails initialisation failed (%s). "
            "Falling back to plain NVIDIA service.",
            exc,
        )
        return None


def generate_guarded_response(user_message: str) -> Optional[str]:
    """
    Pass a user message through NeMo Guardrails and return the AI reply.

    The guardrails pipeline:
      1. Runs input rails (self_check_input) — blocks unsafe/inappropriate messages.
      2. Runs llm continuation — generates a grounded, on-topic response.

    Returns:
        The assistant's reply string, or None if:
        - Guardrails are unavailable (key missing, import error, config error).
        - The message was blocked by a rail (empty string from LLMRails).

    The caller should fall back to the plain NVIDIA service when None is returned
    and guardrails were unavailable, and show a safety message when an empty
    string is returned (message blocked).
    """
    rails = _init_rails()
    if rails is None:
        return None

    messages = [{"role": "user", "content": user_message}]

    try:
        result = rails.generate(messages=messages)
        # LLMRails returns a dict {"role": "assistant", "content": "..."}
        if isinstance(result, dict):
            content = result.get("content", "")
        else:
            content = str(result)

        if not content or not content.strip():
            # Empty reply = message was blocked by an input rail.
            logger.info("Guardrails blocked a message (empty response returned).")
            return ""

        return content.strip()

    except Exception as exc:
        logger.error("NeMo Guardrails generate() failed: %s", exc)
        return None


def is_available() -> bool:
    """Return True if guardrails are configured and ready."""
    return _init_rails() is not None
