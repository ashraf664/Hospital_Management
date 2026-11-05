"""Create application services and their shared SQLite connection."""

from dataclasses import dataclass, field
from pathlib import Path
import sqlite3

from database.connection_manager import ConnectionManager
from database.database_initializer import DatabaseInitializer
from services import (
    AuthenticationService,
    AuthorizationService,
    AppointmentService,
    DepartmentService,
    DoctorService,
    EmergencyCaseService,
    PatientService,
    UserAdministrationService,
)


@dataclass(slots=True)
class ServiceContainer:
    authentication: AuthenticationService
    authorization: AuthorizationService
    user_administration: UserAdministrationService
    departments: DepartmentService
    doctors: DoctorService
    patients: PatientService
    appointments: AppointmentService
    emergency_cases: EmergencyCaseService
    _connection: sqlite3.Connection = field(repr=False)

    def close(self) -> None:
        self._connection.close()


def create_service_container(database_path: str | Path) -> ServiceContainer:
    """Initialize the current schema and wire services to one connection."""
    initializer = DatabaseInitializer(database_path)
    initializer.initialize()
    connection = ConnectionManager(database_path).connect()
    try:
        authentication = AuthenticationService(connection)
        authorization = AuthorizationService(
            connection,
            authentication.session_registry,
        )
        user_administration = UserAdministrationService(
            connection,
            authorization,
        )
        departments = DepartmentService(connection, authorization)
        doctors = DoctorService(connection, authorization)
        patients = PatientService(connection, authorization)
        appointments = AppointmentService(connection, authorization)
        emergency_cases = EmergencyCaseService(connection, authorization)
        return ServiceContainer(
            authentication=authentication,
            authorization=authorization,
            user_administration=user_administration,
            departments=departments,
            doctors=doctors,
            patients=patients,
            appointments=appointments,
            emergency_cases=emergency_cases,
            _connection=connection,
        )
    except BaseException:
        connection.close()
        raise
