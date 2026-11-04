CREATE TABLE emergency_doctor_assignments (
    assignment_event_id INTEGER PRIMARY KEY,
    emergency_case_id INTEGER NOT NULL
        REFERENCES emergency_cases(emergency_case_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0),
    previous_doctor_id INTEGER
        REFERENCES doctors(doctor_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    new_doctor_id INTEGER
        REFERENCES doctors(doctor_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    change_reason TEXT,
    record_origin TEXT NOT NULL
        CHECK (record_origin IN ('application_event', 'migration_baseline')),
    event_at TEXT
        CHECK (
            event_at IS NULL
            OR (
                event_at GLOB '????-??-??T??:??:??*Z'
                AND julianday(event_at) IS NOT NULL
                AND strftime('%Y-%m-%dT%H:%M:%S', event_at)
                    = substr(event_at, 1, 19)
            )
        ),
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            recorded_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(recorded_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', recorded_at)
                = substr(recorded_at, 1, 19)
        ),
    actor_user_id INTEGER
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    audit_log_id INTEGER UNIQUE
        REFERENCES audit_logs(audit_log_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (
        (
            record_origin = 'application_event'
            AND event_at IS NOT NULL
            AND actor_user_id IS NOT NULL
            AND audit_log_id IS NOT NULL
            AND new_doctor_id IS NOT NULL
            AND (previous_doctor_id IS NULL OR previous_doctor_id <> new_doctor_id)
            AND change_reason IS NOT NULL
            AND length(trim(change_reason)) > 0
        )
        OR
        (
            record_origin = 'migration_baseline'
            AND event_at IS NULL
            AND actor_user_id IS NULL
            AND audit_log_id IS NULL
            AND previous_doctor_id IS NULL
            AND change_reason IS NULL
        )
    ),
    UNIQUE (emergency_case_id, sequence_no)
);

CREATE TABLE emergency_triage_history (
    triage_history_id INTEGER PRIMARY KEY,
    emergency_case_id INTEGER NOT NULL
        REFERENCES emergency_cases(emergency_case_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0),
    previous_triage_category TEXT,
    new_triage_category TEXT,
    change_reason TEXT,
    record_origin TEXT NOT NULL
        CHECK (record_origin IN ('application_event', 'migration_baseline')),
    event_at TEXT
        CHECK (
            event_at IS NULL
            OR (
                event_at GLOB '????-??-??T??:??:??*Z'
                AND julianday(event_at) IS NOT NULL
                AND strftime('%Y-%m-%dT%H:%M:%S', event_at)
                    = substr(event_at, 1, 19)
            )
        ),
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            recorded_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(recorded_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', recorded_at)
                = substr(recorded_at, 1, 19)
        ),
    actor_user_id INTEGER
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    audit_log_id INTEGER UNIQUE
        REFERENCES audit_logs(audit_log_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (
        (
            record_origin = 'application_event'
            AND event_at IS NOT NULL
            AND actor_user_id IS NOT NULL
            AND audit_log_id IS NOT NULL
            AND new_triage_category IS NOT NULL
            AND new_triage_category IN ('RED', 'ORANGE', 'YELLOW', 'GREEN', 'BLUE')
            AND previous_triage_category IS NOT new_triage_category
            AND change_reason IS NOT NULL
            AND length(trim(change_reason)) > 0
        )
        OR
        (
            record_origin = 'migration_baseline'
            AND event_at IS NULL
            AND actor_user_id IS NULL
            AND audit_log_id IS NULL
            AND change_reason IS NULL
        )
    ),
    UNIQUE (emergency_case_id, sequence_no)
);

CREATE TABLE emergency_outcome_versions (
    outcome_version_id INTEGER PRIMARY KEY,
    emergency_case_id INTEGER NOT NULL
        REFERENCES emergency_cases(emergency_case_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    version_no INTEGER NOT NULL CHECK (version_no > 0),
    outcome_code TEXT NOT NULL
        CHECK (
            outcome_code IN (
                'Discharged', 'Admitted', 'Transferred',
                'Referred', 'Deceased', 'Other'
            )
        ),
    outcome_explanation TEXT,
    supersedes_version_id INTEGER,
    change_reason TEXT,
    record_origin TEXT NOT NULL
        CHECK (record_origin IN ('application_event', 'migration_baseline')),
    event_at TEXT,
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            recorded_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(recorded_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', recorded_at)
                = substr(recorded_at, 1, 19)
        ),
    actor_user_id INTEGER
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    audit_log_id INTEGER UNIQUE
        REFERENCES audit_logs(audit_log_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (
        outcome_code <> 'Other'
        OR (
            outcome_explanation IS NOT NULL
            AND length(trim(outcome_explanation)) > 0
        )
    ),
    CHECK (
        event_at IS NULL
        OR (
            event_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(event_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', event_at)
                = substr(event_at, 1, 19)
        )
    ),
    CHECK (
        (
            record_origin = 'application_event'
            AND event_at IS NOT NULL
            AND actor_user_id IS NOT NULL
            AND audit_log_id IS NOT NULL
        )
        OR
        (
            record_origin = 'migration_baseline'
            AND event_at IS NULL
            AND actor_user_id IS NULL
            AND audit_log_id IS NULL
        )
    ),
    UNIQUE (emergency_case_id, version_no),
    UNIQUE (emergency_case_id, outcome_version_id),
    FOREIGN KEY (emergency_case_id, supersedes_version_id)
        REFERENCES emergency_outcome_versions(
            emergency_case_id, outcome_version_id
        )
        ON DELETE RESTRICT ON UPDATE RESTRICT
);

CREATE TABLE emergency_status_history (
    status_history_id INTEGER PRIMARY KEY,
    emergency_case_id INTEGER NOT NULL
        REFERENCES emergency_cases(emergency_case_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0),
    previous_status TEXT,
    new_status TEXT NOT NULL CHECK (length(trim(new_status)) > 0),
    transition_type TEXT NOT NULL
        CHECK (
            transition_type IN (
                'case_created', 'status_changed', 'reopened',
                'migration_baseline'
            )
        ),
    change_reason TEXT,
    record_origin TEXT NOT NULL
        CHECK (record_origin IN ('application_event', 'migration_baseline')),
    event_at TEXT
        CHECK (
            event_at IS NULL
            OR (
                event_at GLOB '????-??-??T??:??:??*Z'
                AND julianday(event_at) IS NOT NULL
                AND strftime('%Y-%m-%dT%H:%M:%S', event_at)
                    = substr(event_at, 1, 19)
            )
        ),
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            recorded_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(recorded_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', recorded_at)
                = substr(recorded_at, 1, 19)
        ),
    actor_user_id INTEGER
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    audit_log_id INTEGER UNIQUE
        REFERENCES audit_logs(audit_log_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (
        (
            record_origin = 'application_event'
            AND transition_type <> 'migration_baseline'
            AND event_at IS NOT NULL
            AND actor_user_id IS NOT NULL
            AND audit_log_id IS NOT NULL
            AND (
                (transition_type = 'case_created' AND previous_status IS NULL)
                OR
                (
                    transition_type <> 'case_created'
                    AND previous_status IS NOT NULL
                    AND previous_status <> new_status
                )
            )
            AND (
                transition_type <> 'reopened'
                OR (
                    change_reason IS NOT NULL
                    AND length(trim(change_reason)) > 0
                )
            )
        )
        OR
        (
            record_origin = 'migration_baseline'
            AND transition_type = 'migration_baseline'
            AND event_at IS NULL
            AND actor_user_id IS NULL
            AND audit_log_id IS NULL
            AND previous_status IS NULL
            AND change_reason IS NULL
        )
    ),
    UNIQUE (emergency_case_id, sequence_no)
);

CREATE TABLE emergency_intake_history (
    intake_history_id INTEGER PRIMARY KEY,
    emergency_case_id INTEGER NOT NULL
        REFERENCES emergency_cases(emergency_case_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    version_no INTEGER NOT NULL CHECK (version_no > 0),
    previous_case_number_snapshot TEXT,
    case_number_snapshot TEXT NOT NULL
        CHECK (length(trim(case_number_snapshot)) > 0),
    previous_patient_id_snapshot INTEGER
        REFERENCES patients(patient_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    patient_id_snapshot INTEGER
        REFERENCES patients(patient_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    previous_intake_user_id_snapshot INTEGER
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    intake_user_id_snapshot INTEGER NOT NULL
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    previous_arrival_at_snapshot TEXT,
    arrival_at_snapshot TEXT NOT NULL
        CHECK (
            arrival_at_snapshot GLOB '????-??-??T??:??:??*Z'
            AND julianday(arrival_at_snapshot) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', arrival_at_snapshot)
                = substr(arrival_at_snapshot, 1, 19)
        ),
    intake_notes_snapshot TEXT NOT NULL,
    previous_intake_notes_snapshot TEXT,
    event_type TEXT NOT NULL
        CHECK (
            event_type IN (
                'case_created', 'intake_updated', 'patient_linked',
                'migration_baseline'
            )
        ),
    change_reason TEXT,
    record_origin TEXT NOT NULL
        CHECK (record_origin IN ('application_event', 'migration_baseline')),
    event_at TEXT
        CHECK (
            event_at IS NULL
            OR (
                event_at GLOB '????-??-??T??:??:??*Z'
                AND julianday(event_at) IS NOT NULL
                AND strftime('%Y-%m-%dT%H:%M:%S', event_at)
                    = substr(event_at, 1, 19)
            )
        ),
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            recorded_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(recorded_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', recorded_at)
                = substr(recorded_at, 1, 19)
        ),
    actor_user_id INTEGER
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    audit_log_id INTEGER UNIQUE
        REFERENCES audit_logs(audit_log_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (
        (
            record_origin = 'application_event'
            AND event_type <> 'migration_baseline'
            AND event_at IS NOT NULL
            AND actor_user_id IS NOT NULL
            AND audit_log_id IS NOT NULL
            AND (
                (
                    event_type = 'case_created'
                    AND previous_case_number_snapshot IS NULL
                    AND previous_patient_id_snapshot IS NULL
                    AND previous_intake_user_id_snapshot IS NULL
                    AND previous_arrival_at_snapshot IS NULL
                    AND previous_intake_notes_snapshot IS NULL
                )
                OR
                (
                    event_type IN ('intake_updated', 'patient_linked')
                    AND previous_case_number_snapshot IS NOT NULL
                    AND previous_intake_user_id_snapshot IS NOT NULL
                    AND previous_arrival_at_snapshot IS NOT NULL
                    AND previous_case_number_snapshot = case_number_snapshot
                    AND previous_intake_user_id_snapshot = intake_user_id_snapshot
                    AND previous_arrival_at_snapshot = arrival_at_snapshot
                    AND previous_intake_notes_snapshot IS NOT NULL
                    AND (
                        previous_patient_id_snapshot IS NOT patient_id_snapshot
                        OR previous_intake_notes_snapshot
                            IS NOT intake_notes_snapshot
                    )
                    AND change_reason IS NOT NULL
                    AND length(trim(change_reason)) > 0
                )
            )
        )
        OR
        (
            record_origin = 'migration_baseline'
            AND event_type = 'migration_baseline'
            AND event_at IS NULL
            AND actor_user_id IS NULL
            AND audit_log_id IS NULL
            AND previous_case_number_snapshot IS NULL
            AND previous_patient_id_snapshot IS NULL
            AND previous_intake_user_id_snapshot IS NULL
            AND previous_arrival_at_snapshot IS NULL
            AND previous_intake_notes_snapshot IS NULL
            AND change_reason IS NULL
        )
    ),
    UNIQUE (emergency_case_id, version_no)
);

CREATE TABLE emergency_closure_versions (
    closure_version_id INTEGER PRIMARY KEY,
    emergency_case_id INTEGER NOT NULL
        REFERENCES emergency_cases(emergency_case_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    closure_cycle INTEGER NOT NULL CHECK (closure_cycle > 0),
    version_no INTEGER NOT NULL CHECK (version_no > 0),
    closure_type TEXT NOT NULL
        CHECK (closure_type IN ('closed', 'corrected', 'migration_baseline')),
    closed_at_snapshot TEXT NOT NULL
        CHECK (
            closed_at_snapshot GLOB '????-??-??T??:??:??*Z'
            AND julianday(closed_at_snapshot) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', closed_at_snapshot)
                = substr(closed_at_snapshot, 1, 19)
        ),
    closed_by_user_id INTEGER
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    closure_summary TEXT,
    supersedes_version_id INTEGER,
    correction_reason TEXT,
    record_origin TEXT NOT NULL
        CHECK (record_origin IN ('application_event', 'migration_baseline')),
    event_at TEXT
        CHECK (
            event_at IS NULL
            OR (
                event_at GLOB '????-??-??T??:??:??*Z'
                AND julianday(event_at) IS NOT NULL
                AND strftime('%Y-%m-%dT%H:%M:%S', event_at)
                    = substr(event_at, 1, 19)
            )
        ),
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            recorded_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(recorded_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', recorded_at)
                = substr(recorded_at, 1, 19)
        ),
    actor_user_id INTEGER
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    audit_log_id INTEGER UNIQUE
        REFERENCES audit_logs(audit_log_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (
        (
            record_origin = 'application_event'
            AND closure_type IN ('closed', 'corrected')
            AND event_at IS NOT NULL
            AND actor_user_id IS NOT NULL
            AND audit_log_id IS NOT NULL
            AND closed_by_user_id IS NOT NULL
            AND closure_summary IS NOT NULL
            AND length(trim(closure_summary)) > 0
            AND (
                (closure_type = 'closed' AND supersedes_version_id IS NULL)
                OR
                (
                    closure_type = 'corrected'
                    AND supersedes_version_id IS NOT NULL
                    AND correction_reason IS NOT NULL
                    AND length(trim(correction_reason)) > 0
                )
            )
        )
        OR
        (
            record_origin = 'migration_baseline'
            AND closure_type = 'migration_baseline'
            AND event_at IS NULL
            AND actor_user_id IS NULL
            AND audit_log_id IS NULL
            AND closed_by_user_id IS NULL
            AND supersedes_version_id IS NULL
            AND correction_reason IS NULL
        )
    ),
    UNIQUE (emergency_case_id, closure_cycle, version_no),
    UNIQUE (emergency_case_id, closure_cycle, closure_version_id),
    FOREIGN KEY (emergency_case_id, closure_cycle, supersedes_version_id)
        REFERENCES emergency_closure_versions(
            emergency_case_id, closure_cycle, closure_version_id
        )
        ON DELETE RESTRICT ON UPDATE RESTRICT
);

CREATE INDEX idx_emergency_assignment_case_sequence
    ON emergency_doctor_assignments(emergency_case_id, sequence_no);
CREATE INDEX idx_emergency_assignment_new_doctor
    ON emergency_doctor_assignments(new_doctor_id, emergency_case_id);
CREATE INDEX idx_emergency_triage_case_sequence
    ON emergency_triage_history(emergency_case_id, sequence_no);
CREATE INDEX idx_emergency_outcome_case_version
    ON emergency_outcome_versions(emergency_case_id, version_no DESC);
CREATE INDEX idx_emergency_status_case_sequence
    ON emergency_status_history(emergency_case_id, sequence_no);
CREATE INDEX idx_emergency_status_value
    ON emergency_status_history(new_status, event_at);
CREATE INDEX idx_emergency_intake_case_version
    ON emergency_intake_history(emergency_case_id, version_no DESC);
CREATE INDEX idx_emergency_intake_patient
    ON emergency_intake_history(patient_id_snapshot, emergency_case_id);
CREATE INDEX idx_emergency_closure_case_version
    ON emergency_closure_versions(
        emergency_case_id, closure_cycle, version_no DESC
    );

CREATE TRIGGER emergency_doctor_assignment_guard
BEFORE INSERT ON emergency_doctor_assignments
FOR EACH ROW
WHEN NEW.record_origin = 'application_event'
BEGIN
    SELECT RAISE(ABORT, 'Emergency assignment must replace the current doctor.')
    WHERE NOT EXISTS (
        SELECT 1
        FROM emergency_cases AS emergency_case
        WHERE emergency_case.emergency_case_id = NEW.emergency_case_id
            AND emergency_case.assigned_doctor_id IS NEW.previous_doctor_id
    );
    SELECT RAISE(ABORT, 'The replacement emergency doctor must be active.')
    WHERE NOT EXISTS (
        SELECT 1
        FROM doctors
        WHERE doctor_id = NEW.new_doctor_id AND is_active = 1
    );
    SELECT RAISE(ABORT, 'Emergency assignment must be the next event.')
    WHERE NEW.sequence_no <> (
        SELECT COALESCE(MAX(sequence_no), 0) + 1
        FROM emergency_doctor_assignments
        WHERE emergency_case_id = NEW.emergency_case_id
    );
    SELECT RAISE(ABORT, 'Only active Admin or Receptionist users may assign doctors.')
    WHERE NOT EXISTS (
        SELECT 1
        FROM users AS actor
        JOIN audit_logs AS audit_log
            ON audit_log.audit_log_id = NEW.audit_log_id
        WHERE actor.user_id = NEW.actor_user_id
            AND actor.is_active = 1
            AND actor.role IN ('Admin', 'Receptionist')
            AND audit_log.user_id = NEW.actor_user_id
            AND audit_log.actor_type = 'user'
    );
END;

CREATE TRIGGER emergency_doctor_assignment_updates_case
AFTER INSERT ON emergency_doctor_assignments
FOR EACH ROW
WHEN NEW.record_origin = 'application_event'
BEGIN
    UPDATE emergency_cases
    SET assigned_doctor_id = NEW.new_doctor_id,
        updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE emergency_case_id = NEW.emergency_case_id;
END;

CREATE TRIGGER emergency_case_assignment_requires_history
BEFORE UPDATE OF assigned_doctor_id ON emergency_cases
FOR EACH ROW
WHEN NEW.assigned_doctor_id IS NOT OLD.assigned_doctor_id
    AND NOT EXISTS (
        SELECT 1
        FROM emergency_doctor_assignments AS assignment_event
        WHERE assignment_event.emergency_case_id = OLD.emergency_case_id
            AND assignment_event.previous_doctor_id IS OLD.assigned_doctor_id
            AND assignment_event.new_doctor_id IS NEW.assigned_doctor_id
            AND assignment_event.record_origin = 'application_event'
            AND assignment_event.sequence_no = (
                SELECT MAX(latest.sequence_no)
                FROM emergency_doctor_assignments AS latest
                WHERE latest.emergency_case_id = OLD.emergency_case_id
            )
    )
BEGIN
    SELECT RAISE(ABORT, 'Emergency doctor changes require an assignment history event.');
END;

CREATE TRIGGER emergency_triage_actor_guard
BEFORE INSERT ON emergency_triage_history
FOR EACH ROW
WHEN NEW.record_origin = 'application_event'
BEGIN
    SELECT RAISE(ABORT, 'Only the active doctor assigned to an open case may change triage.')
    WHERE NOT EXISTS (
        SELECT 1
        FROM emergency_cases AS emergency_case
        JOIN doctors AS doctor
            ON doctor.doctor_id = emergency_case.assigned_doctor_id
        JOIN users AS actor
            ON actor.user_id = NEW.actor_user_id
        JOIN audit_logs AS audit_log
            ON audit_log.audit_log_id = NEW.audit_log_id
        WHERE emergency_case.emergency_case_id = NEW.emergency_case_id
            AND emergency_case.closed_at IS NULL
            AND emergency_case.status IN ('Open', 'In Treatment')
            AND emergency_case.triage_category
                IS NEW.previous_triage_category
            AND NEW.sequence_no = (
                SELECT COALESCE(MAX(sequence_no), 0) + 1
                FROM emergency_triage_history
                WHERE emergency_case_id = NEW.emergency_case_id
            )
            AND doctor.is_active = 1
            AND doctor.user_id = actor.user_id
            AND actor.role = 'Doctor'
            AND actor.is_active = 1
            AND audit_log.user_id = NEW.actor_user_id
            AND audit_log.actor_type = 'user'
    );
END;

CREATE TRIGGER emergency_triage_history_updates_case
AFTER INSERT ON emergency_triage_history
FOR EACH ROW
WHEN NEW.record_origin = 'application_event'
BEGIN
    UPDATE emergency_cases
    SET triage_category = NEW.new_triage_category,
        updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE emergency_case_id = NEW.emergency_case_id;
END;

CREATE TRIGGER emergency_case_triage_requires_history
BEFORE UPDATE OF triage_category ON emergency_cases
FOR EACH ROW
WHEN NEW.triage_category IS NOT OLD.triage_category
    AND NOT EXISTS (
        SELECT 1
        FROM emergency_triage_history AS triage_event
        WHERE triage_event.emergency_case_id = OLD.emergency_case_id
            AND triage_event.previous_triage_category IS OLD.triage_category
            AND triage_event.new_triage_category IS NEW.triage_category
            AND triage_event.record_origin = 'application_event'
            AND triage_event.sequence_no = (
                SELECT MAX(latest.sequence_no)
                FROM emergency_triage_history AS latest
                WHERE latest.emergency_case_id = OLD.emergency_case_id
            )
    )
BEGIN
    SELECT RAISE(ABORT, 'Emergency triage changes require a new history event.');
END;

CREATE TRIGGER emergency_outcome_actor_guard
BEFORE INSERT ON emergency_outcome_versions
FOR EACH ROW
WHEN NEW.record_origin = 'application_event'
BEGIN
    SELECT RAISE(ABORT, 'Only the active doctor assigned to the case may update its outcome.')
    WHERE NOT EXISTS (
        SELECT 1
        FROM emergency_cases AS emergency_case
        JOIN doctors AS doctor
            ON doctor.doctor_id = emergency_case.assigned_doctor_id
        JOIN users AS actor
            ON actor.user_id = NEW.actor_user_id
        JOIN audit_logs AS audit_log
            ON audit_log.audit_log_id = NEW.audit_log_id
        WHERE emergency_case.emergency_case_id = NEW.emergency_case_id
            AND emergency_case.status IN ('Open', 'In Treatment')
            AND emergency_case.closed_at IS NULL
            AND doctor.is_active = 1
            AND doctor.user_id = actor.user_id
            AND actor.role = 'Doctor'
            AND actor.is_active = 1
            AND audit_log.user_id = NEW.actor_user_id
            AND audit_log.actor_type = 'user'
    );
    SELECT RAISE(ABORT, 'Outcome versions must append in order.')
    WHERE NEW.version_no <> (
        SELECT COALESCE(MAX(version_no), 0) + 1
        FROM emergency_outcome_versions
        WHERE emergency_case_id = NEW.emergency_case_id
    )
    OR NEW.supersedes_version_id IS NOT (
        SELECT outcome_version_id
        FROM emergency_outcome_versions
        WHERE emergency_case_id = NEW.emergency_case_id
        ORDER BY version_no DESC
        LIMIT 1
    );
END;

CREATE TRIGGER emergency_closure_version_guard
BEFORE INSERT ON emergency_closure_versions
FOR EACH ROW
WHEN NEW.record_origin = 'application_event'
BEGIN
    SELECT RAISE(ABORT, 'Only the current active doctor may close or correct a case.')
    WHERE NOT EXISTS (
        SELECT 1
        FROM emergency_cases AS emergency_case
        JOIN doctors AS doctor
            ON doctor.doctor_id = emergency_case.assigned_doctor_id
        JOIN users AS actor
            ON actor.user_id = NEW.actor_user_id
        JOIN audit_logs AS audit_log
            ON audit_log.audit_log_id = NEW.audit_log_id
        WHERE emergency_case.emergency_case_id = NEW.emergency_case_id
            AND doctor.is_active = 1
            AND doctor.user_id = actor.user_id
            AND actor.role = 'Doctor'
            AND actor.is_active = 1
            AND (
                (
                    NEW.closure_type = 'closed'
                    AND NEW.closed_by_user_id = NEW.actor_user_id
                )
                OR (
                    NEW.closure_type = 'corrected'
                    AND EXISTS (
                        SELECT 1
                        FROM emergency_closure_versions AS previous_version
                        WHERE previous_version.closure_version_id =
                            NEW.supersedes_version_id
                            AND previous_version.emergency_case_id =
                                NEW.emergency_case_id
                            AND previous_version.closed_by_user_id
                                IS NEW.closed_by_user_id
                            AND previous_version.closed_at_snapshot =
                                NEW.closed_at_snapshot
                    )
                )
            )
            AND audit_log.user_id = NEW.actor_user_id
            AND audit_log.actor_type = 'user'
    );
    SELECT RAISE(ABORT, 'Closure timestamp must be after arrival and match the event.')
    WHERE julianday(NEW.closed_at_snapshot) < (
        SELECT julianday(arrival_at)
        FROM emergency_cases
        WHERE emergency_case_id = NEW.emergency_case_id
    )
    OR (
        NEW.closure_type = 'closed'
        AND NEW.event_at IS NOT NEW.closed_at_snapshot
    );
    SELECT RAISE(ABORT, 'Initial closure requires an open In Treatment case.')
    WHERE NEW.closure_type = 'closed'
        AND NOT EXISTS (
            SELECT 1
            FROM emergency_cases AS emergency_case
            WHERE emergency_case.emergency_case_id = NEW.emergency_case_id
                AND emergency_case.status = 'In Treatment'
                AND emergency_case.closed_at IS NULL
        );
    SELECT RAISE(ABORT, 'Closure cycle or version is not the next value.')
    WHERE NEW.closure_type = 'closed'
        AND (
            NEW.closure_cycle <> (
                SELECT COALESCE(MAX(closure_cycle), 0) + 1
                FROM emergency_closure_versions
                WHERE emergency_case_id = NEW.emergency_case_id
            )
            OR NEW.version_no <> 1
        );
    SELECT RAISE(ABORT, 'Closure correction requires an open case after Admin reopen.')
    WHERE NEW.closure_type = 'corrected'
        AND NOT EXISTS (
            SELECT 1
            FROM emergency_cases AS emergency_case
            JOIN emergency_status_history AS reopened
                ON reopened.emergency_case_id = emergency_case.emergency_case_id
            JOIN users AS reopening_admin
                ON reopening_admin.user_id = reopened.actor_user_id
            WHERE emergency_case.emergency_case_id = NEW.emergency_case_id
                AND emergency_case.status IN ('Open', 'In Treatment')
                AND emergency_case.closed_at IS NULL
                AND reopened.transition_type = 'reopened'
                AND reopening_admin.role = 'Admin'
                AND reopening_admin.is_active = 1
                AND reopened.status_history_id = (
                    SELECT MAX(latest.status_history_id)
                    FROM emergency_status_history AS latest
                    WHERE latest.emergency_case_id = NEW.emergency_case_id
                        AND latest.transition_type = 'reopened'
                )
        );
    SELECT RAISE(ABORT, 'Closure correction must append to the latest closure version.')
    WHERE NEW.closure_type = 'corrected'
        AND (
            NEW.supersedes_version_id IS NOT (
                SELECT closure_version_id
                FROM emergency_closure_versions
                WHERE emergency_case_id = NEW.emergency_case_id
                ORDER BY closure_cycle DESC, version_no DESC
                LIMIT 1
            )
            OR NEW.closure_cycle <> (
                SELECT closure_cycle
                FROM emergency_closure_versions
                WHERE emergency_case_id = NEW.emergency_case_id
                ORDER BY closure_cycle DESC, version_no DESC
                LIMIT 1
            )
            OR NEW.version_no <> (
                SELECT COALESCE(MAX(version_no), 0) + 1
                FROM emergency_closure_versions
                WHERE emergency_case_id = NEW.emergency_case_id
                    AND closure_cycle = NEW.closure_cycle
            )
        );
END;

CREATE TRIGGER emergency_closure_version_updates_case
AFTER INSERT ON emergency_closure_versions
FOR EACH ROW
WHEN NEW.record_origin = 'application_event'
    AND NEW.closure_type = 'closed'
BEGIN
    UPDATE emergency_cases
    SET closed_at = NEW.closed_at_snapshot,
        updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE emergency_case_id = NEW.emergency_case_id;
END;

CREATE TRIGGER emergency_status_history_guard
BEFORE INSERT ON emergency_status_history
FOR EACH ROW
WHEN NEW.record_origin = 'application_event'
BEGIN
    SELECT RAISE(ABORT, 'Emergency status event must follow the current state.')
    WHERE NEW.sequence_no <> (
        SELECT COALESCE(MAX(sequence_no), 0) + 1
        FROM emergency_status_history
        WHERE emergency_case_id = NEW.emergency_case_id
    )
    OR (
        NEW.transition_type <> 'case_created'
        AND NEW.previous_status IS NOT (
            SELECT status
            FROM emergency_cases
            WHERE emergency_case_id = NEW.emergency_case_id
        )
    );
    SELECT RAISE(ABORT, 'Only Receptionist/Admin may register case creation.')
    WHERE NEW.transition_type = 'case_created'
        AND (
            NEW.previous_status IS NOT NULL
            OR NEW.new_status <> 'Open'
            OR NOT EXISTS (
                SELECT 1
                FROM emergency_cases AS emergency_case
                JOIN users AS actor
                    ON actor.user_id = NEW.actor_user_id
                JOIN audit_logs AS audit_log
                    ON audit_log.audit_log_id = NEW.audit_log_id
                WHERE emergency_case.emergency_case_id = NEW.emergency_case_id
                    AND emergency_case.status = NEW.new_status
                    AND actor.is_active = 1
                    AND actor.role IN ('Admin', 'Receptionist')
                    AND audit_log.user_id = NEW.actor_user_id
                    AND audit_log.actor_type = 'user'
            )
        );
    SELECT RAISE(ABORT, 'Status transition is not permitted for this actor or state.')
    WHERE NEW.transition_type = 'status_changed'
        AND NOT (
            (
                NEW.previous_status = 'Open'
                AND NEW.new_status = 'In Treatment'
            )
            OR (
                NEW.previous_status = 'In Treatment'
                AND NEW.new_status = 'Open'
                AND NEW.change_reason IS NOT NULL
                AND length(trim(NEW.change_reason)) > 0
                AND NEW.change_reason IS NOT NULL
                AND length(trim(NEW.change_reason)) > 0
            )
            OR (
                NEW.previous_status = 'In Treatment'
                AND NEW.new_status = 'Closed'
                AND EXISTS (
                    SELECT 1
                    FROM emergency_cases AS emergency_case
                    JOIN emergency_closure_versions AS closure
                        ON closure.emergency_case_id =
                            emergency_case.emergency_case_id
                    WHERE emergency_case.emergency_case_id = NEW.emergency_case_id
                        AND emergency_case.closed_at IS NOT NULL
                        AND closure.closure_type = 'closed'
                        AND closure.record_origin = 'application_event'
                        AND closure.closed_at_snapshot = emergency_case.closed_at
                        AND closure.actor_user_id = NEW.actor_user_id
                        AND closure.audit_log_id = NEW.audit_log_id
                        AND closure.closure_cycle = (
                            SELECT MAX(latest.closure_cycle)
                            FROM emergency_closure_versions AS latest
                            WHERE latest.emergency_case_id =
                                NEW.emergency_case_id
                        )
                )
            )
        )
        OR (
            NEW.transition_type = 'status_changed'
            AND NOT EXISTS (
                SELECT 1
                FROM emergency_cases AS emergency_case
                JOIN doctors AS doctor
                    ON doctor.doctor_id = emergency_case.assigned_doctor_id
                JOIN users AS actor
                    ON actor.user_id = NEW.actor_user_id
                JOIN audit_logs AS audit_log
                    ON audit_log.audit_log_id = NEW.audit_log_id
                WHERE emergency_case.emergency_case_id = NEW.emergency_case_id
                    AND doctor.is_active = 1
                    AND doctor.user_id = actor.user_id
                    AND actor.role = 'Doctor'
                    AND actor.is_active = 1
                    AND audit_log.user_id = NEW.actor_user_id
                    AND audit_log.actor_type = 'user'
            )
        );
    SELECT RAISE(ABORT, 'Reopening requires active Admin, a reason, and an active doctor.')
    WHERE NEW.transition_type = 'reopened'
        AND (
            NEW.previous_status <> 'Closed'
            OR NEW.new_status <> 'Open'
            OR NEW.change_reason IS NULL
            OR length(trim(NEW.change_reason)) = 0
            OR NOT EXISTS (
                SELECT 1
                FROM emergency_cases AS emergency_case
                JOIN doctors AS doctor
                    ON doctor.doctor_id = emergency_case.assigned_doctor_id
                JOIN users AS actor
                    ON actor.user_id = NEW.actor_user_id
                JOIN audit_logs AS audit_log
                    ON audit_log.audit_log_id = NEW.audit_log_id
                WHERE emergency_case.emergency_case_id = NEW.emergency_case_id
                    AND emergency_case.closed_at IS NOT NULL
                    AND doctor.is_active = 1
                    AND actor.role = 'Admin'
                    AND actor.is_active = 1
                    AND audit_log.user_id = NEW.actor_user_id
                    AND audit_log.actor_type = 'user'
            )
        );
END;

CREATE TRIGGER emergency_status_history_updates_case
AFTER INSERT ON emergency_status_history
FOR EACH ROW
WHEN NEW.record_origin = 'application_event'
    AND NEW.transition_type <> 'case_created'
BEGIN
    UPDATE emergency_cases
    SET status = NEW.new_status,
        closed_at = CASE
            WHEN NEW.transition_type = 'reopened' THEN NULL
            ELSE closed_at
        END,
        updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE emergency_case_id = NEW.emergency_case_id;
END;

CREATE TRIGGER emergency_case_status_requires_history
BEFORE UPDATE OF status ON emergency_cases
FOR EACH ROW
WHEN NEW.status IS NOT OLD.status
    AND NOT EXISTS (
        SELECT 1
        FROM emergency_status_history AS status_event
        WHERE status_event.emergency_case_id = OLD.emergency_case_id
            AND status_event.previous_status IS OLD.status
            AND status_event.new_status IS NEW.status
            AND status_event.record_origin = 'application_event'
            AND status_event.transition_type IN ('status_changed', 'reopened')
            AND status_event.sequence_no = (
                SELECT MAX(latest.sequence_no)
                FROM emergency_status_history AS latest
                WHERE latest.emergency_case_id = OLD.emergency_case_id
            )
    )
BEGIN
    SELECT RAISE(ABORT, 'Emergency status changes require a new status history event.');
END;

CREATE TRIGGER emergency_case_closed_at_requires_history
BEFORE UPDATE OF closed_at ON emergency_cases
FOR EACH ROW
WHEN NEW.closed_at IS NOT OLD.closed_at
    AND NOT (
        (
            OLD.closed_at IS NULL
            AND NEW.closed_at IS NOT NULL
            AND EXISTS (
                SELECT 1
                FROM emergency_closure_versions AS closure
                JOIN emergency_cases AS emergency_case
                    ON emergency_case.emergency_case_id =
                        closure.emergency_case_id
                WHERE closure.emergency_case_id = OLD.emergency_case_id
                    AND emergency_case.status = 'In Treatment'
                    AND emergency_case.closed_at IS NULL
                    AND closure.record_origin = 'application_event'
                    AND closure.closure_type = 'closed'
                    AND closure.closed_at_snapshot = NEW.closed_at
                    AND closure.actor_user_id = closure.closed_by_user_id
                    AND closure.closure_version_id = (
                        SELECT latest.closure_version_id
                        FROM emergency_closure_versions AS latest
                        WHERE latest.emergency_case_id = OLD.emergency_case_id
                        ORDER BY latest.closure_cycle DESC, latest.version_no DESC
                        LIMIT 1
                    )
            )
        )
        OR (
            OLD.closed_at IS NOT NULL
            AND NEW.closed_at IS NULL
            AND EXISTS (
                SELECT 1
                FROM emergency_status_history AS reopened
                WHERE reopened.emergency_case_id = OLD.emergency_case_id
                    AND reopened.transition_type = 'reopened'
                    AND reopened.record_origin = 'application_event'
                    AND reopened.previous_status = OLD.status
                    AND reopened.new_status = NEW.status
                    AND reopened.sequence_no = (
                        SELECT MAX(latest.sequence_no)
                        FROM emergency_status_history AS latest
                        WHERE latest.emergency_case_id = OLD.emergency_case_id
                    )
            )
        )
    )
BEGIN
    SELECT RAISE(ABORT, 'Emergency closure timestamps require a closure or reopen event.');
END;

CREATE TRIGGER emergency_intake_history_guard
BEFORE INSERT ON emergency_intake_history
FOR EACH ROW
WHEN NEW.record_origin = 'application_event'
BEGIN
    SELECT RAISE(ABORT, 'Only active Admin/Receptionist users may update intake.')
    WHERE NOT EXISTS (
        SELECT 1
        FROM users AS actor
        JOIN audit_logs AS audit_log
            ON audit_log.audit_log_id = NEW.audit_log_id
        WHERE actor.user_id = NEW.actor_user_id
            AND actor.role IN ('Admin', 'Receptionist')
            AND actor.is_active = 1
            AND audit_log.user_id = NEW.actor_user_id
            AND audit_log.actor_type = 'user'
    );
    SELECT RAISE(ABORT, 'Intake history must snapshot the current case values.')
    WHERE NEW.version_no <> (
        SELECT COALESCE(MAX(version_no), 0) + 1
        FROM emergency_intake_history
        WHERE emergency_case_id = NEW.emergency_case_id
    )
    OR NOT EXISTS (
        SELECT 1
        FROM emergency_cases AS emergency_case
        WHERE emergency_case.emergency_case_id = NEW.emergency_case_id
            AND emergency_case.case_number = NEW.case_number_snapshot
            AND emergency_case.arrival_at = NEW.arrival_at_snapshot
            AND emergency_case.intake_user_id = NEW.intake_user_id_snapshot
            AND (
                (
                    NEW.event_type = 'case_created'
                    AND NEW.patient_id_snapshot IS emergency_case.patient_id
                    AND NEW.intake_notes_snapshot = emergency_case.intake_notes
                )
                OR (
                    NEW.event_type IN ('intake_updated', 'patient_linked')
                    AND NEW.previous_case_number_snapshot =
                        emergency_case.case_number
                    AND NEW.previous_patient_id_snapshot
                        IS emergency_case.patient_id
                    AND NEW.previous_intake_user_id_snapshot =
                        emergency_case.intake_user_id
                    AND NEW.previous_arrival_at_snapshot =
                        emergency_case.arrival_at
                    AND NEW.previous_intake_notes_snapshot =
                        emergency_case.intake_notes
                    AND (
                        NEW.patient_id_snapshot IS NOT emergency_case.patient_id
                        OR NEW.intake_notes_snapshot <> emergency_case.intake_notes
                    )
                )
            )
    );
END;

CREATE TRIGGER emergency_intake_history_updates_case
AFTER INSERT ON emergency_intake_history
FOR EACH ROW
WHEN NEW.record_origin = 'application_event'
    AND NEW.event_type IN ('intake_updated', 'patient_linked')
BEGIN
    UPDATE emergency_cases
    SET patient_id = NEW.patient_id_snapshot,
        intake_notes = NEW.intake_notes_snapshot,
        updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE emergency_case_id = NEW.emergency_case_id;
END;

CREATE TRIGGER emergency_case_intake_requires_history
BEFORE UPDATE OF patient_id, intake_notes ON emergency_cases
FOR EACH ROW
WHEN (
        NEW.patient_id IS NOT OLD.patient_id
        OR NEW.intake_notes IS NOT OLD.intake_notes
    )
    AND NOT EXISTS (
        SELECT 1
        FROM emergency_intake_history AS intake_event
        WHERE intake_event.emergency_case_id = OLD.emergency_case_id
            AND intake_event.previous_patient_id_snapshot IS OLD.patient_id
            AND intake_event.patient_id_snapshot IS NEW.patient_id
            AND intake_event.previous_intake_notes_snapshot = OLD.intake_notes
            AND intake_event.intake_notes_snapshot = NEW.intake_notes
            AND intake_event.record_origin = 'application_event'
            AND intake_event.version_no = (
                SELECT MAX(latest.version_no)
                FROM emergency_intake_history AS latest
                WHERE latest.emergency_case_id = OLD.emergency_case_id
            )
    )
BEGIN
    SELECT RAISE(ABORT, 'Emergency intake changes require before/after history.');
END;

CREATE TRIGGER emergency_case_intake_identity_immutable
BEFORE UPDATE OF case_number, arrival_at, intake_user_id ON emergency_cases
FOR EACH ROW
WHEN NEW.case_number IS NOT OLD.case_number
    OR NEW.arrival_at IS NOT OLD.arrival_at
    OR NEW.intake_user_id IS NOT OLD.intake_user_id
BEGIN
    SELECT RAISE(ABORT, 'Emergency case number, arrival, and intake user are immutable.');
END;

CREATE TRIGGER emergency_doctor_assignments_no_update
BEFORE UPDATE ON emergency_doctor_assignments
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Emergency doctor assignment history is append-only.');
END;

CREATE TRIGGER emergency_doctor_assignments_no_delete
BEFORE DELETE ON emergency_doctor_assignments
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Emergency doctor assignment history is append-only.');
END;

CREATE TRIGGER emergency_triage_history_no_update
BEFORE UPDATE ON emergency_triage_history
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Emergency triage history is append-only.');
END;

CREATE TRIGGER emergency_triage_history_no_delete
BEFORE DELETE ON emergency_triage_history
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Emergency triage history is append-only.');
END;

CREATE TRIGGER emergency_outcome_versions_no_update
BEFORE UPDATE ON emergency_outcome_versions
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Emergency outcome versions are append-only.');
END;

CREATE TRIGGER emergency_outcome_versions_no_delete
BEFORE DELETE ON emergency_outcome_versions
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Emergency outcome versions are append-only.');
END;

CREATE TRIGGER emergency_status_history_no_update
BEFORE UPDATE ON emergency_status_history
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Emergency status history is append-only.');
END;

CREATE TRIGGER emergency_status_history_no_delete
BEFORE DELETE ON emergency_status_history
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Emergency status history is append-only.');
END;

CREATE TRIGGER emergency_intake_history_no_update
BEFORE UPDATE ON emergency_intake_history
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Emergency intake history is append-only.');
END;

CREATE TRIGGER emergency_intake_history_no_delete
BEFORE DELETE ON emergency_intake_history
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Emergency intake history is append-only.');
END;

CREATE TRIGGER emergency_closure_versions_no_update
BEFORE UPDATE ON emergency_closure_versions
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Emergency closure versions are append-only.');
END;

CREATE TRIGGER emergency_closure_versions_no_delete
BEFORE DELETE ON emergency_closure_versions
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Emergency closure versions are append-only.');
END;

INSERT INTO emergency_doctor_assignments (
    emergency_case_id, sequence_no, new_doctor_id, record_origin
)
SELECT emergency_case_id, 1, assigned_doctor_id, 'migration_baseline'
FROM emergency_cases;

INSERT INTO emergency_triage_history (
    emergency_case_id, sequence_no, new_triage_category, record_origin
)
SELECT emergency_case_id, 1, triage_category, 'migration_baseline'
FROM emergency_cases;

INSERT INTO emergency_status_history (
    emergency_case_id, sequence_no, new_status, transition_type, record_origin
)
SELECT
    emergency_case_id, 1, status, 'migration_baseline', 'migration_baseline'
FROM emergency_cases;

INSERT INTO emergency_intake_history (
    emergency_case_id, version_no, case_number_snapshot, patient_id_snapshot,
    intake_user_id_snapshot, arrival_at_snapshot, intake_notes_snapshot,
    event_type, record_origin
)
SELECT
    emergency_case_id, 1, case_number, patient_id, intake_user_id, arrival_at,
    intake_notes, 'migration_baseline', 'migration_baseline'
FROM emergency_cases;

INSERT INTO emergency_closure_versions (
    emergency_case_id, closure_cycle, version_no, closure_type,
    closed_at_snapshot, record_origin
)
SELECT
    emergency_case_id, 1, 1, 'migration_baseline', closed_at,
    'migration_baseline'
FROM emergency_cases
WHERE closed_at IS NOT NULL;
