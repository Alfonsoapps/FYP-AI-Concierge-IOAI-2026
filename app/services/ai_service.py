"""Async RAG, NVIDIA Llama 3.1, and local text-to-speech pipeline."""

import asyncio
import base64
import logging
import os
import uuid
from typing import Any

import pyttsx3
from dotenv import load_dotenv, find_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from app.services.rag_service import rag_db

load_dotenv(find_dotenv())
logger = logging.getLogger(__name__)

TEMP_AUDIO_DIR = "./app/data"


class ChatPipeline:
    """Generate source-grounded replies and concurrency-safe speech audio."""

    def __init__(self) -> None:
        if not os.getenv("NVIDIA_API_KEY"):
            logger.warning("NVIDIA_API_KEY is not configured in the environment.")

        self.llm = ChatNVIDIA(model="meta/llama-3.1-8b-instruct")
        # Balance verified event facts with safe general-knowledge assistance.
        # Event-specific answers remain grounded in the retrieved database context.
        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are the official IOAI 2027 AI Concierge in Singapore.

CRITICAL INSTRUCTIONS:
VERIFIED FACTS: Read the 'Verified Event Database' below. If it contains information relevant to the user's question, you MUST use it and prioritize it.
MISSING FACTS: If the user asks about the IOAI event, schedule, or logistics, but the database is empty or lacks the answer, reply EXACTLY: 'I do not have that specific event information yet. Please check the Schedule tab.'
GENERAL KNOWLEDGE: If the user asks a general question (e.g., science, translation, general Singapore tourism, or casual chat) that is clearly outside the scope of IOAI logistics, you may use your general knowledge to answer them helpfully.
TONE: Be enthusiastic, concise, and youth-friendly. Keep answers brief (1-3 sentences).

Verified Event Database: {context}""",
                ),
                ("user", "{input}"),
            ]
        )

        # Prompt variant that includes uploaded document content
        self.prompt_with_document = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are the official IOAI 2027 AI Concierge in Singapore.

CRITICAL INSTRUCTIONS:
1. UPLOADED DOCUMENT: The user has uploaded a document. Its extracted text content is provided below under 'Uploaded Document Content'. Use this content to answer the user's question about the document.
2. VERIFIED FACTS: Read the 'Verified Event Database' below. If it contains information relevant to the user's question, you MUST use it and prioritize it alongside the uploaded document.
3. MISSING FACTS: If the user asks about the IOAI event, schedule, or logistics, but neither the uploaded document nor the database has the answer, reply EXACTLY: 'I do not have that specific event information yet. Please check the Schedule tab.'
4. GENERAL KNOWLEDGE: If the user asks a general question that is clearly outside the scope of IOAI logistics, you may use your general knowledge to answer them helpfully.
5. TONE: Be enthusiastic, concise, and youth-friendly. Keep answers brief (2-4 sentences). Reference the uploaded document when relevant.

Uploaded Document Content:
{document_content}

Verified Event Database: {context}""",
                ),
                ("user", "{input}"),
            ]
        )

    async def generate_reply(self, user_text: str) -> str:
        """Generate a reply using retrieved facts or appropriate general knowledge."""
        try:
            context = await rag_db.retrieve_context(user_text)

            # Always invoke the LLM. An explicit marker lets the prompt distinguish
            # missing event facts from questions that permit general knowledge.
            messages = self.prompt.format_messages(
                context=(
                    "No verified facts found for this query."
                    if context is None
                    or (
                        isinstance(context, str)
                        and (
                            not context.strip()
                            or context
                            == "No verified knowledge-base sources matched this question."
                        )
                    )
                    else context
                ),
                input=user_text,
            )

            response = await self.llm.ainvoke(messages)
            return response.content
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return "I'm sorry, I am having trouble connecting to my AI brain right now. Please try again later."

    async def generate_reply_with_document(
        self, user_text: str, document_content: str
    ) -> str:
        """
        Generate a reply that considers both the uploaded document content
        and the knowledge base (ChromaDB) context.

        Args:
            user_text: The user's question/message.
            document_content: Extracted text from the uploaded file.

        Returns:
            AI-generated response grounded in both sources.
        """
        try:
            # Retrieve relevant knowledge-base context
            context = await rag_db.retrieve_context(user_text)

            context_str = (
                "No verified facts found for this query."
                if context is None
                or (
                    isinstance(context, str)
                    and (
                        not context.strip()
                        or context
                        == "No verified knowledge-base sources matched this question."
                    )
                )
                else context
            )

            # Truncate document content to avoid exceeding token limits
            # (~4000 chars ≈ ~1000 tokens, leaving room for context + response)
            max_doc_chars = 6000
            truncated_doc = document_content[:max_doc_chars]
            if len(document_content) > max_doc_chars:
                truncated_doc += "\n\n[... document truncated for length ...]"

            messages = self.prompt_with_document.format_messages(
                document_content=truncated_doc,
                context=context_str,
                input=user_text,
            )

            response = await self.llm.ainvoke(messages)
            return response.content

        except Exception as e:
            logger.error(f"Chat with document error: {e}")
            return "I'm sorry, I am having trouble processing your document right now. Please try again later."

    async def generate_audio(self, text: str) -> dict[str, str]:
        """Generate uniquely named audio with pyttsx3 in a worker thread."""
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("text must not be empty.")

        os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)
        temp_file = os.path.join(
            TEMP_AUDIO_DIR,
            f"temp_{uuid.uuid4().hex}.mp3",
        )

        def _synthesize_and_encode() -> str:
            engine = None
            try:
                engine = pyttsx3.init()
                engine.setProperty("rate", 160)
                engine.save_to_file(clean_text, temp_file)
                engine.runAndWait()

                if not os.path.exists(temp_file) or os.path.getsize(temp_file) == 0:
                    raise RuntimeError("pyttsx3 did not create an audio file.")

                with open(temp_file, "rb") as audio_file:
                    return base64.b64encode(audio_file.read()).decode("ascii")
            finally:
                if engine is not None:
                    try:
                        engine.stop()
                    except Exception:
                        logger.debug("pyttsx3 engine cleanup failed", exc_info=True)
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except OSError:
                        logger.warning("Unable to remove temporary audio file %s", temp_file)

        try:
            b64_audio = await asyncio.to_thread(_synthesize_and_encode)
            return {"audio_base64": b64_audio}
        except Exception as exc:
            logger.exception("Audio generation failed")
            raise RuntimeError(f"Unable to generate audio: {exc}") from exc


chat_pipeline = ChatPipeline()
