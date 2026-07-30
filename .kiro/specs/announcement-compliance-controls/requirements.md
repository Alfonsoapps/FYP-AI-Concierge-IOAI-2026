# Requirements Document

## Introduction

The Announcement Compliance Controls feature extends the existing announcement capability with a mandatory five-second acknowledgement delay, a 24-hour Critical announcement countdown and escalation watchdog, durable acknowledgement audit records, a logs API, and an administration logs display. The feature is an additive change to the current Python 3.10, FastAPI, SQLite, Jinja2, HTML5, Tailwind, and Vanilla JavaScript application. Eventual implementation is restricted to the five files named in this document; this phase changes requirements only and does not implement application code.

## Glossary

- **Compliance_Controls**: The complete feature specified by this document.
- **Announcement_Service**: The persistence and business-logic module at `app/services/announcement_service.py`.
- **Announcements_Router**: The FastAPI router at `app/routers/announcements.py`.
- **Application**: The existing FastAPI application rooted at `app/main.py`.
- **Application_Lifecycle**: The existing application startup, shutdown, and lifespan behavior, including registered startup handlers.
- **Participant_UI**: The Jinja2 and HTML5 participant page at `templates/announcements.html`.
- **Admin_UI**: The Jinja2 and HTML5 administration page at `templates/admin_announcements.html`.
- **Implementation_Files**: `app/services/announcement_service.py`, `app/routers/announcements.py`, `app/main.py`, `templates/announcements.html`, and `templates/admin_announcements.html`.
- **Application_Import**: A Python import of a module located under the repository's `app` package.
- **Teammate_Code**: Existing application code and behavior not explicitly changed by an acceptance criterion in this document.
- **Acknowledge_Button**: A participant control with the `ack-btn` class that invokes the existing acknowledgement operation.
- **Acknowledgement_Log**: A durable row in `acknowledgement_logs` containing `id`, `announcement_id`, `user_id`, and `timestamp`.
- **User_ID**: The existing participant identity value supplied as `participant_name`, stored in an Acknowledgement_Log as `user_id`.
- **Critical_Announcement**: A published announcement whose `priority` value is exactly `Critical`.
- **Tracked_Recipient**: A row in `announcement_recipients` that associates a participant with an announcement.
- **Unacknowledged_Critical_Announcement**: A Critical_Announcement requiring acknowledgement whose Tracked_Recipient has a null `acknowledged_at` value.
- **Published_Date**: The Critical_Announcement publication timestamp stored as `published_at` and supplied to watchdog processing as `pub_date`.
- **Watchdog**: The asynchronous `monitor_overdue_acknowledgements()` operation.
- **Escalation_Notifier**: The asynchronous `notify_escalation(user_id, announcement_id)` operation.
- **Logs_Endpoint**: `GET /api/v1/announcements/{announcement_id}/logs`.
- **Logs_API_Response**: The JSON object `{"status": "success", "data": logs}`.
- **Logs_Container**: The announcement-specific Admin_UI element that displays acknowledgement logs.
- **Critical_Timer**: A Participant_UI element with class `critical-timer` and a `data-published` value.
- **Vanilla_JavaScript**: Browser JavaScript implemented without React, Next.js, or another client framework.

## Requirements

### Requirement 1: Technology and File Scope

**User Story:** As a maintainer, I want the feature constrained to the current application stack and five integration files, so that the change does not introduce a parallel implementation.

#### Acceptance Criteria

1. THE Compliance_Controls SHALL limit eventual application-code changes to the Implementation_Files.
2. THE Compliance_Controls SHALL add zero application-code files outside the Implementation_Files.
3. THE Compliance_Controls SHALL remain executable with Python 3.10.
4. THE Compliance_Controls SHALL use FastAPI for HTTP routing and application lifecycle integration.
5. THE Compliance_Controls SHALL use SQLite for acknowledgement audit persistence and watchdog queries.
6. THE Participant_UI SHALL use Jinja2, HTML5, Tailwind classes, and Vanilla_JavaScript.
7. THE Admin_UI SHALL use Jinja2, HTML5, Tailwind classes, and Vanilla_JavaScript.
8. THE Compliance_Controls SHALL contain zero React or Next.js implementation dependencies.
9. THE Compliance_Controls SHALL contain zero references to the legacy `frontend/` or `backend/` directories.
10. THE Compliance_Controls SHALL prefix every Application_Import with `app.`.

### Requirement 2: Preservation of Existing Behavior

**User Story:** As a maintainer, I want compliance controls added without replacing existing functionality, so that teammate work continues to operate.

#### Acceptance Criteria

1. THE Compliance_Controls SHALL preserve the existing Jinja2 template composition and includes.
2. THE Compliance_Controls SHALL preserve every existing route path and HTTP method.
3. THE Compliance_Controls SHALL preserve every existing route response behavior not explicitly changed by this document.
4. THE Compliance_Controls SHALL preserve the existing announcement database initialization behavior while adding the `acknowledgement_logs` table.
5. THE Compliance_Controls SHALL preserve the existing sample-data initialization behavior.
6. THE Compliance_Controls SHALL preserve every existing Application_Lifecycle handler and handler order.
7. THE Compliance_Controls SHALL preserve every existing initialization statement.
8. THE Compliance_Controls SHALL preserve Teammate_Code within the Implementation_Files.
9. THE Compliance_Controls SHALL preserve all files outside the Implementation_Files without modification.

### Requirement 3: Mandatory Five-Second Acknowledgement Timer

**User Story:** As a participant, I want each acknowledgement control delayed for five seconds, so that I receive a reading period before acknowledgement.

#### Acceptance Criteria

1. WHEN the Participant_UI renders an unacknowledged announcement that requires acknowledgement, THE Participant_UI SHALL assign the `ack-btn` class to the associated Acknowledge_Button.
2. WHEN an Acknowledge_Button is rendered, THE Participant_UI SHALL disable the Acknowledge_Button before the participant can activate the Acknowledge_Button.
3. WHEN an Acknowledge_Button is rendered, THE Participant_UI SHALL add the `opacity-50` and `cursor-not-allowed` Tailwind classes to the Acknowledge_Button.
4. WHEN an Acknowledge_Button is rendered, THE Participant_UI SHALL capture the original button text for later restoration.
5. WHEN an Acknowledge_Button is rendered, THE Participant_UI SHALL initialize a separate countdown value of five seconds for the Acknowledge_Button.
6. WHEN an Acknowledge_Button countdown starts, THE Participant_UI SHALL display exactly `Please read... (5s)` on the Acknowledge_Button.
7. WHILE an Acknowledge_Button has one or more whole seconds remaining, THE Participant_UI SHALL update the displayed whole-second value at 1000-millisecond intervals.
8. WHILE fewer than 5000 milliseconds have elapsed since an Acknowledge_Button countdown started, THE Participant_UI SHALL keep the Acknowledge_Button disabled.
9. WHEN 5000 milliseconds have elapsed since an Acknowledge_Button countdown started, THE Participant_UI SHALL clear the associated interval.
10. WHEN 5000 milliseconds have elapsed since an Acknowledge_Button countdown started, THE Participant_UI SHALL enable the Acknowledge_Button.
11. WHEN 5000 milliseconds have elapsed since an Acknowledge_Button countdown started, THE Participant_UI SHALL remove the `opacity-50` and `cursor-not-allowed` classes from the Acknowledge_Button.
12. WHEN 5000 milliseconds have elapsed since an Acknowledge_Button countdown started, THE Participant_UI SHALL restore the captured original button text.
13. WHEN multiple Acknowledge_Buttons are rendered, THE Participant_UI SHALL maintain an independent countdown for each Acknowledge_Button.

### Requirement 4: Acknowledgement Audit Persistence and Retrieval

**User Story:** As an organiser, I want acknowledgements recorded durably and retrievable by announcement, so that acknowledgement activity can be audited.

#### Acceptance Criteria

1. WHEN the Announcement_Service initializes the announcement database, THE Announcement_Service SHALL create the `acknowledgement_logs` table if the table is absent.
2. THE `acknowledgement_logs` table SHALL define `id` as an auto-incrementing integer primary key.
3. THE `acknowledgement_logs` table SHALL define `announcement_id` as a non-null text value.
4. THE `acknowledgement_logs` table SHALL define `user_id` as a non-null text value.
5. THE `acknowledgement_logs` table SHALL define `timestamp` as a non-null text value.
6. WHEN the existing acknowledgement operation changes a Tracked_Recipient from unacknowledged to acknowledged, THE Announcement_Service SHALL insert exactly one Acknowledgement_Log in the same database transaction.
7. WHEN the Announcement_Service inserts an Acknowledgement_Log, THE Announcement_Service SHALL store the acknowledged announcement identifier in `announcement_id`.
8. WHEN the Announcement_Service inserts an Acknowledgement_Log, THE Announcement_Service SHALL store the User_ID in `user_id`.
9. WHEN the Announcement_Service inserts an Acknowledgement_Log, THE Announcement_Service SHALL set `timestamp` to `datetime.now(timezone.utc).isoformat()`.
10. WHEN an already acknowledged Tracked_Recipient repeats the acknowledgement operation, THE Announcement_Service SHALL preserve the existing Acknowledgement_Log count for that Tracked_Recipient and announcement.
11. THE Announcement_Service SHALL provide `get_acknowledgement_logs(announcement_id: str)`.
12. WHEN `get_acknowledgement_logs(announcement_id: str)` is called, THE Announcement_Service SHALL select Acknowledgement_Logs whose `announcement_id` equals the supplied identifier.
13. WHEN matching Acknowledgement_Logs exist, THE Announcement_Service SHALL return the matching rows as a list of dictionaries.
14. WHEN no matching Acknowledgement_Log exists, THE Announcement_Service SHALL return an empty list.
15. WHEN the Application restarts after an Acknowledgement_Log is committed, THE Announcement_Service SHALL retrieve the committed Acknowledgement_Log from SQLite.

### Requirement 5: 24-Hour Critical Announcement Watchdog

**User Story:** As an organiser, I want overdue Critical acknowledgement deadlines detected, so that missed deadlines produce escalation records.

#### Acceptance Criteria

1. THE Escalation_Notifier SHALL be declared as the asynchronous function `notify_escalation(user_id, announcement_id)`.
2. WHEN `notify_escalation(user_id, announcement_id)` executes, THE Escalation_Notifier SHALL call `logger.warning` with `ESCALATION: User {user_id} missed 24h deadline for {announcement_id}` after substituting the supplied values.
3. THE Watchdog SHALL be declared as the asynchronous function `monitor_overdue_acknowledgements()`.
4. THE Watchdog SHALL execute an unbounded asynchronous loop.
5. WHEN a Watchdog loop iteration begins, THE Watchdog SHALL query SQLite for Unacknowledged_Critical_Announcements and associated User_ID values.
6. WHEN the Watchdog evaluates a Published_Date, THE Watchdog SHALL parse the Published_Date using `datetime.fromisoformat(pub_date.replace('Z', '+00:00'))`.
7. WHEN the Watchdog evaluates an acknowledgement deadline, THE Watchdog SHALL compare the current UTC time with the parsed Published_Date plus 24 hours.
8. WHEN `datetime.now(timezone.utc) > published_date + timedelta(hours=24)` is true for an Unacknowledged_Critical_Announcement, THE Watchdog SHALL await `notify_escalation(user_id, announcement_id)` with the associated values.
9. WHEN `datetime.now(timezone.utc) > published_date + timedelta(hours=24)` is false for an Unacknowledged_Critical_Announcement, THE Watchdog SHALL preserve the announcement without emitting an escalation warning for that loop iteration.
10. WHEN a Watchdog loop iteration completes, THE Watchdog SHALL await `asyncio.sleep(300)` before starting the next query.

### Requirement 6: Watchdog Application Lifecycle Integration

**User Story:** As an operator, I want the watchdog started with the application, so that deadline monitoring runs in the application process.

#### Acceptance Criteria

1. THE `app/main.py` module SHALL import `asyncio` from the Python 3.10 standard library.
2. THE `app/main.py` module SHALL import `monitor_overdue_acknowledgements` through an `app.`-prefixed Application_Import.
3. WHEN the existing Application startup lifecycle executes, THE Application SHALL create exactly one asynchronous task for `monitor_overdue_acknowledgements()`.
4. WHEN the Application creates the Watchdog task, THE Application SHALL use `asyncio.create_task(monitor_overdue_acknowledgements())`.
5. THE Compliance_Controls SHALL preserve all pre-existing startup handlers while adding Watchdog task creation.
6. THE Compliance_Controls SHALL preserve pre-existing shutdown and lifespan behavior while adding Watchdog task creation.

### Requirement 7: Acknowledgement Logs API

**User Story:** As an organiser, I want acknowledgement logs available through an API, so that the administration page can retrieve audit records.

#### Acceptance Criteria

1. THE Announcements_Router SHALL expose the Logs_Endpoint.
2. THE Logs_Endpoint SHALL accept `announcement_id` as a path parameter.
3. WHEN the Logs_Endpoint receives a request, THE Announcements_Router SHALL call `get_acknowledgement_logs(announcement_id)` on the Announcement_Service.
4. WHEN `get_acknowledgement_logs(announcement_id)` returns `logs`, THE Announcements_Router SHALL return the Logs_API_Response.
5. THE Logs_Endpoint SHALL perform the service call within a `try` block.
6. THE Logs_Endpoint SHALL return the success response within the same `try` block as the service call.
7. IF the Logs_Endpoint catches an exception from acknowledgement-log retrieval, THEN THE Announcements_Router SHALL raise an `HTTPException` from the `except` block.
8. IF the Logs_Endpoint catches an exception from acknowledgement-log retrieval, THEN THE Announcements_Router SHALL set the `HTTPException` status code to 500.
9. THE Announcements_Router SHALL preserve every route that existed before the Logs_Endpoint was added.

### Requirement 8: Administration Acknowledgement Logs UI

**User Story:** As an organiser, I want to view acknowledgement logs beneath each announcement, so that I can inspect acknowledgement users and timestamps.

#### Acceptance Criteria

1. WHEN the Admin_UI renders an announcement card, THE Admin_UI SHALL render a button with the exact text `View Logs` beneath the announcement details.
2. WHEN the Admin_UI renders a `View Logs` button, THE Admin_UI SHALL associate the button with the corresponding announcement identifier.
3. WHEN the Admin_UI renders an announcement card, THE Admin_UI SHALL render a matching Logs_Container beneath the card actions.
4. THE Admin_UI SHALL provide the asynchronous Vanilla_JavaScript function `viewLogs(id)`.
5. WHEN an organiser activates a `View Logs` button, THE Admin_UI SHALL invoke `viewLogs(id)` with the corresponding announcement identifier.
6. WHEN `viewLogs(id)` executes, THE Admin_UI SHALL fetch `/api/v1/announcements/${id}/logs`.
7. WHEN the logs fetch succeeds, THE Admin_UI SHALL read the `data` field from the Logs_API_Response.
8. WHEN `data` contains an Acknowledgement_Log, THE Admin_UI SHALL format the visible log text exactly as `User ${log.user_id} at ${log.timestamp}`.
9. WHEN `data` contains multiple Acknowledgement_Logs, THE Admin_UI SHALL display every formatted log in the matching Logs_Container.
10. WHEN `data` is empty, THE Admin_UI SHALL display exactly `No acknowledgements yet.` in the matching Logs_Container.
11. IF the logs request or response processing fails, THEN THE Admin_UI SHALL display exactly `Could not load acknowledgement logs.` in the matching Logs_Container.
12. WHEN the Admin_UI injects log values into HTML, THE Admin_UI SHALL escape the `user_id` and `timestamp` values before injection.

### Requirement 9: Participant 24-Hour Critical Countdown

**User Story:** As a participant, I want a live 24-hour countdown on Critical announcements, so that I can see the remaining acknowledgement deadline or escalation state.

#### Acceptance Criteria

1. WHEN the Participant_UI renders a Critical_Announcement card, THE Participant_UI SHALL include a Critical_Timer within that card.
2. WHEN the Participant_UI renders a Critical_Timer, THE Participant_UI SHALL apply the classes `critical-timer text-red-400 text-sm font-bold mt-2` to the Critical_Timer.
3. WHEN the Participant_UI renders a Critical_Timer, THE Participant_UI SHALL set `data-published` to the associated Critical_Announcement `published_at` value.
4. WHEN a Critical_Timer is rendered, THE Participant_UI SHALL update the Critical_Timer immediately.
5. WHEN a Critical_Timer is rendered, THE Participant_UI SHALL start a separate 1000-millisecond update interval for the Critical_Timer.
6. WHEN a Critical_Timer update executes, THE Participant_UI SHALL parse the `data-published` value as a browser `Date`.
7. WHEN a Critical_Timer update calculates the deadline, THE Participant_UI SHALL add exactly `86400000` milliseconds to the parsed publication time.
8. WHEN a Critical_Timer update calculates the remaining duration, THE Participant_UI SHALL subtract `Date.now()` from the deadline.
9. WHILE the remaining duration is greater than or equal to zero, THE Participant_UI SHALL display the remaining whole hours, minutes, and seconds as zero-padded `HH:MM:SS`.
10. WHEN the remaining duration is less than zero, THE Participant_UI SHALL set the Critical_Timer text exactly to `DEADLINE MISSED - ESCALATED`.
11. WHEN the remaining duration is less than zero, THE Participant_UI SHALL clear the associated update interval.
12. IF the parsed publication time or calculated deadline is invalid, THEN THE Participant_UI SHALL complete the Critical_Timer update without throwing an exception.
13. WHEN multiple Critical_Timers are rendered, THE Participant_UI SHALL maintain an independent deadline and interval for each Critical_Timer.

## Implementation Scope

Eventual implementation is restricted to:

- `app/services/announcement_service.py`
- `app/routers/announcements.py`
- `app/main.py`
- `templates/announcements.html`
- `templates/admin_announcements.html`

No application code is implemented during the requirements phase.

## Production Considerations

The five-file implementation provides application-level controls within the existing trust and deployment model. Before treating the controls as a regulated audit system, a future production-hardening effort should address these concerns outside this feature's implementation scope:

- The existing client-supplied participant identity and role are not authenticated identities; production authorization requires a trusted identity source.
- A browser-only reading timer and deadline display can be bypassed by a direct API caller unless server-issued timing evidence is introduced.
- Multiple application workers can start multiple Watchdog tasks and emit duplicate escalation warnings unless production scheduling or distributed coordination is introduced.
- Escalations are warning log records rather than durable notifications; production alert delivery, ownership, deduplication, and acknowledgement require an operational alerting integration.
- SQLite audit retention, backup, write contention, access controls, and tamper evidence require deployment-specific policies before compliance certification.
- Application operators should monitor Watchdog task health, database failures, and clock synchronization.