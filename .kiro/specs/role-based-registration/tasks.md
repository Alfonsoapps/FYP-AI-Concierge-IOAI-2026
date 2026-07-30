# Implementation Plan: Role-Based Registration

## Overview

Add the two page routes, build the browser-mocked registration form and registry, extend the existing onboarding/login role flow with participant-only password validation, and append the registered-participants table to the active Jinja Admin Dashboard. Implementation uses Python, HTML, CSS, and Vanilla JavaScript and is restricted to the four approved production files.

## Tasks

- [x] 1. Add registration and login route integration
  - [x] 1.1 Add the two additive FastAPI page routes
    - Add `GET /register` in `app/main.py` using the existing template path helper and `FileResponse` conventions.
    - Add `GET /login` that serves the same `templates/onboarding.html` interface as the existing `/onboarding` route.
    - Preserve `/onboarding`, every existing page/API route, router registration, startup handler, and import.
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 6.4_

  - [x] 1.2 Create the focused registration page and mock submission flow
    - Create `templates/register.html` with exactly Name, masked Password, and Role form controls; make only Student Participant and Team Leader selectable role values and include no email UI or data.
    - Maintain browser-local `{name, password, role}` state, validate all three values, and create the exact transient `{ name, password, role }` mock payload without making an account-creation request.
    - Implement local-storage registry append under `ioai_registered_participants`, preserving a valid existing array, recovering from absent/unreadable data, and storing only `{name, role}`.
    - Style `Register` as the primary action and `Skip to Login` as secondary navigation to `/login`, matching the existing onboarding visual language.
    - _Requirements: 1.1, 1.5, 1.7, 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 6.5_

  - [ ]* 1.3 Write route and registration template tests
    - Verify `/register`, `/login`, and `/onboarding` resolve correctly and pre-existing routes remain registered.
    - Verify the registration template's exact controls, approved role options, password masking, required-field behavior, exact payload keys, no email content, no account API call, registry fallback/append behavior, and password exclusion.
    - _Requirements: 1.2, 1.3, 1.4, 1.6, 1.8, 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 2.10, 2.11, 2.12, 2.13, 3.1, 3.2, 3.3, 3.4, 3.5_
- [x] 2. Extend participant-role login password behavior
  - [x] 2.1 Add and wire the participant-only password control
    - Add a separate `Password` group to `templates/onboarding.html` using the existing form-group input and error styles.
    - Show and require the masked participant password only for Student Participant and Team Leader; hide, de-require, and clear validation errors whenever the control is hidden.
    - Gate participant-role submission on a non-empty password without persisting or adding the password to the existing `/api/team/register` request.
    - Preserve every existing role option, field, local-storage write, country/language validation, team registration request, redirect, and layout style.
    - Preserve the separate Organiser Admin Password visibility, exact comparison, error, and `/admin` redirect behavior.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 6.1, 6.2_

  - [ ]* 2.2 Write conditional login interaction and regression tests
    - Exercise Student Participant and Team Leader selection, blank and populated participant passwords, switching to each Other_Role, masked input behavior, and stale-error cleanup.
    - Verify Observer behavior and Organiser Admin Password authentication remain unchanged, including current request payloads, local-storage keys, and redirects.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 6.1, 6.2_

- [x] 3. Append registered participants to the Admin Dashboard
  - [x] 3.1 Add the visually matching participant table and registry rendering
    - Append a `Registered Participants` section after all existing content in `templates/admin_dashboard.html` without replacing or reordering metrics, quick actions, FAQ, unanswered, or engagement content.
    - Add a responsive, dark, bordered table with exactly Name and Role columns using existing dashboard typography, spacing, colors, and surface styles.
    - Read `ioai_registered_participants`, safely recover from missing/malformed/non-array data, filter to exact Student Participant and Team Leader roles, and render one row per eligible record.
    - Build untrusted name and role cells with DOM `textContent`; render a two-column empty-state row when no eligible record exists.
    - Keep participant loading independent from the existing `loadDashboard()` analytics requests and interactions.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 6.3, 6.6_

  - [ ]* 3.2 Write Admin Dashboard participant-section tests
    - Verify append position, exact heading and columns, eligible-role filtering, row mapping, responsive/matching classes, and preservation of every existing dashboard section and request.
    - Cover absent, malformed, non-array, empty, mixed-role, and markup-bearing registry data; verify the empty state spans both columns and values render as text.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 6.3, 6.6_
- [~] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Wire and validate the complete mocked registration flow
  - [~] 5.1 Complete cross-page integration and preservation checks
    - Verify a valid `/register` submission creates only the exact transient payload, appends only `{name, role}` to the shared browser registry, and becomes visible in the Admin Dashboard table for either approved role.
    - Verify `Skip to Login` reaches `/login`, participant roles require the new password, and Observer/Organiser authentication behavior remains unchanged.
    - Inspect the implementation diff and fail validation if a production file outside the four approved files changes, a dependency is added, an email field appears, an existing route/role/field/dashboard element is removed, or password data enters the registry.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 1.7, 1.8, 2.3, 2.5, 2.6, 2.7, 2.10, 3.1, 3.2, 3.3, 3.4, 4.3, 4.7, 4.8, 4.9, 5.1, 5.2, 5.5, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 5.2 Run focused automated regression tests
    - Run route, template, login interaction, registry, and dashboard tests plus the existing pytest suite in single-run mode.
    - Verify both `/admin` and `/admin/dashboard` retain the existing dashboard and append identical participant behavior when the admin router is available.
    - _Requirements: 1.6, 1.7, 3.4, 3.5, 4.7, 4.8, 4.9, 5.2, 5.8, 5.9, 6.1, 6.2, 6.3, 6.6_

- [~] 6. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test tasks and may be skipped for a faster MVP; implementation tasks are mandatory.
- The design intentionally has no Correctness Properties section because property-based testing does not suit route/template wiring and mocked browser-side effects.
- No task implements production account persistence, server-side password authentication, email collection, or changes outside the four-file scope.
- Each implementation task references granular acceptance criteria, and the final integration task verifies both the requested feature and preservation boundaries.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["1.3", "2.2", "3.1"] },
    { "id": 3, "tasks": ["3.2", "5.1"] },
    { "id": 4, "tasks": ["5.2"] }
  ]
}
```