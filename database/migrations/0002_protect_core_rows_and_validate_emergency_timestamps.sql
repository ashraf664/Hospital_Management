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

CREATE TABLE emergency_cases_v2 (
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

INSERT INTO emergency_cases_v2 (
    emergency_case_id, case_number, patient_id, assigned_doctor_id,
    intake_user_id, triage_category, status, arrival_at, closed_at,
    intake_notes, created_at, updated_at
)
SELECT
    emergency_case_id, case_number, patient_id, assigned_doctor_id,
    intake_user_id, triage_category, status, arrival_at, closed_at,
    intake_notes, created_at, updated_at
FROM emergency_cases;

DROP TRIGGER emergency_cases_no_delete;
DROP TABLE emergency_cases;
ALTER TABLE emergency_cases_v2 RENAME TO emergency_cases;

CREATE INDEX idx_emergency_patient_arrival
    ON emergency_cases(patient_id, arrival_at);
CREATE INDEX idx_emergency_doctor_status
    ON emergency_cases(assigned_doctor_id, status, arrival_at);
CREATE INDEX idx_emergency_status_arrival
    ON emergency_cases(status, arrival_at);

CREATE TRIGGER emergency_cases_no_delete
BEFORE DELETE ON emergency_cases
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Emergency cases cannot be permanently deleted.');
END;
