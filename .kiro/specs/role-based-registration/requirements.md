# Requirements Document

## Introduction

The Role-Based Registration feature adds a focused registration route for Student Participants and Team Leaders, conditionally adds participant-password input to the existing role-based login flow, and appends registered-participant visibility to the existing Admin Dashboard. The feature is additive to the active FastAPI, Jinja2, HTML, CSS, and Vanilla JavaScript application. The feature uses mocked browser-side submission and registry behavior; persistent account creation and server-side password authentication are outside scope.

## Glossary

- **Role_Based_Registration**: The complete feature specified by this document.
- **Application**: The active FastAPI application rooted at `app/main.py`.
- **Registration_Page**: The page served at `/register` by a new registration template.
- **Login_Page**: The existing role-based login interface in `templates/onboarding.html`, served at `/login` while remaining available at `/onboarding`.
- **Admin_Dashboard**: The existing dashboard in `templates/admin_dashboard.html`, served at `/admin` and `/admin/dashboard`.
- **Participant_Role**: Either the exact value `Student Participant` or the exact value `Team Leader`.
- **Other_Role**: Any Login_Page role other than a Participant_Role, including `Observer` and `Organiser`.
- **Participant_Password_Input**: The new Login_Page password control labeled `Password` for Participant_Roles.
- **Admin_Password_Input**: The pre-existing organiser password control and validation behavior.
- **Registration_State**: Browser-local form state containing `name`, `password`, and `role`.
- **Mock_Submission_Payload**: A JavaScript object with exactly the keys `name`, `password`, and `role`.
- **Participant_Record**: A browser-local mock registry entry containing exactly `name` and `role`.
- **Participant_Registry**: Same-origin browser local storage used as the mock/global registry shared by Registration_Page and Admin_Dashboard.
- **Registered_Participants_Section**: The additive Admin_Dashboard section containing the registered participants table.
- **Unrelated_Behavior**: Every route, feature, field, style, chart, table, metric, authentication branch, and interaction not explicitly changed by this document.

## Requirements

### Requirement 1: Additive Scope and Route Integration

**User Story:** As a maintainer, I want registration changes constrained to the active application, so that unrelated functionality remains intact.

#### Acceptance Criteria

1. THE Role_Based_Registration SHALL limit eventual application changes to `app/main.py`, `templates/register.html`, `templates/onboarding.html`, and `templates/admin_dashboard.html`.
2. THE Application SHALL serve the Registration_Page at `/register`.
3. THE Application SHALL serve the Login_Page at `/login`.
4. THE Application SHALL continue to serve the Login_Page at `/onboarding`.
5. THE Role_Based_Registration SHALL use the existing FastAPI, Jinja2, HTML, CSS, and Vanilla JavaScript stack.
6. THE Role_Based_Registration SHALL preserve every existing route path and HTTP method.
7. THE Role_Based_Registration SHALL preserve Unrelated_Behavior.
8. THE Role_Based_Registration SHALL add zero email fields, email labels, email validation rules, and email values to the Registration_Page.
### Requirement 2: Registration Form

**User Story:** As a participant, I want a concise role-based registration form, so that I can create a mocked participant registration without providing an email address.

#### Acceptance Criteria

1. WHEN the Registration_Page renders, THE Registration_Page SHALL display exactly three form controls labeled `Name`, `Password`, and `Role`.
2. WHEN the Registration_Page renders the Password control, THE Registration_Page SHALL use an HTML password input that masks entered characters.
3. WHEN the Registration_Page renders the Role control, THE Registration_Page SHALL display a select containing only `Student Participant` and `Team Leader` as selectable role values.
4. WHILE a user edits a registration control, THE Registration_Page SHALL maintain the corresponding `name`, `password`, or `role` value in Registration_State.
5. WHEN a user submits valid Registration_State, THE Registration_Page SHALL create a Mock_Submission_Payload from Registration_State.
6. WHEN the Registration_Page creates a Mock_Submission_Payload, THE Registration_Page SHALL include exactly `{ name, password, role }` in the Mock_Submission_Payload.
7. WHEN the Registration_Page creates a Mock_Submission_Payload, THE Registration_Page SHALL complete submission through a mocked browser-side handler without calling an account-creation API.
8. WHEN the Registration_Page renders, THE Registration_Page SHALL display a primary action labeled `Register`.
9. WHEN the Registration_Page renders, THE Registration_Page SHALL display a secondary navigation action labeled `Skip to Login`.
10. WHEN a user activates `Skip to Login`, THE Registration_Page SHALL navigate to `/login`.
11. WHEN a user submits a blank Name, THE Registration_Page SHALL keep the user on `/register` and identify Name as required.
12. WHEN a user submits a blank Password, THE Registration_Page SHALL keep the user on `/register` and identify Password as required.
13. WHEN a user submits without a Participant_Role, THE Registration_Page SHALL keep the user on `/register` and identify Role as required.

### Requirement 3: Mock Participant Registry

**User Story:** As an administrator, I want mocked registrations shared with the dashboard, so that I can view the two supported participant roles without introducing account persistence.

#### Acceptance Criteria

1. WHEN a valid Mock_Submission_Payload is submitted, THE Registration_Page SHALL derive a Participant_Record containing exactly the submitted `name` and `role` values.
2. WHEN the Registration_Page derives a Participant_Record, THE Registration_Page SHALL append the Participant_Record to the Participant_Registry.
3. WHEN the Registration_Page writes a Participant_Record, THE Registration_Page SHALL exclude the submitted password from the Participant_Record.
4. WHEN the Registration_Page writes a Participant_Record, THE Registration_Page SHALL preserve Participant_Records already present in the Participant_Registry.
5. IF the Participant_Registry is absent or unreadable, THEN THE Registration_Page SHALL initialize an empty Participant_Registry before appending the Participant_Record.
6. THE Participant_Registry SHALL represent mock browser-local data rather than a durable server-side account store.
### Requirement 4: Conditional Participant Password on Login

**User Story:** As a Student Participant or Team Leader, I want a required password control during login, so that participant-role login captures the expected credential while other role flows remain unchanged.

#### Acceptance Criteria

1. WHEN the Login_Page role selection equals `Student Participant`, THE Login_Page SHALL display the Participant_Password_Input.
2. WHEN the Login_Page role selection equals `Team Leader`, THE Login_Page SHALL display the Participant_Password_Input.
3. WHILE the Login_Page role selection equals a Participant_Role, THE Login_Page SHALL require a non-empty Participant_Password_Input before continuing the existing login submission.
4. WHEN the Login_Page role selection equals an Other_Role, THE Login_Page SHALL hide the Participant_Password_Input.
5. WHEN the Login_Page hides the Participant_Password_Input, THE Login_Page SHALL clear Participant_Password_Input validation errors.
6. WHEN the Login_Page renders the Participant_Password_Input, THE Login_Page SHALL use an HTML password input that masks entered characters.
7. WHEN an Other_Role is selected, THE Login_Page SHALL preserve the pre-existing fields, validation, local-storage writes, registration request, redirect, and authentication logic for the selected Other_Role.
8. WHEN `Organiser` is selected, THE Login_Page SHALL preserve the Admin_Password_Input, the existing organiser-password comparison, and the existing `/admin` redirect.
9. WHEN `Observer` is selected, THE Login_Page SHALL preserve the existing observer login validation, storage, registration request, and `/` redirect.
10. THE Login_Page SHALL preserve the existing visual design except for styling required to add the Participant_Password_Input consistently with existing form controls.

### Requirement 5: Registered Participants Dashboard Section

**User Story:** As an administrator, I want a registered participants table appended to the dashboard, so that I can see mocked Student Participant and Team Leader registrations.

#### Acceptance Criteria

1. WHEN the Admin_Dashboard renders, THE Admin_Dashboard SHALL append the Registered_Participants_Section after all existing dashboard content.
2. THE Registered_Participants_Section SHALL preserve every existing Admin_Dashboard metric, quick action, analytics section, script, and interaction.
3. WHEN the Registered_Participants_Section renders, THE Registered_Participants_Section SHALL display the exact heading `Registered Participants`.
4. WHEN the Registered_Participants_Section renders, THE Registered_Participants_Section SHALL display a table with exactly the visible columns `Name` and `Role`.
5. WHEN the Admin_Dashboard reads the Participant_Registry, THE Admin_Dashboard SHALL retain only Participant_Records whose role equals `Student Participant` or `Team Leader`.
6. WHEN eligible Participant_Records exist, THE Admin_Dashboard SHALL render one table row per eligible Participant_Record.
7. WHEN a Participant_Record is rendered, THE Admin_Dashboard SHALL display the Participant_Record name in the `Name` column and role in the `Role` column.
8. IF the Participant_Registry is absent, unreadable, or contains zero eligible Participant_Records, THEN THE Admin_Dashboard SHALL display an empty-state row spanning both table columns.
9. WHEN the Admin_Dashboard renders Participant_Record values, THE Admin_Dashboard SHALL insert name and role as text content.
10. THE Registered_Participants_Section SHALL visually match the Admin_Dashboard typography, dark surfaces, borders, spacing, and responsive layout.

### Requirement 6: Preservation Boundaries

**User Story:** As a maintainer, I want explicit regression boundaries, so that this focused feature does not disturb existing work.

#### Acceptance Criteria

1. THE Role_Based_Registration SHALL preserve every existing Login_Page role option.
2. THE Role_Based_Registration SHALL preserve every existing Login_Page field other than the additive Participant_Password_Input.
3. THE Role_Based_Registration SHALL preserve every existing Admin_Dashboard chart, table, list, metric, and data-loading request.
4. THE Role_Based_Registration SHALL preserve all application files outside the four implementation files without modification.
5. THE Role_Based_Registration SHALL add zero production dependencies.
6. THE Role_Based_Registration SHALL preserve the existing `/admin` and `/admin/dashboard` dashboard behavior while appending the Registered_Participants_Section.

## Implementation Scope

Eventual implementation is restricted to:

- `app/main.py`
- `templates/register.html` (new)
- `templates/onboarding.html`
- `templates/admin_dashboard.html`

This specification phase changes planning artifacts only and does not implement application code.