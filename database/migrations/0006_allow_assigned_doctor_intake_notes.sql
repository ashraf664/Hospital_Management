DROP TRIGGER emergency_intake_history_guard;

CREATE TRIGGER emergency_intake_history_guard
BEFORE INSERT ON emergency_intake_history
FOR EACH ROW
WHEN NEW.record_origin = 'application_event'
BEGIN
    SELECT RAISE(ABORT, 'Only an authorized active user may update intake.')
    WHERE NOT EXISTS (
        SELECT 1
        FROM users AS actor
        JOIN audit_logs AS audit_log
            ON audit_log.audit_log_id = NEW.audit_log_id
        WHERE actor.user_id = NEW.actor_user_id
            AND actor.is_active = 1
            AND audit_log.user_id = NEW.actor_user_id
            AND audit_log.actor_type = 'user'
            AND (
                actor.role IN ('Admin', 'Receptionist')
                OR (
                    actor.role = 'Doctor'
                    AND NEW.event_type = 'intake_updated'
                    AND EXISTS (
                        SELECT 1
                        FROM emergency_cases AS emergency_case
                        JOIN doctors AS doctor
                            ON doctor.doctor_id =
                                emergency_case.assigned_doctor_id
                        WHERE emergency_case.emergency_case_id =
                                NEW.emergency_case_id
                            AND doctor.user_id = actor.user_id
                            AND doctor.is_active = 1
                            AND NEW.patient_id_snapshot
                                IS emergency_case.patient_id
                            AND NEW.intake_notes_snapshot <>
                                emergency_case.intake_notes
                    )
                )
            )
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
