"""Tests for role-specific dashboard navigation content."""

import unittest

from models.enums import UserRole
from ui.dashboard import dashboard_features_for


class DashboardFeatureTests(unittest.TestCase):
    def test_owner_and_admin_only_see_nonclinical_administration_features(self) -> None:
        owner_features = dashboard_features_for(UserRole.OWNER)
        admin_features = dashboard_features_for(UserRole.ADMIN)

        self.assertEqual(owner_features, admin_features)
        self.assertIn("manage_users", {feature.key for feature in owner_features})
        self.assertNotIn(
            "medical_records",
            {feature.key for feature in owner_features},
        )
        self.assertNotIn(
            "emergency_cases",
            {feature.key for feature in owner_features},
        )

    def test_doctor_features_are_limited_to_care_scope(self) -> None:
        features = dashboard_features_for(UserRole.DOCTOR)
        keys = {feature.key for feature in features}

        self.assertEqual(
            keys,
            {
                "schedule",
                "doctor_profile",
                "patients",
                "medical_records",
                "emergency_cases",
            },
        )
        self.assertNotIn("manage_users", keys)
        self.assertNotIn("audit", keys)

    def test_receptionist_features_exclude_clinical_content(self) -> None:
        features = dashboard_features_for(UserRole.RECEPTIONIST)
        keys = {feature.key for feature in features}

        self.assertEqual(
            keys,
            {"doctors", "patients", "appointments", "emergency_intake"},
        )
        self.assertNotIn("medical_records", keys)
        self.assertNotIn("emergency_cases", keys)

    def test_connected_dashboard_modules_follow_role_matrix(self) -> None:
        expected = {
            UserRole.OWNER: {
                "manage_users",
                "departments",
                "doctors",
                "patients",
                "appointments",
                "emergency_intake",
            },
            UserRole.ADMIN: {
                "manage_users",
                "departments",
                "doctors",
                "patients",
                "appointments",
                "emergency_intake",
            },
            UserRole.DOCTOR: {
                "schedule",
                "doctor_profile",
                "patients",
                "emergency_cases",
            },
            UserRole.RECEPTIONIST: {
                "doctors",
                "patients",
                "appointments",
                "emergency_intake",
            },
        }
        for role in UserRole:
            with self.subTest(role=role):
                available = {
                    feature.key
                    for feature in dashboard_features_for(role)
                    if feature.available
                }
                self.assertEqual(available, expected[role])


if __name__ == "__main__":
    unittest.main()
