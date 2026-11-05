# Hospital Management System
## Software Requirements Specification (SRS)

**Document status:** Draft for review
**Project stage:** Requirements and design for a complete, operational system
**Target platform:** Local desktop application
**Intended users:** Hospital administrators, doctors, and receptionists

## 1. Purpose and Scope

The Hospital Management System (HMS) is a complete, operational desktop application for organizing patient demographics, staff and department information, appointments, emergency cases, and medical records. It will be developed in Python using object-oriented design, custom-implemented data structures, CustomTkinter for the graphical user interface, and SQLite for persistent storage.

The system is intended to support real workflows by authorized hospital staff on a local workstation. This is not a prototype or UI-only demonstration: all required features must be implemented, integrated, connected to persistent storage, and verified end to end. SQLite is the system of record; in-memory data structures may support application operations but must not be the only copy of business data.

### 1.1 Goals

- Centralize the specified hospital information in a consistent local database.
- Provide role-appropriate screens and enforce access rules for sensitive clinical data.
- Reduce scheduling conflicts and make patient and care information easier to find.
- Deliver a maintainable application whose required workflows operate end to end, rather than a foundation or mock-up that leaves core behavior for later.

### 1.2 Out of Scope for This Project

- Billing, insurance claims, pharmacy, laboratory, imaging, and inventory workflows.
- Patient self-service or public internet access.
- Multi-site synchronization, cloud hosting, and integration with external health systems.
- Clinical decision support or automated diagnosis.

These exclusions do not reduce the requirement to fully implement the six in-scope functional systems described in this SRS.

### 1.3 Operational Completeness

- Every in-scope workflow must use real application logic and persist/retrieve its data through SQLite; screens backed only by static, hard-coded, or success-shaped mock data do not satisfy the requirements.
- Test or demonstration patient data may be synthetic and must be clearly confined to development, automated tests, or an explicitly selected demonstration environment. Synthetic data is not a substitute for functional workflows.
- The application must report the actual outcome of operations. It must not report successful saves, updates, or deletes when persistence has failed.
- Running the UI alone is not evidence of completion. Release acceptance is governed by the end-to-end criteria in Section 14.
- Completion of the software requirements does not by itself authorize use with real patient information. Real-data use is gated by the readiness conditions in Section 14.

## 2. User Roles and Authorization

Users must sign in with an active account. Each account has one of the roles below. Owner is a single, independently protected first-run identity represented separately from ordinary account roles. The application must enforce permissions in its service/business layer as well as hide or disable unavailable UI actions; UI visibility alone is not authorization.

| Capability | Owner | Admin | Doctor | Receptionist |
|---|---|---|---|---|
| Sign in, sign out, view own profile | Yes | Yes | Yes | Yes |
| Create, update, deactivate user accounts and assign ordinary roles | Yes | Yes | No | No |
| Create another Owner or change Owner identity | No | No | No | No |
| Manage departments | Yes | Yes | No | No |
| Manage doctor directory and department assignment | Yes | Yes | No; may view own profile | No; may view directory |
| Add and update patient demographics | Yes | Yes | Yes, for patients involved in own care | Yes |
| Search and display patient demographics | Yes | Yes | Yes, for patients involved in own care | Yes |
| Create and manage appointments | Yes | Yes | View own schedule; update own appointment clinical status | Yes |
| Add and update emergency intake details | Yes | Yes | Yes, for assigned cases | Yes |
| Triage and update clinical emergency details | No | No | Yes, for assigned cases | No |
| View, create, and update medical records | No | No | Yes, for patients involved in own care | No |
| Delete or permanently erase clinical records | No | No | No | No |
| View audit events | Yes, without clinical note contents | Yes, without clinical note contents | No | No |

**Authorization rules**

- Admin privileges do not automatically grant access to medical record contents.
- Owner privileges are limited to system administration and audit metadata; Owner does not receive clinical-content access by default.
- Exactly one Owner may be established during first-run setup, only before any user account exists. Ordinary account administration cannot create, replace, deactivate, or change the Owner; recovery requires a separately approved procedure.
- Doctors may access only records and cases related to their care responsibilities. Access outside that scope requires an explicitly approved future policy.
- Receptionists may access demographic and scheduling information needed for intake but not diagnoses, treatment notes, or other medical record contents.
- Account deactivation must prevent future sign-in without erasing historical activity.
- Any permission exception must be explicit, auditable, and approved before implementation.

## 3. Functional Requirements

Every listed system must support **Add**, **Update**, **Delete/deactivate**, **Search**, and **Display** where applicable. These are logical operations, not permission for unrestricted permanent deletion. The following sections define system-specific behavior and restrictions.

### 3.1 Patient Management

- **Add:** Create a patient with a unique patient number and required identity/contact details.
- **Update:** Correct demographic/contact details while retaining the patient number.
- **Delete/deactivate:** Mark a patient inactive; do not physically remove a patient with appointments, cases, records, or audit history.
- **Search:** Find patients by patient number and permitted identity/contact fields.
- **Display:** Show a paginated or bounded list of patients and a role-filtered patient profile.
- Receptionists and authorized doctors may manage demographic information; Admin may manage demographics but is not thereby granted clinical-record access.

### 3.2 Doctor Management

- **Add:** Admin creates a doctor directory entry and associates it with a user account and department.
- **Update:** Admin changes directory and department details; a doctor may view their own profile.
- **Delete/deactivate:** Admin deactivates the doctor and, where applicable, the linked account. Existing records and completed appointments remain.
- **Search:** Search the directory by name, specialty, department, or active status, subject to role.
- **Display:** Show directory information and a doctor's schedule summary. Clinical data is not part of the directory.

### 3.3 Appointment Management

- **Add:** Receptionist or Admin schedules an appointment for an active patient with an active doctor, subject to availability.
- **Update:** Receptionist or Admin changes scheduling details; a doctor may update the clinical status of an appointment on their schedule.
- **Delete/deactivate:** Cancel an appointment with a cancellation status and reason where appropriate; retain the appointment history.
- **Search:** Search by patient, doctor, date range, and status, restricted to the user's permissions.
- **Display:** Show lists and schedules filtered by date, doctor, patient, and status.
- The default appointment duration is 30 minutes and must be configurable. The system must prevent overlapping active appointments for the same doctor.
- Clinic operating hours, time zone, cancellation rules, and other scheduling policies (including any additional restrictions on appointment duration or booking windows) still require confirmation before implementation; do not assume unapproved scheduling rules.

### 3.4 Emergency Management

- **Add:** Receptionist records an emergency intake and may associate it with an existing patient. A case may initially have no patient association when identity is unknown.
- **Update:** Receptionist may update intake and administrative details; an assigned doctor may update triage, clinical status, and outcome details.
- **Delete/deactivate:** A case must not be permanently deleted; authorized correction or closure must preserve an audit trail.
- **Search:** Search by case number, patient (if identified), date, status, and permitted triage category.
- **Display:** Show an operational queue with only the information appropriate to the user's role.
- Cases must move through defined statuses (for example: `Open`, `In Treatment`, `Closed`). The final status list and clinical priority scale require review by hospital stakeholders.

### 3.5 Department Management

- **Add:** Admin creates a department with a unique name.
- **Update:** Admin changes its name or descriptive details.
- **Delete/deactivate:** Admin deactivates a department; a department referenced by doctors or historical data must not be physically deleted.
- **Search:** Search by name and active status.
- **Display:** Show department details and associated active doctors.

### 3.6 Medical Records

- **Add:** A doctor creates a clinical record for a patient under their care; an appointment link may be included.
- **Update:** The authoring doctor may amend a record while preserving an amendment audit event. The system must not silently overwrite clinical history.
- **Delete/deactivate:** No permanent deletion through ordinary application workflows. Corrections must be recorded as amendments or a separately approved, audited correction process.
- **Search:** Doctors may search records for patients under their care by patient, author, date, and record category.
- **Display:** Only authorized doctors may view clinical record contents. Admin may inspect audit metadata, not clinical note contents; receptionists have no clinical-record access.
- The initial record content and categories must be agreed before implementation. This SRS does not prescribe a clinical note template.

## 4. Data Structures

Required custom data structures must be implemented within the project rather than replaced by ready-made data-structure libraries. SQLite remains the durable source of truth. Custom structures may hold data temporarily, accelerate permitted lookups, or support queues and histories; they must not bypass authorization or persist sensitive data as an unprotected secondary store.

All structures below are custom implementations; do not substitute a ready-made data-structure library. Complexity figures are expected time bounds for the stated operations. For hash-based structures, average-case bounds assume a suitable hash function and controlled load factor; worst-case collisions can make an operation O(n). For dynamic arrays, append is amortized.

| Data structure | Intended use and rationale | Basic operations, purpose, and expected time complexity |
|---|---|---|---|---|
| Custom dynamic array/list | Hold bounded, ordered query results for screen tables and other in-memory collections. Do not load an unbounded hospital history. | `get(index)` / `set(index, value)` for indexed access or replacement: O(1). `append(value)` to add a result: amortized O(1). `insert(index, value)` / `remove_at(index)` to modify a position while preserving order: O(n) due to shifting. `find(value)` for a linear lookup: O(n). `iterate()` to display/process all elements: O(n). |
| Custom hash table | Temporarily map unique patient, doctor, or appointment identifiers to permitted in-memory results. Database uniqueness remains authoritative. | `put(key, value)` to add or replace: expected O(1), worst O(n). `get(key)` / `contains(key)` to look up or test membership: expected O(1), worst O(n). `remove(key)` to remove an in-memory entry: expected O(1), worst O(n). `iterate_entries()` to visit all entries: O(n). |
| Custom queue | Preserve first-in-first-out order for intake or administrative work where that ordering is approved; it is not a substitute for clinical triage. | `enqueue(value)` to add at the rear: amortized O(1). `dequeue()` to remove the oldest item: O(1). `peek()` to inspect the oldest item without removal: O(1). `is_empty()` / `size()` for queue state: O(1). `find(value)` when needed: O(n). |
| Custom priority queue (implemented using a binary heap) | Optionally order emergency work by an approved triage priority and arrival-time tie-break. The clinical scale and policy must be approved; the structure does not make clinical decisions. | `enqueue(item, priority)` to insert: O(log n). `peek_highest_priority()` to inspect the next item: O(1). `dequeue_highest_priority()` to remove the next item: O(log n). `is_empty()` / `size()` for queue state: O(1). `find(item)` without an auxiliary index: O(n). **The binary heap is the implementation mechanism for this priority queue, not a separate project data structure or a second structure for the same function.** |
| Custom stack | Maintain in-session navigation history or reversible, non-clinical UI actions; never roll back persisted clinical history. | `push(value)` to add the latest item: amortized O(1). `pop()` to remove the latest item: O(1). `peek()` to inspect it without removal: O(1). `is_empty()` / `size()` for stack state: O(1). `find(value)` when needed: O(n). |
| Custom set (hash-based) | Hold a bounded collection of unique in-memory identifiers for duplicate checks or membership tests. Persisted uniqueness must still be enforced by SQLite constraints. | `add(value)` / `remove(value)` to change membership: expected O(1), worst O(n). `contains(value)` to test membership: expected O(1), worst O(n). `union(other)` / `intersection(other)` when required for bounded result collections: expected O(n + m), where n and m are the input sizes, subject to hash behavior. `iterate()` to visit members: O(n). |

Empty-state behavior, bounds/resize behavior where relevant, and error conditions must be specified and tested for every structure. These operations support in-memory application behavior only; they do not replace database persistence, authorization checks, or database constraints.

## 5. Object-Oriented Design Principles

- **Encapsulation:** Keep state and validation rules within appropriate domain/service boundaries; avoid unrestricted direct mutation of sensitive records.
- **Abstraction:** Separate UI, business workflows, persistence, and custom data-structure interfaces so each can be changed and tested independently.
- **Inheritance:** Use only where a genuine, stable “is-a” relationship exists. Prefer composition for role permissions and shared services; do not force all users into an inheritance hierarchy merely to share fields.
- **Polymorphism:** Where multiple implementations of a stable behavior are needed, expose a common interface and test each implementation. Avoid speculative frameworks.
- **Single responsibility and separation of concerns:** UI components handle presentation and user interaction; services enforce workflows and authorization; database components handle queries and transactions; models represent domain data.
- **Dependency direction:** UI should call services, and services should depend on explicit persistence abstractions rather than embedding SQL in screen code.

## 6. SQLite Data Model

All tables use a primary key. Foreign keys must be enabled for each database connection. Use `NOT NULL`, `UNIQUE`, `CHECK`, and indexes where appropriate. Store timestamps consistently in an agreed format (recommended: UTC ISO 8601 text) and convert for display.

| Table | Core fields (proposed) | Relationships and notes |
|---|---|---|---|---|
| `users` | `user_id`, `username`, `password_hash`, `role`, `is_active`, `created_at`, `updated_at` | One account may be linked to one doctor profile; Admin and Receptionist accounts need no doctor profile. Store password hashes, never plaintext passwords. |
| `departments` | `department_id`, `name`, `description`, `is_active`, `created_at`, `updated_at` | One department has zero or more doctors. Department name must be unique under the agreed case-sensitivity policy. |
| `doctors` | `doctor_id`, `user_id`, `department_id`, `full_name`, `specialty`, `phone`, `is_active` | `user_id` is unique and references `users`; `department_id` references `departments`. |
| `patients` | `patient_id`, `patient_number`, `full_name`, `date_of_birth`, `sex` (if required), `phone`, `address`, `emergency_contact`, `is_active`, `created_at`, `updated_at` | One patient may have many appointments, emergency cases, and medical records. Patient number is unique. Collect only data necessary for approved workflows. |
| `doctor_patient_assignments` | `assignment_id`, `doctor_id`, `patient_id`, `assigned_by_user_id`, `assigned_at`, `ended_by_user_id` (nullable), `ended_at` (nullable), `end_reason` (nullable) | Records the care relationship between a doctor and patient, including its lifecycle and the users/timestamps responsible for starting and ending it. `doctor_id` references `doctors`; `patient_id` references `patients`; assigning and ending users reference `users`. Keep ended assignments as history. |
| `appointments` | `appointment_id`, `patient_id`, `doctor_id`, `scheduled_start`, `scheduled_end`, `status`, `reason` (if approved), `created_by_user_id`, `created_at`, `updated_at` | Each appointment references one patient and one doctor; one user creates it. Index scheduling and search fields. Overlap prevention must be enforced transactionally in the service/database workflow. |
| `emergency_cases` | `emergency_case_id`, `case_number`, `patient_id` (nullable), `assigned_doctor_id` (nullable), `intake_user_id`, `triage_category`, `status`, `arrival_at`, `closed_at`, `intake_notes` (restricted), `created_at`, `updated_at` | Patient may be unknown at intake. Doctor assignment and patient association may be added later. Restrict access to clinical details by role. |
| `medical_records` | `medical_record_id`, `patient_id`, `doctor_id`, `appointment_id` (nullable), `record_type`, `record_content`, `created_at`, `updated_at`, `is_amended` | Each record references a patient and authoring doctor; optional appointment reference. Clinical content is restricted to authorized doctors. Each record has zero or more immutable prior-content versions in `medical_record_versions`. |
| `medical_record_versions` | `version_id`, `medical_record_id`, `patient_id_snapshot`, `doctor_id_snapshot`, `appointment_id_snapshot`, `record_type_snapshot`, `record_content_snapshot`, `created_at_snapshot`, `updated_at_snapshot`, `is_amended_snapshot`, `modified_by_user_id`, `modified_at` | Many versions belong to one medical record. Before every modification, store a complete snapshot of the record's pre-change state: every field in `medical_records` other than its stable identity, including all mutable fields and any additional record fields introduced later. `medical_record_id` identifies the source record; the snapshot columns preserve its prior values. Record who made the change and when. Insert the snapshot, required audit event, and updated record in one transaction. |
| `audit_logs` | `audit_log_id`, `user_id`, `action`, `entity_type`, `entity_id`, `occurred_at`, `details` (non-clinical metadata only) | Records security-relevant create/update/deactivate, sign-in, and access events. Avoid copying clinical note contents or passwords into logs. |

**Care-assignment lifecycle and authorization**

- An assignment is created only through an authorized, explicit assignment workflow. Record the assigning user and timestamp; do not infer a care assignment merely from an appointment, department membership, or the doctor's ability to search for a patient.
- End an assignment by recording `ended_by_user_id`, `ended_at`, and, where provided, `end_reason`; never erase the assignment row during ordinary use. An assignment is active while `ended_at` is null.
- A partial unique index on `(doctor_id, patient_id)` for rows where `ended_at IS NULL` prevents duplicate active assignments for the same doctor/patient pair while allowing a later assignment after an earlier one has ended.
- Add indexes on `doctor_id`, `patient_id`, and the active-assignment lookup fields (including the active pair) to support authorization checks and care-scope searches. Retain the unique active-pair partial index as an integrity constraint.
- Doctor access to patient demographics and medical records must be checked against an active `doctor_patient_assignments` row on every service request. Emergency-case access remains governed by the assigned-doctor and case rules in Section 3.4; a care assignment alone does not grant access to an emergency case. Do not grant patient-data access outside the applicable approved scope, and do not rely on cached assignments as the authorization source.
- Creating or ending an assignment must be authorized and audited; the assignment change and its required audit event must commit in the same transaction. The role(s) permitted to create or end assignments require approval and are not inferred here.
- Whether a doctor may access historical patient information after an assignment ends is not specified; deny such access unless an explicit policy is approved. Other roles remain governed by their separately defined permissions.

### 6.1 Relationship Summary

- `departments` 1-to-many `doctors`.
- `users` 1-to-zero/one `doctors`.
- `doctors` many-to-many `patients` through `doctor_patient_assignments`, with assignment history retained.
- `patients` 1-to-many `appointments`, `emergency_cases`, and `medical_records`.
- `doctors` 1-to-many `appointments`, `emergency_cases` (assignments), and `medical_records`.
- `medical_records` 1-to-many `medical_record_versions`; each version references exactly one medical record and the user who initiated the modification.
- `appointments` 1-to-many or zero-to-many `medical_records` unless stakeholders approve a stricter one-record-per-appointment rule.
- `users` 1-to-many care assignments created/ended, created appointments, emergency intakes, audit events, and medical-record version events.

### 6.2 Referential Integrity and Retention

- Use restrictive foreign-key behavior for referenced historical entities; prefer deactivation over cascading deletion.
- Retain ended doctor-patient assignments and do not cascade-delete their history.
- Permit `emergency_cases.patient_id` to be null until identity is established.
- Do not use database cascade deletion for medical or audit history.
- Do not expose deletion or editing of `medical_record_versions` through ordinary application workflows. Retain them as append-only history; any exceptional retention or legal disposition must follow an approved, separately controlled and audited process.
- Define backups, retention, recovery, encryption-at-rest expectations, and database-file access controls before handling real patient information.

## 7. CustomTkinter Screens

| Screen | Purpose | Access |
|---|---|---|
| Sign In | Authenticate an active account and route to role-appropriate home screen | All roles |
| Dashboard | Show role-specific shortcuts, schedule summaries, and operational counts without exposing unauthorized clinical details | All roles, filtered |
| Patient List and Patient Profile | Search, display, add, update, and deactivate demographic data | Admin, Doctor (care-scoped), Receptionist |
| Doctor Directory and Doctor Profile | Manage staff directory and department assignment; display availability summary | Admin; restricted display for other roles |
| Appointment Calendar/List and Appointment Form | Schedule, search, display, reschedule, and cancel appointments | Admin, Receptionist; Doctor sees own schedule and permitted status controls |
| Emergency Queue and Case Details | Record intake, assign/triage, update status, and display permitted case details | Receptionist, Doctor; Admin receives non-clinical oversight |
| Department List and Department Form | Add, edit, search, display, and deactivate departments | Admin |
| Medical Records List and Record Editor/Viewer | Create, amend, search, and display clinical records | Authorized Doctors only |
| User and Role Management | Create, update, deactivate accounts, and assign supported roles | Admin |
| Audit Log Viewer | Review security and change metadata without clinical note content | Admin |

All list screens should provide clear empty states, loading/operation feedback, and validation messages. Destructive or status-changing actions require confirmation and must explain whether the action deactivates, cancels, closes, or amends a record rather than erasing it.

## 8. Use Cases and Basic Scenarios

### UC-01: Sign In
1. User enters credentials.
2. System verifies the account and active status.
3. System creates an authenticated session and opens the permitted dashboard.
4. On failure, the system shows a generic error without revealing whether the username exists and records an appropriate security event.

### UC-01a: Secure First Admin Setup
1. During first-run initialization, the system verifies that no Admin account has already been created.
2. An authorized operator uses the approved, access-controlled initial-setup procedure to provide the first Admin account details and choose its credential.
3. The system rejects weak/invalid credentials according to the approved password policy, stores only a password hash, and creates the account with the Admin role and active status.
4. Account creation and its required audit event are committed atomically. If either fails, neither is committed and setup is not reported as complete.
5. After successful creation, permanently disable the initial-Admin setup path for ordinary use. Subsequent Admin accounts can only be created by an authenticated Admin through normal account management.
6. Never use a fixed/default password, silently create an Admin account, expose an unauthenticated reusable setup path, or allow setup to bypass authorization, audit, or credential controls.

### UC-02: Register or Update a Patient
1. Receptionist or authorized user searches for a likely existing patient.
2. If no match is found, the user enters required demographic details.
3. System validates the fields and unique patient number, then saves the patient.
4. System displays the saved profile and reports duplicate or invalid input without losing entered data.

### UC-03: Schedule an Appointment
1. Receptionist selects an active patient, doctor, and requested time.
2. System validates the time and checks for overlapping active appointments.
3. If available, the system saves the appointment and displays confirmation.
4. If unavailable, it explains the conflict and allows the user to choose another time.

### UC-04: View Doctor Schedule
1. Doctor signs in.
2. System displays only that doctor's appointments within the selected date range.
3. Doctor opens an appointment and updates only the permitted status or clinical workflow fields.

### UC-05: Receive an Emergency Case
1. Receptionist opens a new case and records required intake details.
2. If the patient is known, the receptionist associates the patient; otherwise, the case remains unlinked.
3. System assigns a unique case number and adds the case to the operational queue.
4. An authorized doctor reviews the case, records triage/clinical updates, and changes its status.
5. After identity is confirmed, an authorized user links the case to the patient and the system records the change.

### UC-06: Create or Amend a Medical Record
1. Doctor opens a patient within their care scope.
2. Doctor creates a record or selects an existing record for amendment.
3. System validates required fields, stores the record/change, and writes an audit event.
4. Receptionist and Admin cannot open clinical record contents.

### UC-07: Manage Departments and Doctor Accounts
1. Admin creates or updates a department.
2. Admin creates or updates a doctor account and profile, assigning an active department.
3. System validates uniqueness and references.
4. When a doctor or department is no longer active, Admin deactivates it; historical appointments and records remain available under their access rules.

### UC-08: Search and Display Records
1. User chooses a supported filter or search term.
2. System applies role-based access restrictions before returning results.
3. System displays bounded results and a clear no-results state.
4. The user can open only details permitted for their role.

## 9. Validation Requirements

- Trim surrounding whitespace and reject required fields that are empty.
- Enforce unique usernames, patient numbers, doctor-to-user links, and department names.
- Validate date/time values, valid appointment end-after-start, and supported status/role values.
- Reject appointments for inactive patients/doctors or outside approved scheduling rules.
- Check appointment conflicts transactionally so simultaneous actions cannot create overlapping active appointments.
- Validate foreign-key references before saving and rely on SQLite foreign-key constraints as a second integrity layer.
- Apply sensible maximum lengths and input formats to names, phone numbers, addresses, and free text; exact formats and limits require stakeholder approval.
- Do not treat user-provided search text as SQL. Use parameterized database operations.
- Protect authentication secrets using a vetted password-hashing approach; do not store plaintext passwords or log credentials.
- On first-run initialization only, provide a controlled procedure for creating the single Owner account with a credential chosen during setup. The Owner is the initial system-administration account; create no default credential and do not silently create the account. Store only a salted, memory-hard password hash and atomically audit the setup. Disable first-Owner setup after any account is created; require a separately approved recovery procedure if the Owner is unavailable.
- Prevent unauthorized access even if a screen is invoked outside its expected navigation path.
- Collect only necessary patient data. Define applicable privacy, consent, retention, and audit policies before real clinical use.

## 10. Error Handling and Recovery

- Show understandable, actionable messages for validation failures, permission denials, missing records, duplicate data, scheduling conflicts, and database failures.
- Preserve user-entered form data when a save fails where safe to do so.
- Use database transactions for related changes; roll back incomplete operations and never display a success confirmation for a failed save.
- Keep detailed technical diagnostics in restricted logs; do not expose stack traces, SQL details, credentials, or clinical content in routine UI errors.
- Handle database unavailability or corruption explicitly and guide the user to an administrator; do not silently substitute an empty database or in-memory-only success.
- **Mandatory audit policy:** Audit events required for security-sensitive actions (including successful authentication/session establishment, authorization-sensitive access, and account/permission changes) and clinical changes must be written to `audit_logs` as part of the same SQLite transaction as the protected business change whenever the event changes persisted data. A clinical-record creation must atomically write the record and its audit event; every clinical-record modification must atomically write its pre-change version, audit event, and updated record. Do not commit the protected operation unless the mandatory audit write succeeds.
- If a mandatory audit write fails, roll back the entire transaction so neither the business change nor its associated version is partially committed; do not update in-memory state or show success. For an access/session operation without a business-data transaction, fail closed: do not grant the session or protected access unless its required audit event is durably recorded.
- Surface a safe, actionable error to the user and emit a restricted operational diagnostic/alert without including credentials or clinical note contents. Preserve existing committed data; do not retry in a way that can duplicate an operation or audit event. If the database cannot guarantee the required event, block the protected operation and direct the user to an administrator. Resume only after database/audit health is restored and verified.
- Audit/version history is append-only through normal application use. Never delete or overwrite prior audit events or medical-record versions as part of ordinary edits or cleanup.
- Make deactivate, cancel, close, and amend outcomes distinct from physical deletion in messages and screens.

## 11. Non-Functional Requirements

- **Security and privacy:** Role-based least privilege, secure password storage, session sign-out, restricted database-file access, and auditable changes are required before real patient data is used.
- **Reliability:** Core changes must be transactionally consistent; failed operations must not leave partial records.
- **Usability:** Forms and messages must be understandable to non-technical staff, keyboard navigable where practical, and consistent across roles.
- **Maintainability:** Separate presentation, services, persistence, domain models, and custom data structures.
- **Testability:** Unit tests for custom data structures and validation; integration tests for database constraints and core workflows; permission tests for each role.
- **Performance:** Search and list screens should use bounded results and appropriate indexes. Numeric response-time targets require agreement after expected data volume is known.
- **Accessibility/localization:** The interface language, accessibility expectations, and date/number formats require stakeholder confirmation.

## 12. Assumptions and Open Decisions

### 12.1 Agreed Assumptions

1. The application interface is in English and must support entering and displaying Arabic patient and staff data.
2. The default appointment duration is 30 minutes and must be configurable.
3. Version 1 is intended to run on one workstation/device; multi-workstation deployment and synchronization are out of scope.
4. Synthetic patient data is permitted only in development, automated testing, and explicitly designated demonstrations. It must not be treated as real clinical information or used to imply operational readiness.

### 12.2 Open Decisions

The following items must be confirmed before or during implementation:

1. Hospital jurisdiction and applicable patient privacy, consent, retention, and data-protection rules.
2. Required patient demographic fields and patient-number generation policy.
3. Operating hours, time zone, cancellation rules, and whether appointments may overlap across different doctors. The 30-minute default duration is fixed as an assumption; permitted duration changes require an agreed policy.
4. Which authorized role(s) may create and end doctor-patient care assignments, and what operational approval is required for those actions.
5. Emergency triage scale, priority policy, role handoffs, and required intake fields.
6. Medical-record template, record categories, and whether doctors may edit each other's records. Prior-content versioning before every update and ordinary-use non-deletion are requirements, not open decisions.
7. Whether Admin may see additional clinical information; this draft denies such access by default.
8. Password reset, session timeout, the controlled first-Admin setup/recovery procedure, backup, restore, encryption, and audit retention policies.
9. Accessibility expectations and date/number display formats.

## 13. Acceptance Criteria for This Requirements Document

- The three user roles and their permissions are documented.
- The six requested functional systems and applicable Add, Update, Delete/deactivate, Search, and Display operations are specified.
- Candidate custom data structures and their rationale are documented.
- OOP principles, SQLite entities and relationships, screens, use cases, validation, and error handling are described.
- Open policy decisions are visible for review.
- This document contains no implementation code and does not change the existing project structure.

## 14. Product Completion and Release Acceptance

The HMS is complete only when all criteria below pass. A successful application launch or screen demonstration alone is insufficient.

### 14.1 End-to-End Functional Acceptance

- **Authentication and authorization:** Each role can sign in and out; invalid or inactive accounts are rejected; service-layer tests prove allowed actions succeed and forbidden actions are denied independently of UI visibility.
- **Patient management:** An authorized user can add a patient, retrieve and search the saved patient after the operation (including after application restart), update details, and deactivate without erasing referenced history.
- **Doctor and department management:** Admin can create and manage departments and doctor accounts/profiles, assign doctors to departments, and search/retrieve the saved data. Invalid or inactive relationships are rejected, and history remains intact after deactivation.
- **Appointment management:** Receptionist/Admin can create, retrieve, search, update/reschedule, and cancel appointments; doctors can view their own schedule and make only permitted changes. Conflicting appointments are rejected, and saved results persist across restart.
- **Emergency management:** Receptionist can create and retrieve an emergency case with or without a known patient; an authorized doctor can access assigned cases and update clinical status; linking a patient later is persisted and audited. Unauthorized roles cannot access restricted case details.
- **Medical records:** An authorized doctor can create, retrieve, search, and amend a record for a patient in scope. Amendment history is retained. Receptionist and Admin cannot access clinical contents under the default policy.
- **Search and display:** Every in-scope system returns data from persistent storage, applies role filters before exposing results, and handles empty results and invalid queries clearly.
- **Data integrity and errors:** Validation, database constraints, transactions, error reporting, and rollback behavior are exercised. A failed operation never appears successful or silently falls back to in-memory data.
- **Persistence:** Tests verify that saved records can be read back and remain available after closing and reopening the application.

### 14.2 Verification Evidence

- Automated unit tests cover custom data structures, validation, and other isolated business rules.
- Integration tests exercise SQLite persistence, constraints, transactions, and service-layer authorization.
- End-to-end tests or documented repeatable acceptance tests exercise the scenarios above across the connected UI, services, and database.
- Tests use isolated temporary databases and synthetic fixtures; they must not require or modify real patient data.
- Documentation explains environment setup, installation, database initialization, startup, role-specific usage, test execution, backup/restore procedures, and known operational limitations.
- No core in-scope function may be left as a placeholder, static demonstration, or unimplemented workflow at release.

### 14.3 Real-Data Readiness Gate

Before the system is used with real patient information, the responsible organization must complete and approve all of the following:

- Security and privacy review of the implemented application, authorization rules, data storage, access controls, and audit behavior.
- Applicable legal, regulatory, consent, data-retention, and jurisdiction-specific review by qualified stakeholders.
- A documented backup and recovery plan, with a successful restore test and assigned operational responsibility.
- Defined policies for account lifecycle, password recovery, session handling, incident response, data access, and retention.
- Approval of the unresolved clinical and operational decisions in Section 12.

Passing software acceptance tests does not establish legal compliance or replace organizational approval for handling real patient data.

## 15. Implementation Phases

Implementation proceeds in the following order. Each phase must meet its exit criteria before dependent work is considered complete. Verification is continuous; the dedicated testing phase performs full integrated acceptance.

1. **Requirements and solution design:** Review and approve roles, workflows, data fields, clinical policies, authorization boundaries, error behavior, and open decisions. Produce an agreed design and acceptance-test plan before implementation begins.
2. **SQLite schema and persistence foundation:** Define and initialize the schema, foreign keys, constraints, indexes, transactions, and persistence/repository operations, including the append-only medical-record version and mandatory audit requirements. Verify schema creation and persistence behavior against an isolated test database.
3. **Domain models and custom data structures:** Define the domain boundaries and implement the required custom structures with their stated operations, complexity expectations, and unit tests. Confirm they support application workflows without replacing SQLite as the source of truth.
4. **Service and authorization workflows:** Implement authentication, role enforcement, validation, and integrated services for patients, doctors, departments, appointments, emergency cases, medical records, audit events, and version history. Verify authorization and transaction behavior at the service boundary before connecting screens.
5. **CustomTkinter interface:** Build role-appropriate screens and connect every action to the corresponding service. Implement English interface text and Arabic data entry/display, actual success/failure feedback, and safe handling of unavailable or denied operations. Do not substitute static or mock data for functional workflows.
6. **Integrated verification and acceptance:** Run unit, database integration, service authorization, and end-to-end tests using isolated databases and synthetic data. Execute each release-acceptance scenario in Section 14, fix failures, and repeat affected and regression tests.
7. **Operational readiness and final run:** Complete installation/startup/use documentation, database initialization, backup and restore instructions, and final clean-environment run-through. Review security, privacy, audit, backup/recovery, and applicable legal readiness gates. Do not authorize real-patient-data use until Section 14.3 is approved.
