# Role-Based Registration Technical Design

## Overview

Role-Based Registration extends the active FastAPI/Jinja application in four files. `app/main.py` adds `/register` and `/login` page routes; `templates/register.html` provides a standalone three-field registration form; `templates/onboarding.html` remains the login implementation and gains a conditional participant password control; and `templates/admin_dashboard.html` appends a matching participant table. No backend account model, email field, password persistence, registration API, dependency, or unrelated UI change is introduced.

The browser-side mock registry uses the same-origin local-storage key `ioai_registered_participants`. Registration creates the required transient `{ name, password, role }` payload, projects only `{ name, role }` into the registry, and performs no network request. The dashboard parses and filters the registry before rendering. This gives `/register` and the dashboard a shared mock data source while keeping credentials out of registry records.

### Design Goals

- Expose `/register` and `/login` without removing or changing `/onboarding`.
- Keep registration limited to Name, masked Password, and the two approved roles.
- Add participant-password validation without changing Observer or Organiser behavior.
- Append a safe, responsive participants table without replacing dashboard content.
- Keep every production edit inside the four approved files.

### Non-Goals

The feature does not implement durable users, password verification, password hashing, sessions, authorization, email identity, a registration API, cross-browser synchronization, or production account management. The existing `/api/team/register` call in the Login_Page remains unchanged and separate from the new mocked registration flow.

### Repository Research Findings

- `app/main.py` currently serves the role-based interface only at `/onboarding`; adding `/login` as a second route to the same `onboarding.html` template preserves the original route while satisfying login navigation.
- `templates/onboarding.html` currently supports Student Participant, Team Leader, Observer, and Organiser. Organiser uses a distinct `Admin Password` field and exact local comparison; the new `Password` field must therefore be a separate participant-only control.
- The login submission writes participant identity to local storage, posts `{name, country, role}` to `/api/team/register`, redirects Organiser to `/admin`, and redirects all other roles to `/`. Those branches remain unchanged after participant-password validation succeeds.
- The existing team-safety registry requires country and does not retain role in member records, so it cannot provide the requested `{name, role}` mock dashboard data without unrelated backend changes.
- `templates/admin_dashboard.html` is the active Jinja dashboard for both `/admin` and `/admin/dashboard`. Its existing content ends with engagement analytics, making the end of `.admin-main` the additive insertion point.
- The dashboard already uses dark translucent cards, violet borders, section titles, responsive grids, and safe text escaping. The participant section will reuse those visual tokens and use DOM `textContent` rather than HTML interpolation.

No external research was required because the repository establishes the stack, route ownership, current authentication branches, and compatible integration points.
## Architecture

```mermaid
flowchart LR
    Browser -->|GET /register| FastAPI
    Browser -->|GET /login or /onboarding| FastAPI
    FastAPI --> RegisterTemplate[register.html]
    FastAPI --> LoginTemplate[onboarding.html]
    RegisterTemplate -->|transient exact payload| MockSubmit[Mock submission handler]
    MockSubmit -->|project name and role only| Registry[(localStorage registry)]
    Registry -->|read, parse, filter allowed roles| DashboardTemplate[admin_dashboard.html]
    DashboardTemplate --> ParticipantsTable[Registered Participants table]
    LoginTemplate -->|existing payload unchanged| TeamAPI[/api/team/register]
```

The design is intentionally client-local. FastAPI only serves pages; registration data remains a browser mock. The local-storage key is duplicated as a constant in the registration and dashboard templates to avoid adding a fifth production file.

### Route Integration

`app/main.py` adds two GET handlers near the existing page routes:

- `GET /register` returns `FileResponse(_tpl("register.html"))`.
- `GET /login` returns `FileResponse(_tpl("onboarding.html"))`.

The existing `GET /onboarding`, `/admin`, `/admin/dashboard`, router registrations, startup handlers, and all API routes remain untouched.

## Components and Interfaces

### Registration Page

`templates/register.html` is a self-contained page visually aligned with `onboarding.html`. The form contains exactly these controls:

| Label | Element | State key | Constraints |
|---|---|---|---|
| Name | `input[type="text"]` | `name` | Required, trimmed for validation and record creation |
| Password | `input[type="password"]` | `password` | Required, masked, never persisted |
| Role | `select` | `role` | Required; selectable values only `Student Participant`, `Team Leader` |

A local `registrationState` object is updated on control input/change events. Submit validation reads this state and creates the exact object `{ name, password, role }`. `mockSubmit(payload)` performs no fetch; it appends `{ name: payload.name, role: payload.role }` to `ioai_registered_participants`. `Skip to Login` is a secondary anchor to `/login`, while `Register` is the primary submit button.

### Login Page Extension

`templates/onboarding.html` receives a new form group with label `Password`, an `input[type="password"]`, and participant-specific error text. A single visibility function derives state from `field-role`:

- Student Participant or Team Leader: show the participant group and set the input's `required` property.
- Every other role: hide the participant group, clear `required`, and remove its validation error.
- Organiser: independently retain the existing Admin Password visibility and exact comparison.

Submission adds one validation guard for participant roles. The participant password is not added to local storage and is not added to the existing `/api/team/register` payload. All existing name, role, country, language, organiser-password, registration-request, and redirect logic remains in its current order.

### Admin Dashboard Extension

`templates/admin_dashboard.html` appends the new section after Engagement and before the closing `.admin-main` element. The section uses a `.section-title`, a bordered dark table container, and responsive horizontal overflow consistent with existing surfaces. The table has exactly `Name` and `Role` headers.

`loadRegisteredParticipants()` reads the registry, accepts only an array, filters to the two exact Participant_Role values, and constructs rows with `document.createElement` and `textContent`. The function never inserts registry strings through `innerHTML`. Missing, malformed, non-array, or empty eligible data produces one two-column empty-state row. The function runs independently of `loadDashboard()` so participant rendering cannot prevent existing analytics requests.
## Data Models

### Registration State and Mock Payload

```javascript
const registrationState = {
  name: "",
  password: "",
  role: "",
};

// Created only after successful validation; exact key set is required.
const payload = {
  name: registrationState.name.trim(),
  password: registrationState.password,
  role: registrationState.role,
};
```

`password` exists only in runtime form state and the transient payload. It is not written to local storage, rendered by the dashboard, or sent to an API.

### Participant Record and Registry

```javascript
// Stored record
{ name: string, role: "Student Participant" | "Team Leader" }

// Stored under localStorage key "ioai_registered_participants"
ParticipantRecord[]
```

On registration, the writer parses the existing value. A missing value, JSON parse failure, or non-array value falls back to `[]`; valid existing records are preserved. The writer appends one projected record and serializes the array. The dashboard treats all registry content as untrusted and applies its own role filter and text-only rendering.

## Error Handling

- Registration validation prevents mock submission for blank trimmed Name, blank Password, or absent approved Role and marks the associated field using the existing onboarding error style.
- Registry read or parse failure falls back to an empty array before registration append, allowing a valid registration to proceed.
- Registry write failure is handled in the mock submission path without exposing password content; the page remains usable and does not issue an account API request.
- Login hides and de-requires the participant password for every Other_Role and clears stale participant-password validation state whenever hidden.
- Existing Admin Password failures continue to use the existing organiser error branch.
- Dashboard parse failure, non-array storage, and no eligible records converge on the same two-column empty state.
- Malformed registry entries and roles other than the two exact participant roles are omitted from rendering.
- Participant names and roles are rendered through `textContent` to prevent stored markup execution.

## Testing Strategy

Property-based testing is not appropriate for this feature. The change consists of static route registration, UI rendering, role-dependent interaction, local-storage side effects, and preservation checks; representative unit/integration/browser examples provide more value than generated inputs. No `Correctness Properties` section is included.

### Route and Template Tests

Use the existing Python/pytest test style with FastAPI test requests or route-table inspection to verify `/register`, `/login`, and `/onboarding` resolve to the intended templates, and that all pre-existing routes remain registered. Static template assertions verify the registration form has exactly Name, Password, and Role controls, no email control, only the two selectable roles, and the two required actions.

### Browser Interaction Tests

Use an isolated DOM-capable harness if available; otherwise use focused JavaScript extraction/static contract checks without adding a production dependency. Cover:

- local Registration_State updates and the exact payload key set;
- required-field rejection and password masking;
- no registration fetch and password exclusion from stored records;
- preservation and append behavior for valid registry arrays;
- fallback behavior for absent, malformed, and non-array registry values;
- Student Participant and Team Leader participant-password visibility and requirement;
- Observer and Organiser participant-password hiding and error clearing;
- unchanged Organiser Admin Password and redirect behavior;
- dashboard filtering, exact columns, empty state, text-only rendering, and append position.

### Regression and Scope Checks

Run the existing pytest suite and targeted new tests. Inspect the diff to ensure production changes are limited to the four approved files, no dependency manifests change, and existing login fields/options, admin metrics, quick actions, FAQ, unanswered, engagement, scripts, routes, and authentication branches remain present. Validate the planning documents with Kiro spec diagnostics before implementation begins.