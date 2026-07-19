import os
import asyncio
import base64
import logging
import uuid

import pyttsx3
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.prompts import ChatPromptTemplate

from services.rag_service import rag_db

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are the IOAI 2027 AI Concierge. Answer based ONLY on context. "
    "CRITICAL: You MUST cite your sources (e.g., 'According to the Event Handbook...'). "
    "Context: {context}. User: {input}"
)


class ChatPipeline:
    """End-to-end chat pipeline with LLM generation and TTS audio synthesis."""

    def __init__(self) -> None:
        self.llm = ChatNVIDIA(model="meta/llama-3.1-8b-instruct")
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "{input}"),
        ])

    async def generate_reply(self, user_text: str) -> str:
        """Generate an AI reply using RAG context and the LLM."""
        try:
            context = await rag_db.retrieve_context(user_text)
            formatted = self.prompt.format_messages(context=context, input=user_text)
            response = await asyncio.to_thread(self.llm.invoke, formatted)
            return response.content
        except Exception as e:
            logger.error(f"Error generating reply: {e}")
            return "I'm sorry, I encountered an error processing your request."

    async def generate_audio_and_visemes(self, text: str) -> dict:
        """Generate TTS audio as Base64 and placeholder visemes."""
        try:
            result = await asyncio.to_thread(self._synthesize_audio, text)
            return result
        except Exception as e:
            logger.error(f"Error generating audio: {e}")
            return {"audio_base64": "", "visemes": []}

    @staticmethod
    def _synthesize_audio(text: str) -> dict:
        """Synchronous TTS synthesis (run in thread)."""
        temp_file = f"temp_{uuid.uuid4().hex}.mp3"
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 160)
            engine.save_to_file(text, temp_file)
            engine.runAndWait()

            with open(temp_file, "rb") as f:
                audio_bytes = f.read()

            b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
            return {"audio_base64": b64_audio, "visemes": []}
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)


chat_pipeline = ChatPipeline()
