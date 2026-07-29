# Bugfix Requirements Document

## Introduction

This bugfix updates only `app/services/ai_service.py` so the IOAI 2027 concierge no longer blocks clearly non-event general-knowledge questions when retrieval finds no verified facts, while preserving verified event grounding, the event-information fallback, audio generation, RAG integration, imports, and connection-error behavior.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN RAG retrieval returns no usable verified facts THEN the system returns before formatting the prompt and invoking the language model.
1.2 WHEN a user asks a clearly non-event general-knowledge question and RAG retrieval is empty THEN the system responds with the old verified-database fallback instead of answering the question.
1.3 WHEN a user asks an event question for which a relevant verified fact is available, such as the stored `University event` fact with category `Event` and content `Date 29/7/2026`, THEN the system can respond with the old verified-database fallback rather than using the fact.
1.4 WHEN the language model receives the concierge instructions THEN the system does not reliably distinguish verified event facts, missing event information, and clearly non-event general knowledge while maintaining the requested concise youth-friendly tone.

### Expected Behavior (Correct)

2.1 WHEN RAG retrieval returns no usable verified facts THEN the system SHALL format the prompt with `No verified facts found for this query.` as the context and invoke the language model.
2.2 WHEN a user asks a clearly non-event question about subjects such as science, translation, general Singapore tourism, or casual conversation and no verified event fact is relevant THEN the system SHALL answer helpfully using permitted general knowledge.
2.3 WHEN a user asks an event question for which a relevant verified database fact is available, including the stored `University event` fact with category `Event` and content `Date 29/7/2026`, THEN the system SHALL prioritize and use that verified fact in the answer.
2.4 WHEN the concierge handles a user question THEN the system SHALL apply the following prompt exactly:

```text
You are the official IOAI 2027 AI Concierge in Singapore.

CRITICAL INSTRUCTIONS:
VERIFIED FACTS: Read the 'Verified Event Database' below. If it contains information relevant to the user's question, you MUST use it and prioritize it.
MISSING FACTS: If the user asks about the IOAI event, schedule, or logistics, but the database is empty or lacks the answer, reply EXACTLY: 'I do not have that specific event information yet. Please check the Schedule tab.'
GENERAL KNOWLEDGE: If the user asks a general question (e.g., science, translation, general Singapore tourism, or casual chat) that is clearly outside the scope of IOAI logistics, you may use your general knowledge to answer them helpfully.
TONE: Be enthusiastic, concise, and youth-friendly. Keep answers brief (1-3 sentences).

Verified Event Database: {context}
```

### Unchanged Behavior (Regression Prevention)

3.1 WHEN `app/services/ai_service.py` is upgraded THEN the system SHALL CONTINUE TO retain all existing imports, with every internal application import starting with `app`, including exactly `from app.services.rag_service import rag_db`.
3.2 WHEN a chat reply needs event context THEN the system SHALL CONTINUE TO retrieve context through the existing `rag_db` integration.
3.3 WHEN reply generation or context retrieval raises an exception THEN the system SHALL CONTINUE TO catch the exception, log the chat error, and return exactly `I'm sorry, I am having trouble connecting to my AI brain right now. Please try again later.`.
3.4 WHEN audio generation is requested THEN the system SHALL CONTINUE TO use the existing `generate_audio` pyttsx3 behavior without modification.
3.5 WHEN this bugfix is implemented THEN the system SHALL CONTINUE TO leave every file other than `app/services/ai_service.py` unchanged.
