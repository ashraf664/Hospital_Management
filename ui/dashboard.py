"""Role-specific dashboard content; authorization remains in Services."""

from dataclasses import dataclass

from models.enums import UserRole


@dataclass(frozen=True, slots=True)
class DashboardFeature:
    key: str
    title: str
    description: str
    available: bool = False


_ADMIN_FEATURES = (
    DashboardFeature(
        "manage_users",
        "Staff accounts",
        "Create staff accounts and assign ordinary roles.",
        available=True,
    ),
    DashboardFeature(
        "departments",
        "Departments",
        "Manage hospital departments.",
        available=True,
    ),
    DashboardFeature(
        "doctors",
        "Doctor directory",
        "Manage the doctor directory and department assignment.",
        available=True,
    ),
    DashboardFeature(
        "patients",
        "Patient demographics",
        "Manage patient identity and contact information only.",
        available=True,
    ),
    DashboardFeature(
        "appointments",
        "Appointments",
        "Manage appointment scheduling.",
        available=True,
    ),
    DashboardFeature(
        "emergency_intake",
        "Emergency intake",
        "Manage administrative intake details.",
        available=True,
    ),
    DashboardFeature(
        "audit",
        "Audit metadata",
        "Review security and administrative audit metadata.",
    ),
)

_DOCTOR_FEATURES = (
    DashboardFeature(
        "schedule",
        "My schedule",
        "View your own appointment schedule.",
        available=True,
    ),
    DashboardFeature(
        "doctor_profile",
        "My doctor profile",
        "View your own directory profile.",
        available=True,
    ),
    DashboardFeature(
        "patients",
        "Patients in my care",
        "Access only patients connected to your care responsibilities.",
        available=True,
    ),
    DashboardFeature(
        "medical_records",
        "Medical records",
        "View and update records within your authorized care scope.",
    ),
    DashboardFeature(
        "emergency_cases",
        "Assigned emergency cases",
        "View assigned cases and update their intake notes.",
        available=True,
    ),
)

_RECEPTIONIST_FEATURES = (
    DashboardFeature(
        "doctors",
        "Doctor directory",
        "Search the nonclinical doctor directory.",
        available=True,
    ),
    DashboardFeature(
        "patients",
        "Patient intake",
        "Manage demographic and contact information.",
        available=True,
    ),
    DashboardFeature(
        "appointments",
        "Appointments",
        "Schedule and manage appointments.",
        available=True,
    ),
    DashboardFeature(
        "emergency_intake",
        "Emergency intake",
        "Create cases and manage permitted intake information.",
        available=True,
    ),
)


def dashboard_features_for(role: UserRole) -> tuple[DashboardFeature, ...]:
    if role in {UserRole.OWNER, UserRole.ADMIN}:
        return _ADMIN_FEATURES
    if role is UserRole.DOCTOR:
        return _DOCTOR_FEATURES
    if role is UserRole.RECEPTIONIST:
        return _RECEPTIONIST_FEATURES
    raise ValueError(f"Unsupported user role: {role!r}")
