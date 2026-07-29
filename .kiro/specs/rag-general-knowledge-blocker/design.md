# RAG General Knowledge Blocker Bugfix Design

## Overview

This bugfix removes the reply-generation gate that treats an empty RAG result as a reason to return the verified-database fallback before consulting the language model. `ChatPipeline.generate_reply` will continue to retrieve through the existing `rag_db`, but it will normalize retrieval results that contain no usable verified facts to the exact context marker `No verified facts found for this query.` and always pass the request to the model. The exact concierge prompt then decides whether to use a relevant verified event fact, issue the exact missing-event fallback, or answer a clearly non-event question with general knowledge.

The implementation boundary is strictly `app/services/ai_service.py`. The existing imports, RAG integration, prompt and fallback strings, exception behavior, and `generate_audio` implementation remain unchanged. `app/services/rag_service.py` is read-only context: its contract returns formatted source blocks when entries exist and currently returns `No verified knowledge-base sources matched this question.` when no entries exist.

## Glossary

- **Bug_Condition (C)**: A successfully retrieved request is blocked before model invocation when no usable facts exist, or a usable relevant verified fact is not supplied to the model.
- **Property (P)**: The reply path invokes the model with the exact concierge prompt and either normalized no-facts context or unchanged usable verified context.
- **Preservation**: Behavior outside the defective routing decision that must remain byte-for-byte or observably unchanged.
- **Usable_Verified_Context**: A non-empty retrieval string containing formatted knowledge-base source content, rather than an empty value, whitespace, or the RAG no-match sentinel.
- **No_Facts_Marker**: The exact string `No verified facts found for this query.` supplied as prompt context when retrieval has no usable facts.
- **RAG_No_Match_Sentinel**: The current `rag_db.retrieve_context` empty-result string: `No verified knowledge-base sources matched this question.`
- **Event_Fallback**: The exact prompt-mandated reply `I do not have that specific event information yet. Please check the Schedule tab.`
- **Connection_Fallback**: The exact exception reply `I'm sorry, I am having trouble connecting to my AI brain right now. Please try again later.`
- **`ChatPipeline.generate_reply`**: The asynchronous method in `app/services/ai_service.py` that retrieves context, formats messages, invokes the model, and handles chat errors.
- **`rag_db`**: The existing `KnowledgeBase` singleton imported exactly with `from app.services.rag_service import rag_db`.

## Bug Details

### Bug Condition

The defect occurs after successful context retrieval when reply generation treats an empty or semantically empty retrieval result as a terminal condition, preventing the exact prompt from distinguishing general knowledge from missing event information. It also includes routing that fails to pass an available relevant verified event fact to the model.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input containing userText, retrievedContext, modelInvoked, promptContext
  OUTPUT: boolean

  noUsableFacts := retrievedContext IS null
                   OR trim(string(retrievedContext)) = ""
                   OR trim(string(retrievedContext)) =
                      "No verified knowledge-base sources matched this question."
  relevantFactAvailable := containsRelevantVerifiedEventFact(
                             retrievedContext, input.userText)

  RETURN retrievalSucceeded(input)
         AND ((noUsableFacts AND NOT modelInvoked)
              OR (relevantFactAvailable
                  AND NOT promptContextContainsFactUnchanged(retrievedContext)))
END FUNCTION
```
### Examples

- **General science, empty retrieval**: For `Why is the sky blue?` with the RAG no-match sentinel, the defective path returns an event-information fallback without model invocation. The fixed path invokes the model with the No_Facts_Marker and permits a brief general-knowledge answer.
- **Translation, blank retrieval**: For `How do I say thank you in Malay?` with whitespace-only context, the defective path blocks the answer. The fixed path supplies the No_Facts_Marker and lets the prompt permit a helpful translation.
- **Verified event fact**: For an IOAI event-date question with context `[Source: University event]\n[Category: Event]\nDate 29/7/2026`, the fixed path passes that context unchanged and the answer prioritizes `29/7/2026`.
- **Missing event logistics**: For `Where is tomorrow's IOAI shuttle pickup?` with no usable facts, the model is invoked and the prompt requires exactly `I do not have that specific event information yet. Please check the Schedule tab.`
- **Retrieval exception**: If retrieval raises, this is outside the successful-retrieval bug condition; the existing catch-and-log path returns the Connection_Fallback unchanged.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Keep every existing import in `app/services/ai_service.py`; every internal application import continues to start with `app`, including exactly `from app.services.rag_service import rag_db`.
- Await `rag_db.retrieve_context(user_text)` for event context using the unchanged user text and existing asynchronous integration.
- Preserve the exact system prompt, including whitespace, punctuation, capitalization, `{context}`, the exact Event_Fallback text, and the `{input}` user-message template.
- Preserve the broad `generate_reply` exception boundary, chat-error logging, and exact Connection_Fallback return value.
- Preserve usable retrieved context without rewriting, filtering, reordering, or replacing its source, category, or content text.
- Preserve `generate_audio`, its pyttsx3 behavior, temporary-file lifecycle, base64 response shape, errors, and logging without modification.
- Leave every repository file other than `app/services/ai_service.py` unchanged during implementation.

**Scope:**
All behavior outside successful reply routing for no-facts or relevant-fact retrieval results is unaffected. This includes:
- retrieval failures and model invocation failures;
- non-empty usable context formatting supplied by `rag_db`;
- module initialization, model selection, environment loading, and logging;
- audio requests and all `generate_audio` inputs;
- RAG storage, retrieval, and compatibility APIs in `app/services/rag_service.py`.

## Hypothesized Root Cause

1. **Truthiness does not represent retrieval usability**: `rag_db.retrieve_context` returns a non-empty no-match sentinel when the collection has no entries.
   - A check limited to `if context` or `if str(context).strip()` classifies that sentinel as usable verified context.
   - `ai_service.py` must adapt the retrieval contract locally because `rag_service.py` cannot be changed.

2. **Premature reply routing**: The defective flow returns a verified-database fallback before prompt formatting and `llm.ainvoke` when retrieval appears empty.
   - This prevents the prompt from classifying clearly non-event questions as eligible for general knowledge.
   - The reply path should have no successful-retrieval early return before model invocation.

3. **Relevant-context gate or substitution**: A broad empty/invalid-context branch can discard context that actually contains a relevant event fact.
   - Usable formatted retrieval output must be forwarded unchanged.
   - The `University event` source label and `Event` category are meaningful evidence and must not be collapsed.

4. **Prompt instruction drift**: Earlier instructions may not have separated verified facts, missing event facts, and general knowledge clearly enough.
   - The current approved prompt already expresses that separation and must be retained exactly rather than paraphrased.
## Correctness Properties

**Expected-behavior specification:**
```
FUNCTION expectedBehavior(input, result)
  INPUT: input containing userText and retrievedContext; result from fixed generate_reply
  OUTPUT: boolean

  noUsableFacts := retrievedContext IS null
                   OR trim(string(retrievedContext)) = ""
                   OR trim(string(retrievedContext)) =
                      "No verified knowledge-base sources matched this question."
  expectedContext := IF noUsableFacts
                     THEN "No verified facts found for this query."
                     ELSE retrievedContext

  RETURN ragRetrievalCalledExactlyOnceWith(input.userText)
         AND exactApprovedPromptUsed()
         AND promptContext = expectedContext
         AND modelInvokedExactlyOnce()
         AND (NOT containsRelevantVerifiedEventFact(
                    retrievedContext, input.userText)
              OR responsePrioritizesRelevantFact(result, retrievedContext))
         AND (NOT (noUsableFacts AND isMissingEventQuestion(input.userText))
              OR result = "I do not have that specific event information yet. Please check the Schedule tab.")
         AND (NOT (noUsableFacts AND isClearlyNonEventQuestion(input.userText))
              OR isHelpfulBriefGeneralKnowledgeAnswer(result))
END FUNCTION
```

Property 1: Bug Condition - Route No-Fact and Verified-Fact Queries Correctly

_For any_ input where the bug condition holds (`isBugCondition` returns true), the fixed `generate_reply` function SHALL satisfy `expectedBehavior`: normalize empty, blank, or RAG-no-match context to the exact No_Facts_Marker; preserve usable relevant verified context unchanged; invoke the language model with the exact approved prompt; prioritize relevant verified facts; use the exact Event_Fallback for missing IOAI information; and permit concise helpful general knowledge for clearly non-event questions.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation - Existing Pipeline Contracts Remain Unchanged

_For any_ input where the bug condition does NOT hold (`isBugCondition` returns false), the fixed pipeline SHALL produce the same observable result as the original pipeline, preserving imports, the `rag_db` call contract, usable context text, exact prompt and fallback strings, exception logging and return behavior, model configuration, and audio generation; implementation SHALL not alter any file other than `app/services/ai_service.py`.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming the root-cause analysis is correct:

**File**: `app/services/ai_service.py`

**Function**: `ChatPipeline.generate_reply` (with the existing `ChatPipeline.__init__` prompt retained exactly)

**Specific Changes**:
1. **Preserve retrieval integration**: Continue to await `rag_db.retrieve_context(user_text)` exactly once inside the existing `try` block.
2. **Classify unusable retrieval locally**: Treat `None`, an empty string, whitespace-only text, and the exact RAG_No_Match_Sentinel as having no usable verified facts.
3. **Normalize only no-facts results**: Set prompt context to the exact No_Facts_Marker for those values; pass every other retrieved context value through unchanged.
4. **Remove successful-retrieval early fallback**: Always call `self.prompt.format_messages` and `self.llm.ainvoke` after retrieval succeeds. Do not hard-code event/general question classification in Python.
5. **Retain approved model instructions**: Keep the exact prompt shown below so the model, rather than the retrieval gate, selects verified facts, Event_Fallback, or allowed general knowledge.
6. **Preserve error and audio paths**: Do not modify imports, initialization, exception handling, Connection_Fallback, `generate_audio`, or any other repository file.
**Exact prompt to preserve:**
```text
You are the official IOAI 2027 AI Concierge in Singapore.

CRITICAL INSTRUCTIONS:
VERIFIED FACTS: Read the 'Verified Event Database' below. If it contains information relevant to the user's question, you MUST use it and prioritize it.
MISSING FACTS: If the user asks about the IOAI event, schedule, or logistics, but the database is empty or lacks the answer, reply EXACTLY: 'I do not have that specific event information yet. Please check the Schedule tab.'
GENERAL KNOWLEDGE: If the user asks a general question (e.g., science, translation, general Singapore tourism, or casual chat) that is clearly outside the scope of IOAI logistics, you may use your general knowledge to answer them helpfully.
TONE: Be enthusiastic, concise, and youth-friendly. Keep answers brief (1-3 sentences).

Verified Event Database: {context}
```

The user message remains exactly `{input}`. The normalization can be expressed without changing the retrieval service:
```
retrievedContext := AWAIT rag_db.retrieve_context(userText)
IF retrievedContext is null
   OR trim(string(retrievedContext)) = ""
   OR trim(string(retrievedContext)) = RAG_No_Match_Sentinel THEN
  promptContext := No_Facts_Marker
ELSE
  promptContext := retrievedContext
END IF
messages := prompt.format_messages(context=promptContext, input=userText)
response := AWAIT llm.ainvoke(messages)
RETURN response.content
```

## Testing Strategy

### Validation Approach

Validation first captures counterexamples against the unfixed behavior, then checks the fixed bug domain and compares all preserved behavior against the baseline. Because Requirement 3.5 forbids repository changes outside `app/services/ai_service.py`, test code and fixtures must be executed through an ephemeral or external harness and must not be committed to `tests/` or any other project file.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples before implementation and confirm whether the failure is an early return, incorrect no-facts classification, or loss of usable context. If these tests refute the hypothesis, revisit the root-cause analysis before changing code.

**Test Plan**: Replace `rag_db` and `llm` with asynchronous test doubles at runtime, invoke `generate_reply`, and inspect retrieval calls, formatted messages, model calls, and returned content on the unfixed baseline.

**Test Cases**:
1. **RAG sentinel/general science**: Return the RAG_No_Match_Sentinel for `Why is the sky blue?`; verify whether the LLM is skipped or receives the wrong context (expected counterexample on unfixed code).
2. **Empty context/translation**: Return `""` for a translation request; verify whether an early Event_Fallback is returned (expected counterexample on unfixed code).
3. **Verified University event**: Return `[Source: University event]\n[Category: Event]\nDate 29/7/2026`; verify whether the exact context reaches the model and the answer includes the date (expected counterexample if relevant context is discarded).
4. **Whitespace edge case**: Return generated whitespace-only strings; verify that none are treated as verified facts (may expose additional unfixed counterexamples).

**Expected Counterexamples**:
- `llm.ainvoke` is not called after successful empty retrieval, or it receives the RAG_No_Match_Sentinel instead of the No_Facts_Marker.
- A relevant formatted event block is replaced by a fallback or otherwise fails to reach the prompt unchanged.
- Possible causes: premature return, truthiness-only context classification, or context substitution.
### Fix Checking

**Goal**: Verify that every successful-retrieval input in the bug domain reaches the model with the correct context and satisfies the approved routing behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := generateReply_fixed(input.userText)
  ASSERT expectedBehavior(input, result)
END FOR
```

Check null, empty, whitespace, and exact RAG sentinel values against the No_Facts_Marker. Check arbitrary usable contexts for identity preservation. Use representative question classes to verify permitted general knowledge, exact missing-event fallback, and prioritization of the `University event` date.

### Preservation Checking

**Goal**: Verify that inputs outside the bug condition retain baseline behavior and that protected source regions are unchanged.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  originalResult := generateReply_original(input)
  fixedResult := generateReply_fixed(input)
  ASSERT observableBehavior(originalResult) = observableBehavior(fixedResult)
END FOR
ASSERT imports_original = imports_fixed
ASSERT prompt_original = prompt_fixed = approvedExactPrompt
ASSERT generateAudioSource_original = generateAudioSource_fixed
ASSERT changedRepositoryFiles = {"app/services/ai_service.py"}
```

**Testing Approach**: Property-based differential checks generate context and failure variants around the narrow normalization boundary. Static source comparison protects exact strings and untouched code. Runtime doubles capture asynchronous calls without changing production integrations.

**Test Plan**: Record baseline results and side effects for usable contexts, retrieval exceptions, LLM exceptions, and audio behavior. After the fix, replay the same generated inputs and compare return values, calls, log events, and protected source text.

**Test Cases**:
1. **Usable context preservation**: Generated non-empty context other than the sentinel is passed through with exact string identity and the same call order.
2. **Exception preservation**: Retrieval and model exceptions are caught, chat errors are logged, and the exact Connection_Fallback is returned.
3. **Source preservation**: Imports, exact approved prompt, `generate_audio`, and all files outside `ai_service.py` match the baseline.
4. **RAG call preservation**: Retrieval is awaited exactly once with the original `user_text`.

### Unit Tests

- Parameterize no-facts normalization over `None`, `""`, whitespace-only strings, and the exact RAG_No_Match_Sentinel; assert the exact No_Facts_Marker and one model invocation.
- Verify a usable formatted context, especially `[Source: University event]\n[Category: Event]\nDate 29/7/2026`, is passed unchanged.
- Assert the exact system prompt and `{input}` user template, including all whitespace and fallback punctuation.
- Inject exceptions from retrieval and model invocation; assert chat-error logging and the exact Connection_Fallback.
- Compare the import block and `generate_audio` source before and after implementation.

### Property-Based Tests

- Generate arbitrary `None`, empty, and Unicode-whitespace context values and verify they normalize to the No_Facts_Marker and invoke the model exactly once.
- Generate arbitrary non-empty context strings excluding the exact RAG_No_Match_Sentinel and verify they are forwarded unchanged.
- Generate clearly non-event prompts from science, translation, Singapore tourism, and casual-chat categories with no usable facts; verify no pre-model Event_Fallback occurs.
- Generate exceptions at each awaited reply stage and verify the exception preservation property.
- Generate audio text inputs and compare baseline versus fixed `generate_audio` behavior through a mocked pyttsx3 boundary.

### Integration Tests

- Run the complete `ChatPipeline.generate_reply` flow with an empty knowledge base contract result and a clearly non-event question; confirm prompt context is the No_Facts_Marker and a concise general answer is returned.
- Run the flow with the stored `University event` record (`Event`, `Date 29/7/2026`); confirm retrieval remains through `rag_db` and the answer prioritizes the verified date.
- Run an unanswered IOAI schedule/logistics query; confirm the model receives the no-facts marker and returns the exact Event_Fallback.
- Smoke-test chat exception handling and audio generation to confirm both integrations remain unchanged.
- Inspect the final repository diff and require that `app/services/ai_service.py` is the only modified application or repository file.