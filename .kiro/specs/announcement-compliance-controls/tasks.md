# Implementation Plan: Announcement Compliance Controls

## Overview

Extend the existing Python 3.10/FastAPI/SQLite announcement flow in place, then wire the logs API, application watchdog lifecycle, and Vanilla JavaScript participant/admin controls together. All production edits remain limited to the five approved implementation files; automated checks use isolated ephemeral harnesses because repository test files are outside the approved scope.

## Tasks

- [ ] 1. Extend acknowledgement persistence in the existing announcement service
  - [x] 1.1 Add the acknowledgement audit schema and retrieval operation
    - Extend `init_db()` in `app/services/announcement_service.py` to create `acknowledgement_logs` with the required auto-incrementing key and non-null text columns without changing existing schema or sample-data initialization.
    - Add `get_acknowledgement_logs(announcement_id: str)` using the existing SQLite connection conventions and return matching rows as dictionaries or an empty list.
    - Keep all imports `app.`-prefixed where application imports are needed and retain Python 3.10 compatibility.
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.10, 2.4, 2.5, 2.7, 2.8, 2.9, 4.1, 4.2, 4.3, 4.4, 4.5, 4.11, 4.12, 4.13, 4.14, 4.15_

  - [x] 1.2 Make first acknowledgement transitions write exactly one durable audit row
    - Extend the existing `acknowledge()` transaction so a successful unacknowledged-to-acknowledged transition inserts one row with the announcement ID, participant name as `user_id`, and `datetime.now(timezone.utc).isoformat()` before the existing commit.
    - Preserve idempotency for repeated acknowledgements and ensure recipient update and log insertion commit or roll back together.
    - Preserve existing acknowledgement return values, validation, error behavior, CRUD behavior, and teammate code.
    - _Requirements: 2.3, 2.8, 4.6, 4.7, 4.8, 4.9, 4.10, 4.15_

  - [-] 1.3 Write ephemeral unit and transaction tests for acknowledgement audit behavior
    - In an isolated external Python harness, exercise schema initialization, filtered retrieval, empty results, exact first-transition insertion, repeat acknowledgement idempotency, transaction rollback, and retrieval after reopening the SQLite database.
    - Verify existing initialization and acknowledgement responses remain unchanged; remove the harness and temporary database after the checks.
    - _Requirements: 2.3, 2.4, 2.5, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 4.13, 4.14, 4.15_

- [ ] 2. Implement Critical-announcement deadline monitoring
  - [x] 2.1 Add the asynchronous escalation notifier and watchdog
    - Add `notify_escalation(user_id, announcement_id)` with the exact warning message and `monitor_overdue_acknowledgements()` with an unbounded asynchronous loop in `app/services/announcement_service.py`.
    - Query only tracked, unacknowledged, acknowledgement-required announcements whose priority is exactly `Critical`; parse publication timestamps with the specified ISO conversion and apply the strict greater-than 24-hour comparison.
    - Await one notifier call for each overdue result, emit nothing for non-overdue results, and await `asyncio.sleep(300)` after each completed query iteration.
    - _Requirements: 1.3, 1.5, 2.8, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10_

  - [~] 2.2 Write ephemeral asynchronous tests for watchdog classification and timing
    - Use an isolated Python harness with mocked SQLite rows, clock values, logger, notifier, and sleep to cover before, exactly at, and after the 24-hour boundary; include `Z` and offset-aware publication timestamps.
    - Verify only qualifying Critical recipient rows escalate, arguments and warning text are exact, non-overdue rows remain silent, and every completed iteration sleeps for 300 seconds without entering a real unbounded run.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10_

- [ ] 3. Expose logs and start the watchdog through existing FastAPI integration points
  - [~] 3.1 Add the acknowledgement logs endpoint to the existing announcements router
    - Add `GET /api/v1/announcements/{announcement_id}/logs` in `app/routers/announcements.py`, pass the path identifier to the service retrieval function, and return `{"status": "success", "data": logs}`.
    - Keep the service call and success response in one `try` block and translate retrieval exceptions to `HTTPException(status_code=500, ...)` in the corresponding `except` block.
    - Preserve every existing route path, method, response contract, and application import convention.
    - _Requirements: 1.4, 1.10, 2.2, 2.3, 2.8, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9_

  - [~] 3.2 Register exactly one watchdog task in the existing application startup flow
    - Import standard-library `asyncio` and import `monitor_overdue_acknowledgements` through an `app.`-prefixed import in `app/main.py`.
    - Extend the existing announcement startup handler in place with the exact `asyncio.create_task(monitor_overdue_acknowledgements())` call, retaining a task reference if needed without adding or reordering lifecycle handlers.
    - Preserve every initialization statement, startup handler order, shutdown behavior, lifespan behavior, route, and unrelated teammate code.
    - _Requirements: 1.3, 1.4, 1.10, 2.6, 2.7, 2.8, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [~] 3.3 Write ephemeral FastAPI integration tests for the logs route and startup registration
    - Use dependency/mocking boundaries in an external harness to verify success with populated and empty logs, identifier forwarding, 500 error translation, and preservation of the pre-existing route table.
    - Exercise startup with the watchdog coroutine mocked so exactly one task is created while existing startup handlers execute once and in their original order; clean up the created task and all temporary artifacts.
    - _Requirements: 2.2, 2.3, 2.6, 2.7, 6.3, 6.4, 6.5, 6.6, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9_

- [ ] 4. Add independent participant compliance timers
  - [~] 4.1 Implement the five-second acknowledgement-button delay
    - In `templates/announcements.html`, render each eligible unacknowledged control with the `ack-btn` class, initially disabled, and with `opacity-50 cursor-not-allowed` while preserving the existing acknowledgement action and card rendering.
    - Capture each button's original text, display `Please read... (5s)` initially, update a separate whole-second countdown every 1000 milliseconds, and prevent enablement before 5000 milliseconds.
    - At 5000 milliseconds clear only that button's interval, enable it, remove both disabled-state classes, restore its captured text, and keep multiple button countdowns independent across re-renders.
    - _Requirements: 1.6, 1.8, 1.9, 2.1, 2.3, 2.8, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13_

  - [~] 4.2 Implement independent 24-hour Critical countdown displays
    - Render a `critical-timer text-red-400 text-sm font-bold mt-2` element inside each Critical card with the announcement's escaped `published_at` value in `data-published`.
    - Update each timer immediately and every 1000 milliseconds, computing the deadline by adding exactly `86400000` milliseconds and showing zero-padded whole `HH:MM:SS` while time remains.
    - For expired timers, show exactly `DEADLINE MISSED - ESCALATED` and clear only that timer's interval; handle invalid dates without throwing and keep all timer state independent.
    - _Requirements: 1.6, 1.8, 1.9, 2.1, 2.3, 2.8, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12, 9.13_

  - [~] 4.3 Write ephemeral browser-script tests for participant timers
    - Load the template script in an isolated DOM/fake-timer harness and verify initial button state/text/classes, no early activation, exact five-second restoration, independent buttons, and preserved acknowledgement click behavior.
    - Generate representative valid, expired, boundary, offset-aware, and invalid publication values to verify immediate rendering, exact deadline arithmetic and terminal text, zero padding, interval cleanup, and independence without committing a test file.
    - _Requirements: 2.1, 2.3, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12, 9.13_

- [ ] 5. Add the administration acknowledgement-log display
  - [~] 5.1 Render and populate announcement-specific log controls safely
    - In `templates/admin_announcements.html`, add an exact `View Logs` button beneath each announcement's details/actions and a matching announcement-specific logs container without changing existing card actions or template includes.
    - Add asynchronous `viewLogs(id)`, wire each button to its announcement ID, and fetch `/api/v1/announcements/${id}/logs`.
    - Render every result as exactly `User ${log.user_id} at ${log.timestamp}`, escape both values before HTML injection, and render the exact empty and failure messages in only the matching container.
    - _Requirements: 1.7, 1.8, 1.9, 2.1, 2.3, 2.8, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12_

  - [~] 5.2 Write ephemeral browser-script tests for admin log rendering
    - In an isolated DOM harness, mock success, empty, malformed, and rejected responses and verify exact fetch URL, announcement-container targeting, all-row rendering, and exact empty/error messages.
    - Include HTML-bearing `user_id` and `timestamp` values to prove they are displayed as text rather than executable markup while existing publish, stats, edit, and delete controls remain wired.
    - _Requirements: 2.1, 2.3, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12_

- [~] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Wire and validate the complete five-file feature
  - [~] 7.1 Complete cross-layer integration and preservation checks
    - Verify the participant acknowledgement request reaches the transaction that creates one audit row, the logs endpoint retrieves that row, and the admin control renders it in the corresponding card container.
    - Verify published Critical recipient records feed both the participant deadline display and watchdog query without changing existing publication, recipient tracking, CRUD, route, template include, or initialization behavior.
    - Inspect the implementation diff and fail validation if any application file outside the five approved files changed, any new application/test/configuration file was added, any import under `app` lacks the `app.` prefix, or any React/Next.js/legacy `frontend/`/`backend/` dependency appears.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 4.6, 4.10, 4.15, 5.5, 5.8, 6.3, 7.3, 7.4, 8.5, 8.6, 8.7, 9.1, 9.3_

  - [~] 7.2 Run an ephemeral end-to-end automated regression harness
    - Use temporary SQLite state, FastAPI test requests, mocked watchdog timing, and an isolated browser DOM to automate the first/repeated acknowledgement, persisted logs retrieval, admin rendering, five-second control delay, Critical countdown, and overdue/non-overdue escalation paths.
    - Re-run focused regressions for all pre-existing announcement routes, initialization/sample data, startup handlers, template composition, and card actions; remove all external harness artifacts after completion.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3.8, 3.9, 3.10, 3.13, 4.6, 4.10, 4.15, 5.8, 5.9, 5.10, 6.3, 6.5, 6.6, 7.4, 7.7, 7.8, 8.8, 8.9, 8.10, 8.11, 8.12, 9.9, 9.10, 9.11, 9.12, 9.13_

- [~] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and may be skipped for a faster MVP; implementation tasks are mandatory.
- The design has no `Correctness Properties` section or numbered properties, so this plan does not invent property-based test tasks. Its optional automated tests are unit, transaction, integration, browser-script, and end-to-end checks run from ephemeral external harnesses as required by the five-file boundary.
- No repository test files, dependencies, migrations, configuration files, application files outside the five-file scope, or changes under legacy `frontend/` or `backend/` are permitted.
- Each task references granular acceptance criteria for traceability, and the final integration task verifies both feature behavior and preservation constraints.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "2.1"] },
    { "id": 3, "tasks": ["2.2", "3.1", "3.2", "4.1", "5.1"] },
    { "id": 4, "tasks": ["3.3", "4.2", "5.2"] },
    { "id": 5, "tasks": ["4.3", "7.1"] },
    { "id": 6, "tasks": ["7.2"] }
  ]
}
```
