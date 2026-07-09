# Requirements Document

## Introduction

The Announcements module adds broadcast messaging to the existing IOAI 2027 Participant Platform (FYP-AI-Concierge-IOAI-2026), a FastAPI application. Organisers create and publish announcements targeted at specific audiences; users see only the announcements relevant to their role, receive notification indicators, view announcement history, and acknowledge critical announcements. Organisers view delivery and acknowledgement statistics. The existing AI concierge can retrieve the latest announcements to answer participant questions.

This module is developed by Member 2 of a shared repository and is scoped strictly to announcements. It MUST integrate into the existing structure (FastAPI routers under `app/routers/`, services under `app/services/`, Pydantic schemas in `app/models/schemas.py`, Jinja2 templates under `templates/`, static assets under `static/`, and the shared bottom navigation partial `templates/partials/navbar.html`) without removing or breaking existing features, and MUST match the current dark-theme, purple-gradient, mobile-first visual style.

Because the platform currently has no server-side database and no server-side authentication, user identity and role are held client-side in `localStorage` (`participant_name`, `participant_role`, `participant_country`, `participant_language`). The module introduces lightweight server-side persistence for announcements and per-user tracking, and normalizes client-supplied roles to the module's audience categories.

## Glossary

- **Announcements_Module**: The complete feature set (backend routers, service, persistence, and frontend pages) that manages announcements for the platform.
- **Announcement_Service**: The backend service component that performs announcement persistence, retrieval, audience resolution, and tracking.
- **Announcement**: A stored message with the fields: identifier, title, message body, category, priority, target audience, acknowledgement-required flag, status (draft or published), created timestamp, and published timestamp.
- **Announcement_Recipient_Record**: A stored per-user, per-announcement record capturing read state (read timestamp) and acknowledgement state (acknowledged timestamp).
- **Organiser**: A user whose normalized role is "Organisers"; the only audience permitted to create, edit, delete, publish, and view statistics for announcements.
- **User**: Any person using the platform, identified by the client-side `participant_name` and `participant_role` values.
- **Audience_Category**: One of the fixed target values: "Students", "Team Leaders", "Observers", "Volunteers", "Organisers", "All Users".
- **Role_Normalizer**: The component that maps a client-supplied `participant_role` value to an Audience_Category.
- **Priority**: The urgency level of an Announcement, one of "Normal" or "Critical".
- **Category**: A label classifying an Announcement's topic (for example "General", "Schedule", "Logistics", "Emergency").
- **Critical_Announcement**: An Announcement whose acknowledgement-required flag is true.
- **Notification_Indicator**: The notification bell UI element that shows the count of unread announcements targeted to the current User.
- **Announcement_Page**: The user-facing page at `/announcements` listing announcements targeted to the current User.
- **Announcement_History**: The chronological list of all announcements previously targeted to and delivered to the current User, including already-read ones.
- **Admin_Console**: The organiser-facing management page at `/admin/announcements` for creating, editing, deleting, publishing, and viewing statistics.
- **AI_Concierge**: The existing chat feature (POST `/chat` router and `app/services/nvidia_service.py`) that answers participant questions.
- **Latest_Announcements_Endpoint**: The API endpoint `/api/announcements/latest` that returns recent published announcements for programmatic access.
- **Sample_Data**: A predefined set of announcements and recipient records used for testing and demonstration.

## Requirements

### Requirement 1: Create Announcements

**User Story:** As an Organiser, I want to create announcements with structured fields, so that I can communicate targeted information to the right participants.

#### Acceptance Criteria

1. WHEN an Organiser submits an announcement with a title of 1 to 200 characters, a message of 1 to 5000 characters, a non-empty Category, a Priority equal to "Normal" or "Critical", exactly one Audience_Category value from {Students, Team Leaders, Observers, Volunteers, Organisers, All Users}, and a boolean acknowledgement-required flag, THE Announcement_Service SHALL store a new Announcement with status "draft" and a unique generated identifier.
2. IF a create request omits the title or message, or provides a title or message that is empty or contains only whitespace, THEN THE Announcement_Service SHALL reject the request, return a validation error identifying the missing or empty field, and SHALL NOT store any Announcement.
3. IF a create request provides a title longer than 200 characters or a message longer than 5000 characters, THEN THE Announcement_Service SHALL reject the request, return a validation error identifying the field that exceeds its maximum length, and SHALL NOT store any Announcement.
4. IF a create request omits the Priority or specifies a Priority value that is not "Normal" or "Critical", THEN THE Announcement_Service SHALL reject the request, return a validation error indicating an invalid Priority, and SHALL NOT store any Announcement.
5. IF a create request omits the target audience or specifies a target audience that is not one of the six Audience_Category values, THEN THE Announcement_Service SHALL reject the request, return a validation error indicating an invalid audience, and SHALL NOT store any Announcement.
6. IF a create request omits the acknowledgement-required flag or provides a value that is not a boolean, THEN THE Announcement_Service SHALL reject the request, return a validation error indicating an invalid acknowledgement-required flag, and SHALL NOT store any Announcement.
7. WHEN an Announcement is created, THE Announcement_Service SHALL record the created timestamp as a UTC value.

### Requirement 2: Read, Update, and Delete Announcements

**User Story:** As an Organiser, I want to read, edit, and delete announcements, so that I can correct or remove information after it is entered.

#### Acceptance Criteria

1. WHEN an Organiser requests the list of announcements in the Admin_Console, THE Announcement_Service SHALL return all stored announcements, including both draft-status and published-status announcements.
2. WHEN an Organiser requests a single announcement by identifier that matches a stored Announcement, THE Announcement_Service SHALL return the Announcement matching that identifier.
3. IF an announcement identifier submitted in a read, edit, or delete request does not match any stored Announcement, THEN THE Announcement_Service SHALL return a not-found error and SHALL make no change to any stored Announcement.
4. WHEN an Organiser submits an edit to an existing Announcement in which all required fields are present, each field value is within its defined length limit, and the status value is either draft or published, THE Announcement_Service SHALL update the stored Announcement with the new field values.
5. IF an Organiser submits an edit to an existing Announcement in which a required field is missing, a field value exceeds its defined length limit, or the status value is neither draft nor published, THEN THE Announcement_Service SHALL reject the edit, SHALL return a validation error indicating which field is invalid, and SHALL retain the previously stored field values unchanged.
6. WHEN an Organiser deletes an existing Announcement, THE Announcement_Service SHALL remove the Announcement together with all of its associated Announcement_Recipient_Records as a single atomic operation, such that either all records are removed or, on failure, none are removed.

### Requirement 3: Publish Announcements

**User Story:** As an Organiser, I want to publish announcements, so that targeted users can see them only when they are ready.

#### Acceptance Criteria

1. WHEN an Organiser publishes a draft Announcement, THE Announcement_Service SHALL set the Announcement status to "published".
2. WHILE an Announcement status is "draft", THE Announcement_Service SHALL exclude the Announcement from results returned to non-organiser Users.
3. WHEN an Announcement status changes to "published", THE Announcement_Service SHALL make the Announcement available to every User whose Audience_Category matches the Announcement target audience.
4. WHEN an Organiser publishes a draft Announcement, THE Announcement_Service SHALL record the published timestamp as the server date and time at the moment the status is set to "published".
5. IF a non-organiser User attempts to publish an Announcement, THEN THE Announcement_Service SHALL reject the request, leave the Announcement status and published timestamp unchanged, and return an error indicating the User is not authorised to publish.
6. IF an Organiser attempts to publish an Announcement whose status is not "draft", THEN THE Announcement_Service SHALL reject the request, leave the Announcement status and published timestamp unchanged, and return an error indicating the Announcement is not in a draft state.

### Requirement 4: Audience Targeting and Role Normalization

**User Story:** As a User, I want to see only announcements meant for my role, so that the information I receive is relevant to me.

#### Acceptance Criteria

1. THE Role_Normalizer SHALL map the client-supplied role "Student Participant" to the Audience_Category "Students".
2. THE Role_Normalizer SHALL map the client-supplied role "Team Leader" to the Audience_Category "Team Leaders".
3. THE Role_Normalizer SHALL map the client-supplied role "Observer" to the Audience_Category "Observers".
4. WHERE a client-supplied role matches a defined Audience_Category name directly, THE Role_Normalizer SHALL map the role to that Audience_Category.
5. IF a client-supplied role is absent, empty, contains only whitespace, or does not match any mapping defined in criteria 1 through 4, THEN THE Role_Normalizer SHALL map the role to the Audience_Category "All Users".
6. WHEN a User requests announcements with a resolved Audience_Category, THE Announcement_Service SHALL return published announcements whose target audience equals that Audience_Category or equals "All Users".
7. THE Announcement_Service SHALL exclude from a User's results every published Announcement whose target audience neither equals the User's Audience_Category nor equals "All Users".
8. WHERE a client-supplied role is compared against a known role name or Audience_Category name, THE Role_Normalizer SHALL perform the comparison after removing leading and trailing whitespace and treating uppercase and lowercase letters as equivalent.
9. IF no published announcement's target audience equals the User's Audience_Category or equals "All Users", THEN THE Announcement_Service SHALL return an empty result set without raising an error.

### Requirement 5: View Announcements and History

**User Story:** As a User, I want to view current announcements and my announcement history, so that I can stay informed and revisit past messages.

#### Acceptance Criteria

1. WHEN a User opens the Announcement_Page, THE Announcements_Module SHALL display up to 100 published announcements currently targeted to the User, ordered by published timestamp with the most recent first, and where more than 100 exist SHALL display the 100 most recent.
2. WHEN a User opens the Announcement_History, THE Announcements_Module SHALL display all published announcements previously targeted to the User, including announcements the User has already read, ordered by published timestamp with the most recent first.
3. WHERE a User has no currently targeted published announcements, THE Announcement_Page SHALL display an empty-state message indicating that no announcements are available.
4. WHERE a User has no previously targeted published announcements, THE Announcement_History SHALL display an empty-state message indicating that no past announcements are available.
5. WHEN the Announcement_Page or Announcement_History displays an Announcement, THE Announcements_Module SHALL display the title, message, Category, Priority, and published timestamp for that Announcement.
6. IF retrieval of targeted published announcements fails when a User opens the Announcement_Page or Announcement_History, THEN THE Announcements_Module SHALL display an error indication that announcements could not be loaded and SHALL retain any previously displayed announcement list unchanged.

### Requirement 6: Read Tracking

**User Story:** As an Organiser, I want the system to record when users read announcements, so that I can measure reach.

#### Acceptance Criteria

1. WHEN a User views an Announcement targeted to that User AND no Announcement_Recipient_Record with a read timestamp exists for that User and that Announcement, THE Announcement_Service SHALL create an Announcement_Recipient_Record with a read timestamp recorded in UTC for that User and that Announcement.
2. IF an Announcement_Recipient_Record with a read timestamp already exists for the User and the Announcement, THEN THE Announcement_Service SHALL retain the original read timestamp AND SHALL NOT create a duplicate Announcement_Recipient_Record.
3. THE Announcement_Service SHALL identify a User for tracking purposes using the client-supplied `participant_name` value.
4. IF the `participant_name` value is missing, empty, contains only whitespace, or exceeds 100 characters, THEN THE Announcement_Service SHALL reject the read-tracking request, SHALL NOT create an Announcement_Recipient_Record, AND SHALL return an error indicating that a valid `participant_name` is required.
5. IF a User views an Announcement that is not targeted to that User, THEN THE Announcement_Service SHALL NOT create an Announcement_Recipient_Record for that User and that Announcement.

### Requirement 7: Critical Announcement Acknowledgement

**User Story:** As an Organiser, I want users to acknowledge critical announcements, so that I can confirm important information was received.

#### Acceptance Criteria

1. WHERE an Announcement is a Critical_Announcement, THE Announcement_Page SHALL display an acknowledge button for that Announcement.
2. WHERE an Announcement is not a Critical_Announcement, THE Announcement_Page SHALL omit the acknowledge button for that Announcement.
3. WHEN a User selects the acknowledge button for a Critical_Announcement that has no acknowledged timestamp recorded for that User, THE Announcement_Service SHALL record an acknowledged timestamp containing the date and time of the acknowledgement in the Announcement_Recipient_Record for that User and that Announcement within 3 seconds.
4. WHILE a Critical_Announcement has an acknowledged timestamp recorded for the current User, THE Announcement_Page SHALL display an acknowledged state showing the recorded acknowledged date and time instead of the acknowledge button for that Announcement.
5. IF an acknowledgement is submitted for an Announcement that is not a Critical_Announcement, THEN THE Announcement_Service SHALL reject the submission, record no acknowledged timestamp, and return a validation error indicating that acknowledgement is not applicable to the Announcement.
6. IF a User submits an acknowledgement for a Critical_Announcement that already has an acknowledged timestamp recorded for that User, THEN THE Announcement_Service SHALL retain the existing acknowledged timestamp unchanged and return a response indicating the Announcement was already acknowledged.
7. IF recording an acknowledged timestamp fails, THEN THE Announcement_Service SHALL retain the prior acknowledgement state without recording a timestamp and return an error indicating the acknowledgement was not recorded.

### Requirement 8: Notification Indicator

**User Story:** As a User, I want a notification bell that shows unread announcements, so that I know when new information is available.

#### Acceptance Criteria

1. WHEN a User loads a page that includes the Notification_Indicator, THE Announcements_Module SHALL display, within 3 seconds of page load completion, the count of published announcements targeted to the User that have no read timestamp for that User.
2. WHERE the count of unread targeted announcements is zero, THE Notification_Indicator SHALL display no unread count badge.
3. WHERE the count of unread targeted announcements exceeds 99, THE Notification_Indicator SHALL display the badge value as "99+".
4. WHEN a User selects the Notification_Indicator, THE Announcements_Module SHALL navigate the User to the Announcement_Page.
5. THE Notification_Indicator SHALL retrieve its count from the `/api/notifications` endpoint using the User's resolved Audience_Category.
6. IF the retrieval of the count from the `/api/notifications` endpoint fails or does not return a response within 5 seconds, THEN THE Notification_Indicator SHALL display no unread count badge and SHALL retain the last successfully retrieved count until the next successful retrieval.

### Requirement 9: Organiser Statistics

**User Story:** As an Organiser, I want statistics for each announcement, so that I can see who has read and acknowledged it and who has not.

#### Acceptance Criteria

1. WHEN an Organiser requests statistics for an existing Announcement, THE Announcement_Service SHALL return the count of targeted users, the read count, and the acknowledged count, each as a non-negative integer, within 3 seconds.
2. WHEN an Organiser requests statistics for a Critical_Announcement, THE Announcement_Service SHALL return the list of targeted users who have no acknowledged timestamp for that Announcement, and SHALL return an empty list when every targeted user has an acknowledged timestamp.
3. THE Announcement_Service SHALL compute the read count as the number of Announcement_Recipient_Records for the Announcement that have a read timestamp.
4. THE Announcement_Service SHALL compute the acknowledged count as the number of Announcement_Recipient_Records for the Announcement that have an acknowledged timestamp.
5. THE Announcement_Service SHALL compute the count of targeted users as the total number of Announcement_Recipient_Records for the Announcement.
6. IF an Organiser requests statistics for an Announcement that does not exist, THEN THE Announcement_Service SHALL reject the request, return no statistics, and return an error indicating the Announcement was not found.
7. IF a requester who is not an Organiser authorized for the Announcement requests its statistics, THEN THE Announcement_Service SHALL reject the request, return no statistics, and return an error indicating the requester is not authorized.

### Requirement 10: AI Concierge Access to Announcements

**User Story:** As a User, I want to ask the AI concierge about announcements, so that I can find out what I missed or whether there are urgent updates.

#### Acceptance Criteria

1. WHEN a client requests the Latest_Announcements_Endpoint, THE Announcement_Service SHALL return a structured response containing up to 20 published announcements ordered by published timestamp in descending order (most recent first).
2. WHERE a request to the Latest_Announcements_Endpoint includes an Audience_Category parameter, THE Announcement_Service SHALL return only published announcements whose target audience equals that Audience_Category or equals "All Users".
3. IF a request to the Latest_Announcements_Endpoint includes an Audience_Category parameter that does not match any defined audience category, THEN THE Announcement_Service SHALL return a response indicating an invalid audience category and SHALL NOT return any announcements.
4. WHEN the Latest_Announcements_Endpoint returns published announcements, THE Latest_Announcements_Endpoint SHALL include for each returned Announcement the title, message, Category, Priority, and published timestamp.
5. IF no published announcements match the request to the Latest_Announcements_Endpoint, THEN THE Announcement_Service SHALL return a structured response containing an empty announcement collection.
6. WHEN the AI_Concierge answers a question about recent or urgent announcements, THE AI_Concierge SHALL use data obtained from the Latest_Announcements_Endpoint.
7. IF the Latest_Announcements_Endpoint is unavailable or returns an error when the AI_Concierge requests announcement data, THEN THE AI_Concierge SHALL respond with a message indicating that announcement information cannot be retrieved at that time.

### Requirement 11: Persistence

**User Story:** As Member 2, I want lightweight server-side persistence, so that announcements and tracking survive across requests without requiring the shared team to adopt a full database.

#### Acceptance Criteria

1. THE Announcement_Service SHALL persist announcements and Announcement_Recipient_Records in file-based server-side storage that is local to the Announcements_Module and retained on non-volatile disk.
2. WHEN an Announcement or an Announcement_Recipient_Record is created, updated, or deleted, THE Announcement_Service SHALL write the change to the persistent storage before returning a success response to the caller.
3. IF a write to the persistent storage fails, THEN THE Announcement_Service SHALL return an error indicating the persistence failure and retain the previously stored announcements and Announcement_Recipient_Records unchanged.
4. WHEN the application restarts, THE Announcement_Service SHALL load and make retrievable all announcements and Announcement_Recipient_Records that were successfully written before the restart, with every stored field value unchanged.
5. THE Announcements_Module SHALL provide Sample_Data containing at least 3 announcements spanning at least 2 distinct Audience_Categories, at least 1 Critical_Announcement, at least 1 Announcement_Recipient_Record that has a read timestamp, and at least 1 Announcement_Recipient_Record that has no read timestamp.
6. WHEN Sample_Data loading is triggered and the persistent storage contains zero announcements, THE Announcement_Service SHALL store the Sample_Data as retrievable announcements and Announcement_Recipient_Records.
7. IF Sample_Data loading is triggered while the persistent storage already contains one or more announcements, THEN THE Announcement_Service SHALL leave the existing stored announcements and Announcement_Recipient_Records unchanged and SHALL NOT load the Sample_Data.

### Requirement 12: Integration with Existing Application

**User Story:** As Member 2, I want the module to plug into the existing app cleanly, so that existing features keep working and navigation stays consistent.

#### Acceptance Criteria

1. WHEN the FastAPI application starts, THE Announcements_Module SHALL register its routers with the existing FastAPI application through `app.include_router`, and the existing chat, TTS, and RAG endpoints SHALL remain reachable at their original paths and return the same HTTP responses as before the integration.
2. IF a router registered by the Announcements_Module declares a path that collides with an existing chat, TTS, or RAG endpoint path, THEN THE Announcements_Module SHALL fail application startup and surface a startup error indicating the conflicting path, without partially registering announcement routes.
3. WHEN a user activates the announcements navigation control in the shared bottom navigation partial `templates/partials/navbar.html` or the included Notification_Indicator, THE Announcements_Module SHALL navigate the user to the Announcement_Page.
4. THE Announcement_Page, Announcement_History, and Admin_Console SHALL apply the existing visual style: background color `#0c0c1d`, text color `#e8e8f0`, purple gradient accents from `#7c3aed` to `#a78bfa`, the Inter or Segoe UI font family, and a mobile-first maximum content width of 600 pixels.
5. WHILE rendered on viewport widths from 360 pixels to 600 pixels inclusive, THE Announcement_Page, Announcement_History, and Admin_Console SHALL display all interactive controls and text content without horizontal scrolling, without clipping content beyond the viewport, and without overlapping elements.

### Requirement 13: Organiser Access Restriction

**User Story:** As an Organiser, I want management actions restricted to organisers, so that participants cannot create or alter announcements.

#### Acceptance Criteria

1. WHERE the requesting User's resolved Audience_Category is "Organisers", WHEN the Admin_Console is loaded, THE Admin_Console SHALL enable and display the create, edit, delete, publish, and view-statistics actions.
2. WHERE the requesting User's resolved Audience_Category is not "Organisers", WHEN the Admin_Console is loaded, THE Admin_Console SHALL hide all five management actions (create, edit, delete, publish, view-statistics) and display a visible not-authorized message indicating that management is restricted to Organisers.
3. IF the requesting User's Audience_Category cannot be resolved because the role value in `localStorage` is absent, empty, or not one of the defined Audience_Category values, THEN THE Admin_Console SHALL treat the User as a non-Organiser, hide all five management actions, and display the not-authorized message.
4. IF a User whose resolved Audience_Category is not "Organisers" attempts to invoke any management action (create, edit, delete, publish, or view-statistics), THEN THE Admin_Console SHALL reject the action, make no change to any announcement, and display the not-authorized message.
5. THE Announcements_Module SHALL document that role information originates from client-side `localStorage` and therefore does not constitute enforced server-side authorization.
