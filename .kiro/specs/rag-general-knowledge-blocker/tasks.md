# Implementation Plan

## Overview

Explore and preserve the unfixed behavior with ephemeral external property-based tests, apply the narrowly scoped routing fix only in `app/services/ai_service.py`, and replay the same checks to validate correctness and preservation.

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2"] },
    { "wave": 2, "tasks": ["3.1"] },
    { "wave": 3, "tasks": ["3.2", "3.3"] },
    { "wave": 4, "tasks": ["4"] }
  ]
}
```

- Tasks 1 and 2 are independent pre-implementation checks and may run in parallel.
- Task 3.1 depends on completion of tasks 1 and 2.
- Task 3.2 depends on tasks 1 and 3.1; task 3.3 depends on tasks 2 and 3.1.
- Task 4 depends on tasks 3.2 and 3.3.

## Notes

- All test code, generated fixtures, and baseline captures must remain ephemeral or external and must not be committed anywhere in the repository.
- The implementation scope permits production changes only to `app/services/ai_service.py`; approved prerequisite documents remain unchanged.

## Tasks

- [x] 1. Write and run the bug-condition exploration property test in an ephemeral external harness
  - **Property 1: Bug Condition** - Route No-Fact and Verified-Fact Queries Correctly
  - **CRITICAL**: Create no repository test file and make no production change; run the property-based harness from a temporary/external location against the unfixed `ChatPipeline.generate_reply`.
  - Model `isBugCondition(input)` from the design: retrieval succeeds and either `retrievedContext` is `None`, empty, Unicode-whitespace-only, or exactly `No verified knowledge-base sources matched this question.` without correct model routing, or a relevant verified event fact is not included unchanged in the prompt context.
  - Generate the no-facts variants plus representative science, translation, Singapore tourism, casual-chat, missing-event, and verified-event questions; include `[Source: University event]\n[Category: Event]\nDate 29/7/2026` as the deterministic relevant-fact case.
  - Assert `expectedBehavior(input, result)`: one unchanged `rag_db.retrieve_context(user_text)` call, one model invocation after successful retrieval, the exact approved prompt, exact `No verified facts found for this query.` normalization only for unusable context, unchanged usable context, relevant-fact prioritization, exact missing-event fallback, and brief helpful general-knowledge routing.
  - Run on unfixed code and expect the property to FAIL; do not fix the test or code when it fails. Record the exact minimized counterexample and whether it demonstrates sentinel misclassification, premature return, or relevant-context loss, then remove the ephemeral harness.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4_

- [x] 2. Write and run preservation property tests in an ephemeral external harness before implementation
  - **Property 2: Preservation** - Existing Pipeline Contracts Remain Unchanged
  - **IMPORTANT**: Follow observation-first methodology without adding or changing repository files: capture the unfixed baseline first, then encode the observed behavior in temporary/external property-based tests.
  - For inputs where `isBugCondition(input)` is false, generate usable non-sentinel contexts and verify exact context identity, call order, one retrieval await with unchanged `user_text`, exact approved system prompt and `{input}` template, and unchanged model result propagation.
  - Generate retrieval and model exceptions and record the catch, chat-error log event, and exact connection fallback; generate audio text/error cases through mocked pyttsx3 and record `generate_audio` results, failures, cleanup, and logging.
  - Snapshot externally the import block, model configuration and initialization, exact prompt/fallback strings, `generate_audio` source, and repository status/hash baseline needed to prove that implementation changes no repository file except `app/services/ai_service.py`.
  - Run on unfixed code and require all preservation properties to PASS; retain baseline observations outside the repository for post-fix differential checking and remove executable temporary artifacts when validation finishes.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 3. Fix successful-retrieval routing in `ChatPipeline.generate_reply`

  - [x] 3.1 Implement the narrowly scoped context normalization fix
    - Modify only `app/services/ai_service.py`; leave every other production, test, configuration, requirements, and spec prerequisite file unchanged.
    - Continue awaiting `rag_db.retrieve_context(user_text)` exactly once inside the existing `try`; classify `None`, empty, whitespace-only, and the exact RAG no-match sentinel as unusable and normalize them to the exact no-facts marker.
    - Pass every other retrieved context through unchanged, remove or avoid any successful-retrieval early fallback, and always format messages and invoke the model after successful retrieval; do not classify event versus general questions in Python.
    - Retain all imports, initialization/model selection, exact approved prompt and `{input}` template, exception/logging behavior, connection fallback, and the complete `generate_audio` implementation unchanged.
    - _Bug_Condition: `isBugCondition(input)` from Design > Bug Details, covering blocked no-facts requests and loss of relevant verified context_
    - _Expected_Behavior: `expectedBehavior(input, result)` from Design > Correctness Properties, including exact normalization, prompt use, one retrieval/model call, event fallback, general knowledge, and relevant-fact priority_
    - _Preservation: Design > Expected Behavior > Preservation Requirements, including exact source regions and the single-file production-change boundary_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.2 Verify the original bug-condition exploration property now passes
    - **Property 1: Expected Behavior** - Route No-Fact and Verified-Fact Queries Correctly
    - Re-run the SAME external property test and recorded counterexample from task 1; do not add a repository test file or weaken the generated domain.
    - Require all no-facts variants to receive the exact marker, all usable contexts to remain unchanged, retrieval and model invocation counts to be exactly one, and the approved routing outcomes to hold; expect PASS and remove the harness afterward.
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.3 Verify the original preservation properties still pass
    - **Property 2: Preservation** - Existing Pipeline Contracts Remain Unchanged
    - Re-run the SAME external tests from task 2 and compare against the recorded unfixed baseline; do not write new repository tests.
    - Require equivalent usable-context, exception, logging, model, and mocked-audio behavior; require exact protected source text and a repository diff containing no implementation change outside `app/services/ai_service.py`.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Checkpoint - validate the complete bugfix without persistent test artifacts
  - Run the ephemeral unit/property checks and focused integration smoke cases for general knowledge with no facts, missing IOAI logistics, the verified `University event` date, retrieval/model exceptions, and mocked audio behavior.
  - Confirm all checks pass, delete temporary/external harness artifacts, and inspect the final diff: among implementation files only `app/services/ai_service.py` may differ, while approved `bugfix.md`, `design.md`, `.config.kiro`, and all other prerequisite/repository files remain unchanged.
  - Ask the user if questions arise.
