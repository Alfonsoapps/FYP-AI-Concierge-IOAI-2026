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


def _safety_context() -> str:
    """
    Build a short, plain-text summary of emergency contacts and nearby
    medical facilities so the concierge can provide safety guidance and
    recommend nearby medical facilities (Requirements F6R4, F6R6).

    Fails soft: returns an empty string if the safety directory is
    unavailable, so a concierge reply is still generated.
    """
    try:
        # Imported lazily to avoid a hard dependency during unrelated chats.
        from app.services import team_safety_service as safety_svc

        contacts = safety_svc.get_emergency_contacts()
        facilities = safety_svc.get_medical_facilities()

        lines = ["Emergency contacts:"]
        for c in contacts:
            lines.append(f"- {c['label']}: {c['phone']} ({c['notes']})")

        lines.append("Nearby medical facilities:")
        for f in facilities:
            lines.append(
                f"- {f['name']} ({f['category']}, near {f['near']}): "
                f"{f['address']}, {f['phone']}"
            )

        return "\n".join(lines)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Could not load safety context: %s", e)
        return ""


def _culture_context() -> str:
    """
    Build a short, plain-text summary of Singapore culture facts, food
    recommendations, and etiquette tips so the concierge can proactively
    answer participant-experience questions (Requirements F10R1, F10R2, F10R3).

    Fails soft: returns an empty string if the Explore module is unavailable,
    so a concierge reply is still generated.
    """
    try:
        # Imported lazily to avoid a hard dependency during unrelated chats.
        from app.services import explore_service as explore_svc

        guide = explore_svc.get_culture_guide()

        lines = ["Singapore culture facts:"]
        for f in guide["culture_facts"]:
            lines.append(f"- {f['title']}: {f['body']}")

        lines.append("Local food recommendations:")
        for f in guide["food_recommendations"]:
            lines.append(f"- {f['dish']}: {f['description']} (Where: {f['where']})")

        lines.append("Local etiquette tips:")
        for t in guide["etiquette_tips"]:
            lines.append(f"- {t['tip']}: {t['detail']}")

        return "\n".join(lines)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Could not load culture context: %s", e)
        return ""


def _announcement_context(role: str | None = None) -> str:
    """
    Build a short, plain-text summary of the latest published announcements so
    the concierge can answer questions like "What have I missed?" or "Any
    urgent updates?" (Requirement 10.6: AI Concierge uses the
    Latest_Announcements_Endpoint data path).

    Fails soft: returns an empty string if the announcement store is
    unavailable, so a concierge reply is still generated (Requirement 10.7).
    """
    try:
        # Imported lazily to avoid a hard dependency during unrelated chats.
        from app.services import announcement_service as ann_svc

        audience = ann_svc.normalize_role(role) if role else None
        items = ann_svc.latest_published(audience=audience, limit=20)
        if not items:
            return ""

        lines = []
        for a in items:
            urgent = " [CRITICAL]" if a.get("priority") == "Critical" else ""
            ack = " (acknowledgement required)" if a.get("ack_required") else ""
            lines.append(f"- {a['title']}{urgent}{ack}: {a['message']}")

        return (
            "Latest published announcements relevant to this user "
            "(use these to answer questions about missed or urgent updates):\n"
            + "\n".join(lines)
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Could not load announcement context: %s", e)
        return ""


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
SAFETY: If the user describes an emergency, injury, illness, feeling unsafe, or being lost, calmly provide safety guidance first (e.g. advise contacting a team leader or calling the emergency numbers below), then reference the most relevant emergency contact or nearby medical facility from the 'Verified Event Database' if one is included. For life-threatening emergencies, tell the user to call 999 (Police) or 995 (Ambulance/Fire) immediately and use the in-app SOS button on the Safety tab.
CULTURE: If the user asks about Singapore culture, local food recommendations, or local etiquette, use the culture facts, food recommendations, and etiquette tips included in the 'Verified Event Database' below, and mention they can find more on the Explore tab.
TONE: Be enthusiastic, concise, and youth-friendly. Keep answers brief (1-3 sentences), except safety guidance may be up to 4 sentences.

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

    async def generate_reply(self, user_text: str, role: str | None = None) -> str:
        """Generate a reply using retrieved facts or appropriate general knowledge."""
        try:
            context = await rag_db.retrieve_context(user_text)

            # An explicit marker lets the prompt distinguish missing event facts
            # from questions that permit general knowledge.
            rag_context = (
                None
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

            # Blend in the latest published announcements relevant to the
            # caller's role, so the concierge can answer questions about
            # missed or urgent announcements (Requirement 10.6).
            announcement_context = _announcement_context(role)

            # Blend in emergency contacts and nearby medical facilities so the
            # concierge can provide safety guidance (Requirements F6R4, F6R6).
            safety_context = _safety_context()

            # Blend in Singapore culture facts, food recommendations, and
            # etiquette tips (Requirements F10R1, F10R2, F10R3).
            culture_context = _culture_context()

            extra_context = "\n\n".join(
                c for c in (announcement_context, safety_context, culture_context) if c
            )

            if rag_context and extra_context:
                combined_context = f"{rag_context}\n\n{extra_context}"
            elif rag_context:
                combined_context = rag_context
            elif extra_context:
                combined_context = extra_context
            else:
                combined_context = "No verified facts found for this query."

            # Always invoke the LLM after successful retrieval.
            messages = self.prompt.format_messages(
                context=combined_context,
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
