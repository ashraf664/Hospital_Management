"""Enumerations for values explicitly constrained by the requirements."""

from enum import Enum


class UserRole(str, Enum):
    OWNER = "Owner"
    ADMIN = "Admin"
    DOCTOR = "Doctor"
    RECEPTIONIST = "Receptionist"


class AuditActorType(str, Enum):
    USER = "user"
    ANONYMOUS = "anonymous"
    FIRST_ADMIN_SETUP = "first_admin_setup"
