CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE
        CHECK (length(trim(username)) > 0),
    password_hash TEXT NOT NULL
        CHECK (length(trim(password_hash)) > 0),
    role TEXT NOT NULL
        CHECK (role IN ('Admin', 'Doctor', 'Receptionist')),
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            created_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(created_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', created_at) = substr(created_at, 1, 19)
        ),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            updated_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(updated_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', updated_at) = substr(updated_at, 1, 19)
        )
);

CREATE TABLE departments (
    department_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
        CHECK (length(trim(name)) > 0),
    description TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            created_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(created_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', created_at) = substr(created_at, 1, 19)
        ),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            updated_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(updated_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', updated_at) = substr(updated_at, 1, 19)
        )
);

CREATE TABLE doctors (
    doctor_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    department_id INTEGER NOT NULL
        REFERENCES departments(department_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    full_name TEXT NOT NULL
        CHECK (length(trim(full_name)) > 0),
    specialty TEXT NOT NULL
        CHECK (length(trim(specialty)) > 0),
    phone TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1))
);

CREATE TABLE patients (
    patient_id INTEGER PRIMARY KEY,
    patient_number TEXT NOT NULL UNIQUE
        CHECK (length(trim(patient_number)) > 0),
    full_name TEXT NOT NULL
        CHECK (length(trim(full_name)) > 0),
    date_of_birth TEXT NOT NULL
        CHECK (
            length(date_of_birth) = 10
            AND date_of_birth GLOB '????-??-??'
            AND julianday(date_of_birth) IS NOT NULL
            AND strftime('%Y-%m-%d', date_of_birth) = date_of_birth
        ),
    sex TEXT,
    phone TEXT,
    address TEXT,
    emergency_contact TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            created_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(created_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', created_at) = substr(created_at, 1, 19)
        ),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            updated_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(updated_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', updated_at) = substr(updated_at, 1, 19)
        )
);

CREATE TABLE doctor_patient_assignments (
    assignment_id INTEGER PRIMARY KEY,
    doctor_id INTEGER NOT NULL
        REFERENCES doctors(doctor_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    patient_id INTEGER NOT NULL
        REFERENCES patients(patient_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    assigned_by_user_id INTEGER NOT NULL
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    assigned_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            assigned_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(assigned_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', assigned_at) = substr(assigned_at, 1, 19)
        ),
    ended_by_user_id INTEGER
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    ended_at TEXT,
    end_reason TEXT,
    CHECK (
        (ended_at IS NULL AND ended_by_user_id IS NULL)
        OR
        (ended_at IS NOT NULL AND ended_by_user_id IS NOT NULL
            AND ended_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(ended_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', ended_at) = substr(ended_at, 1, 19)
            AND julianday(ended_at) >= julianday(assigned_at))
    )
);

CREATE TABLE appointments (
    appointment_id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL
        REFERENCES patients(patient_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    doctor_id INTEGER NOT NULL
        REFERENCES doctors(doctor_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    scheduled_start TEXT NOT NULL
        CHECK (
            scheduled_start GLOB '????-??-??T??:??:??*Z'
            AND julianday(scheduled_start) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', scheduled_start)
                = substr(scheduled_start, 1, 19)
        ),
    scheduled_end TEXT NOT NULL
        CHECK (
            scheduled_end GLOB '????-??-??T??:??:??*Z'
            AND julianday(scheduled_end) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', scheduled_end)
                = substr(scheduled_end, 1, 19)
            AND julianday(scheduled_end) > julianday(scheduled_start)
        ),
    status TEXT NOT NULL
        CHECK (length(trim(status)) > 0),
    reason TEXT,
    cancellation_reason TEXT,
    created_by_user_id INTEGER NOT NULL
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            created_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(created_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', created_at) = substr(created_at, 1, 19)
        ),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            updated_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(updated_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', updated_at) = substr(updated_at, 1, 19)
        )
);

CREATE TABLE emergency_cases (
    emergency_case_id INTEGER PRIMARY KEY,
    case_number TEXT NOT NULL UNIQUE
        CHECK (length(trim(case_number)) > 0),
    patient_id INTEGER
        REFERENCES patients(patient_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    assigned_doctor_id INTEGER
        REFERENCES doctors(doctor_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    intake_user_id INTEGER NOT NULL
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    triage_category TEXT,
    status TEXT NOT NULL
        CHECK (length(trim(status)) > 0),
    arrival_at TEXT NOT NULL
        CHECK (
            arrival_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(arrival_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', arrival_at) = substr(arrival_at, 1, 19)
        ),
    closed_at TEXT
        CHECK (
            closed_at IS NULL
            OR (
                closed_at GLOB '????-??-??T??:??:??*Z'
                AND julianday(closed_at) IS NOT NULL
                AND strftime('%Y-%m-%dT%H:%M:%S', closed_at) = substr(closed_at, 1, 19)
                AND julianday(closed_at) >= julianday(arrival_at)
            )
        ),
    intake_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            created_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(created_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', created_at) = substr(created_at, 1, 19)
        ),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            updated_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(updated_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', updated_at) = substr(updated_at, 1, 19)
        )
);

CREATE TABLE medical_records (
    medical_record_id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL
        REFERENCES patients(patient_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    doctor_id INTEGER NOT NULL
        REFERENCES doctors(doctor_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    appointment_id INTEGER
        REFERENCES appointments(appointment_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    record_type TEXT NOT NULL
        CHECK (length(trim(record_type)) > 0),
    record_content TEXT NOT NULL
        CHECK (length(trim(record_content)) > 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            created_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(created_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', created_at) = substr(created_at, 1, 19)
        ),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            updated_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(updated_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', updated_at) = substr(updated_at, 1, 19)
        ),
    is_amended INTEGER NOT NULL DEFAULT 0
        CHECK (is_amended IN (0, 1))
);

CREATE TABLE medical_record_versions (
    version_id INTEGER PRIMARY KEY,
    medical_record_id INTEGER NOT NULL
        REFERENCES medical_records(medical_record_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    patient_id_snapshot INTEGER NOT NULL
        REFERENCES patients(patient_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    doctor_id_snapshot INTEGER NOT NULL
        REFERENCES doctors(doctor_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    appointment_id_snapshot INTEGER
        REFERENCES appointments(appointment_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    record_type_snapshot TEXT NOT NULL
        CHECK (length(trim(record_type_snapshot)) > 0),
    record_content_snapshot TEXT NOT NULL
        CHECK (length(trim(record_content_snapshot)) > 0),
    created_at_snapshot TEXT NOT NULL
        CHECK (
            created_at_snapshot GLOB '????-??-??T??:??:??*Z'
            AND julianday(created_at_snapshot) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', created_at_snapshot)
                = substr(created_at_snapshot, 1, 19)
        ),
    updated_at_snapshot TEXT NOT NULL
        CHECK (
            updated_at_snapshot GLOB '????-??-??T??:??:??*Z'
            AND julianday(updated_at_snapshot) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', updated_at_snapshot)
                = substr(updated_at_snapshot, 1, 19)
        ),
    is_amended_snapshot INTEGER NOT NULL
        CHECK (is_amended_snapshot IN (0, 1)),
    modified_by_user_id INTEGER NOT NULL
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    modified_at TEXT NOT NULL
        CHECK (
            modified_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(modified_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', modified_at) = substr(modified_at, 1, 19)
        )
);

CREATE TABLE audit_logs (
    audit_log_id INTEGER PRIMARY KEY,
    user_id INTEGER
        REFERENCES users(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    actor_type TEXT NOT NULL
        CHECK (actor_type IN ('user', 'anonymous', 'first_admin_setup')),
    action TEXT NOT NULL
        CHECK (length(trim(action)) > 0),
    entity_type TEXT NOT NULL
        CHECK (length(trim(entity_type)) > 0),
    entity_id TEXT,
    occurred_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            occurred_at GLOB '????-??-??T??:??:??*Z'
            AND julianday(occurred_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%S', occurred_at) = substr(occurred_at, 1, 19)
        ),
    details TEXT NOT NULL DEFAULT '',
    CHECK (
        (actor_type = 'user' AND user_id IS NOT NULL)
        OR
        (actor_type IN ('anonymous', 'first_admin_setup') AND user_id IS NULL)
    )
);

CREATE INDEX idx_doctors_department_active
    ON doctors(department_id, is_active);

CREATE INDEX idx_patients_name_active
    ON patients(full_name, is_active);

CREATE INDEX idx_assignments_doctor_active
    ON doctor_patient_assignments(doctor_id, ended_at, patient_id);
CREATE INDEX idx_assignments_patient_active
    ON doctor_patient_assignments(patient_id, ended_at, doctor_id);
CREATE UNIQUE INDEX uq_assignments_active_pair
    ON doctor_patient_assignments(doctor_id, patient_id)
    WHERE ended_at IS NULL;

CREATE INDEX idx_appointments_patient_start
    ON appointments(patient_id, scheduled_start);
CREATE INDEX idx_appointments_doctor_start_status
    ON appointments(doctor_id, scheduled_start, status);
CREATE INDEX idx_appointments_status_start
    ON appointments(status, scheduled_start);

CREATE INDEX idx_emergency_patient_arrival
    ON emergency_cases(patient_id, arrival_at);
CREATE INDEX idx_emergency_doctor_status
    ON emergency_cases(assigned_doctor_id, status, arrival_at);
CREATE INDEX idx_emergency_status_arrival
    ON emergency_cases(status, arrival_at);

CREATE INDEX idx_medical_records_patient_created
    ON medical_records(patient_id, created_at);
CREATE INDEX idx_medical_records_doctor_created
    ON medical_records(doctor_id, created_at);
CREATE INDEX idx_medical_records_appointment
    ON medical_records(appointment_id);
CREATE INDEX idx_medical_record_versions_record_time
    ON medical_record_versions(medical_record_id, modified_at);

CREATE INDEX idx_audit_logs_occurred
    ON audit_logs(occurred_at);
CREATE INDEX idx_audit_logs_user_occurred
    ON audit_logs(user_id, occurred_at);
CREATE INDEX idx_audit_logs_entity
    ON audit_logs(entity_type, entity_id, occurred_at);

CREATE TRIGGER doctors_require_doctor_role_insert
BEFORE INSERT ON doctors
FOR EACH ROW
WHEN (SELECT role FROM users WHERE user_id = NEW.user_id) IS NOT 'Doctor'
BEGIN
    SELECT RAISE(ABORT, 'Doctor profile must reference a Doctor user.');
END;

CREATE TRIGGER doctors_require_doctor_role_update
BEFORE UPDATE OF user_id ON doctors
FOR EACH ROW
WHEN (SELECT role FROM users WHERE user_id = NEW.user_id) IS NOT 'Doctor'
BEGIN
    SELECT RAISE(ABORT, 'Doctor profile must reference a Doctor user.');
END;

CREATE TRIGGER users_keep_doctor_role_update
BEFORE UPDATE OF role ON users
FOR EACH ROW
WHEN NEW.role <> 'Doctor'
    AND EXISTS (SELECT 1 FROM doctors WHERE user_id = OLD.user_id)
BEGIN
    SELECT RAISE(ABORT, 'A user with a doctor profile must retain the Doctor role.');
END;

CREATE TRIGGER appointments_no_overlap_insert
BEFORE INSERT ON appointments
FOR EACH ROW
-- No appointment status vocabulary is imposed here. Only a status whose
-- trimmed, case-insensitive value is exactly "cancelled" releases the slot;
-- every other non-empty status is treated as occupying it.
WHEN lower(trim(NEW.status)) <> 'cancelled'
    AND EXISTS (
        SELECT 1
        FROM appointments AS existing
        WHERE existing.doctor_id = NEW.doctor_id
            AND lower(trim(existing.status)) <> 'cancelled'
            AND julianday(NEW.scheduled_start) < julianday(existing.scheduled_end)
            AND julianday(NEW.scheduled_end) > julianday(existing.scheduled_start)
    )
BEGIN
    SELECT RAISE(ABORT, 'Appointment overlaps an active appointment for this doctor.');
END;

CREATE TRIGGER appointments_no_overlap_update
BEFORE UPDATE OF doctor_id, scheduled_start, scheduled_end, status ON appointments
FOR EACH ROW
-- Keep the same "cancelled" comparison rule as the insert trigger.
WHEN lower(trim(NEW.status)) <> 'cancelled'
    AND EXISTS (
        SELECT 1
        FROM appointments AS existing
        WHERE existing.doctor_id = NEW.doctor_id
            AND existing.appointment_id <> OLD.appointment_id
            AND lower(trim(existing.status)) <> 'cancelled'
            AND julianday(NEW.scheduled_start) < julianday(existing.scheduled_end)
            AND julianday(NEW.scheduled_end) > julianday(existing.scheduled_start)
    )
BEGIN
    SELECT RAISE(ABORT, 'Appointment overlaps an active appointment for this doctor.');
END;

CREATE TRIGGER assignments_are_ended_once
BEFORE UPDATE ON doctor_patient_assignments
FOR EACH ROW
WHEN NEW.assignment_id <> OLD.assignment_id
    OR NEW.doctor_id <> OLD.doctor_id
    OR NEW.patient_id <> OLD.patient_id
    OR NEW.assigned_by_user_id <> OLD.assigned_by_user_id
    OR NEW.assigned_at <> OLD.assigned_at
    OR OLD.ended_at IS NOT NULL
    OR (NEW.ended_at IS NULL AND NEW.ended_by_user_id IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT, 'Care assignments are immutable except for ending once.');
END;

CREATE TRIGGER assignments_no_delete
BEFORE DELETE ON doctor_patient_assignments
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Care assignment history cannot be deleted.');
END;

CREATE TRIGGER emergency_cases_no_delete
BEFORE DELETE ON emergency_cases
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Emergency cases cannot be permanently deleted.');
END;

CREATE TRIGGER medical_records_no_delete
BEFORE DELETE ON medical_records
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Medical records cannot be permanently deleted.');
END;

CREATE TRIGGER patients_no_delete
BEFORE DELETE ON patients
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Patients must be deactivated, not permanently deleted.');
END;

CREATE TRIGGER doctors_no_delete
BEFORE DELETE ON doctors
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Doctors must be deactivated, not permanently deleted.');
END;

CREATE TRIGGER departments_no_delete
BEFORE DELETE ON departments
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Departments must be deactivated, not permanently deleted.');
END;

CREATE TRIGGER users_no_delete
BEFORE DELETE ON users
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Users must be deactivated, not permanently deleted.');
END;

-- MedicalRecordService must perform each record amendment explicitly inside
-- one IMMEDIATE transaction: read the current row, insert its complete
-- pre-change snapshot into medical_record_versions, insert the mandatory
-- audit event, update medical_records, then commit. Any failure rolls back
-- the snapshot, audit event, and record update together. No trigger imposes
-- this ordering; the Services layer owns and tests the workflow.
CREATE TRIGGER medical_record_versions_no_update
BEFORE UPDATE ON medical_record_versions
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Medical record versions are append-only.');
END;

CREATE TRIGGER medical_record_versions_no_delete
BEFORE DELETE ON medical_record_versions
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Medical record versions are append-only.');
END;

CREATE TRIGGER audit_logs_no_update
BEFORE UPDATE ON audit_logs
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Audit logs are append-only.');
END;

CREATE TRIGGER audit_logs_no_delete
BEFORE DELETE ON audit_logs
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Audit logs are append-only.');
END;
