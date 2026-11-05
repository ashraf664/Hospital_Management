"""Authorized patient-demographic workflows."""

from datetime import date
import sqlite3

from database.transaction_manager import TransactionManager
from models import AuditActorType, AuditLog, Patient, UserRole
from repositories.audit_log_repository import AuditLogRepository
from repositories.page import DEFAULT_PAGE_LIMIT, Page
from repositories.patient_repository import PatientRepository
from services.authorization_service import AuthorizationService, Permission


class PatientService:
    """Handle demographics only and enforce doctor care scope in Services."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        authorization_service: AuthorizationService,
    ) -> None:
        self.transaction_manager = TransactionManager(connection)
        self.authorization_service = authorization_service
        self.patient_repository = PatientRepository(connection)
        self.audit_repository = AuditLogRepository(connection)

    def create(
        self,
        session_token: str,
        patient_number: str,
        full_name: str,
        date_of_birth: str,
        *,
        sex: str | None = None,
        phone: str | None = None,
        address: str | None = None,
        emergency_contact: str | None = None,
    ) -> Patient:
        normalized_number = self._required_text(patient_number, "patient_number")
        normalized_name = self._required_text(full_name, "full_name")
        normalized_birth = self._validate_birth_date(date_of_birth)
        normalized_sex = self._optional_text(sex, "sex")
        normalized_phone = self._optional_text(phone, "phone")
        normalized_address = self._optional_text(address, "address")
        normalized_contact = self._optional_text(
            emergency_contact,
            "emergency_contact",
        )

        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.CREATE_PATIENT,
            )
            created = self.patient_repository.create(
                Patient(
                    patient_number=normalized_number,
                    full_name=normalized_name,
                    date_of_birth=normalized_birth,
                    sex=normalized_sex,
                    phone=normalized_phone,
                    address=normalized_address,
                    emergency_contact=normalized_contact,
                )
            )
            self._audit(actor.user_id, "patient_created", created.patient_id)
            return created

    def update_demographics(
        self,
        session_token: str,
        patient_id: int,
        full_name: str,
        date_of_birth: str,
        *,
        sex: str | None = None,
        phone: str | None = None,
        address: str | None = None,
        emergency_contact: str | None = None,
    ) -> Patient | None:
        self._validate_id(patient_id, "patient_id")
        normalized_name = self._required_text(full_name, "full_name")
        normalized_birth = self._validate_birth_date(date_of_birth)
        normalized_sex = self._optional_text(sex, "sex")
        normalized_phone = self._optional_text(phone, "phone")
        normalized_address = self._optional_text(address, "address")
        normalized_contact = self._optional_text(
            emergency_contact,
            "emergency_contact",
        )

        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_PATIENT_DEMOGRAPHICS,
            )
            self.authorization_service.require_patient_access(
                session_token,
                patient_id,
                clinical=False,
                write=True,
            )
            updated = self.patient_repository.update_demographics(
                patient_id,
                normalized_name,
                normalized_birth,
                normalized_sex,
                normalized_phone,
                normalized_address,
                normalized_contact,
            )
            if updated is not None:
                self._audit(actor.user_id, "patient_demographics_updated", patient_id)
            return updated

    def set_active(
        self,
        session_token: str,
        patient_id: int,
        is_active: bool,
    ) -> Patient | None:
        self._validate_id(patient_id, "patient_id")
        if type(is_active) is not bool:
            raise TypeError("is_active must be a boolean.")
        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_PATIENT_DEMOGRAPHICS,
            )
            self.authorization_service.require_patient_access(
                session_token,
                patient_id,
                clinical=False,
                write=True,
            )
            updated = (
                self.patient_repository.activate(patient_id)
                if is_active
                else self.patient_repository.deactivate(patient_id)
            )
            if updated is not None:
                action = "patient_activated" if is_active else "patient_deactivated"
                self._audit(actor.user_id, action, patient_id)
            return updated

    def find_by_id(
        self,
        session_token: str,
        patient_id: int,
    ) -> Patient | None:
        self._validate_id(patient_id, "patient_id")
        with self.transaction_manager.transaction():
            self.authorization_service.require_patient_access(
                session_token,
                patient_id,
                clinical=False,
            )
            return self.patient_repository.find_by_id(patient_id)

    def search(
        self,
        session_token: str,
        *,
        patient_number: str | None = None,
        full_name: str | None = None,
        phone: str | None = None,
        query: str | None = None,
        is_active: bool | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> Page[Patient]:
        normalized_number = (
            self._optional_text(patient_number, "patient_number")
            if patient_number is not None
            else None
        )
        normalized_name = (
            self._optional_text(full_name, "full_name")
            if full_name is not None
            else None
        )
        normalized_phone = (
            self._optional_text(phone, "phone") if phone is not None else None
        )
        normalized_query = (
            self._optional_text(query, "query") if query is not None else None
        )
        if is_active is not None and type(is_active) is not bool:
            raise TypeError("is_active must be a boolean or None.")

        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_PATIENT_DEMOGRAPHICS,
            )
            doctor_id = None
            if actor.role is UserRole.DOCTOR:
                doctor_id = (
                    self.authorization_service.authorization_repository
                    .doctor_id_for_user(actor.user_id)
                )
                if doctor_id is None:
                    raise PermissionError(
                        "A Doctor directory profile is required for patient search."
                    )
                if not self.authorization_service.authorization_repository.doctor_is_active(
                    doctor_id
                ):
                    raise PermissionError(
                        "An active Doctor directory profile is required "
                        "for patient search."
                    )
            return self.patient_repository.search(
                patient_number=normalized_number,
                full_name=normalized_name,
                phone=normalized_phone,
                query=normalized_query,
                is_active=is_active,
                doctor_id=doctor_id,
                limit=limit,
                offset=offset,
            )

    def _audit(self, user_id: int, action: str, patient_id: int | None) -> None:
        self.audit_repository.create(
            AuditLog(
                actor_type=AuditActorType.USER,
                action=action,
                entity_type="patient",
                user_id=user_id,
                entity_id=str(patient_id) if patient_id is not None else None,
            )
        )

    @staticmethod
    def _required_text(value: str, field_name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string.")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} must not be empty.")
        return normalized

    @classmethod
    def _optional_text(cls, value: str | None, field_name: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string or None.")
        normalized = value.strip()
        return normalized or None

    @classmethod
    def _validate_birth_date(cls, value: str) -> str:
        normalized = cls._required_text(value, "date_of_birth")
        try:
            parsed = date.fromisoformat(normalized)
        except ValueError as error:
            raise ValueError("date_of_birth must use YYYY-MM-DD format.") from error
        if parsed.isoformat() != normalized:
            raise ValueError("date_of_birth must use YYYY-MM-DD format.")
        if parsed > date.today():
            raise ValueError("date_of_birth cannot be in the future.")
        return normalized

    @staticmethod
    def _validate_id(value: int, field_name: str) -> None:
        if type(value) is not int or value < 1:
            raise ValueError(f"{field_name} must be a positive integer.")
