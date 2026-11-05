# Database migrations

`schema.sql` is the version 2 baseline schema and is applied transactionally to
new databases. `DatabaseInitializer` records the applied version in SQLite's
`user_version` pragma.

Future schema changes belong in numbered SQL files named
`NNNN_short_description.sql`, starting at version `0003`. Existing version 1
databases are upgraded by `0002_protect_core_rows_and_validate_emergency_timestamps.sql`.
Each migration is
applied in version order inside a transaction; version numbers must be
contiguous. Migration `0004_add_single_owner_account.sql` adds the independently
protected singleton Owner identity without rebuilding the existing users table.
Migration `0005_record_doctor_account_activation_state.sql` records the linked
account's activity state when a doctor profile is deactivated, allowing later
reactivation to restore only accounts that were active before that transition.
Existing doctor rows retain `NULL` because their previous account state cannot
be safely inferred.
Migration `0006_allow_assigned_doctor_intake_notes.sql` allows an active doctor
to create an intake-note correction only for a case currently assigned to that
doctor. Administrative roles retain their existing intake permissions, and
doctors cannot create cases or link patients through intake history.
Migration `0007_reject_closed_case_intake_updates.sql` rejects intake-note
corrections while a case is closed, both in the service and in the database
history trigger. SQLite triggers validate database invariants; they do not
authenticate application sessions. Direct access to the SQLite database file
is outside the application's session-authentication boundary.
Do not edit the baseline schema to represent changes to an already initialized
database.
