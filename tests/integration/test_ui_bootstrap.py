"""Integration tests for UI service composition and first-run flows."""

from pathlib import Path
import tempfile
import unittest

from models.enums import UserRole
from services.authorization_service import Permission
from ui.bootstrap import create_service_container


_OWNER_PASSWORD = "Synthetic Arabic Owner Passphrase 2026!"
_ADMIN_PASSWORD = "Synthetic Admin Passphrase 2026!"


class UIBootstrapIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "ui.db"
        self.addCleanup(self.temporary_directory.cleanup)
        self.services = create_service_container(self.database_path)
        self.addCleanup(self.services.close)

    def test_empty_database_enables_owner_setup_then_authentication(self) -> None:
        authentication = self.services.authentication
        self.assertTrue(authentication.first_owner_setup_available())

        owner_id = authentication.create_first_owner(
            "مالك-تجريبي",
            _OWNER_PASSWORD,
        )
        self.assertFalse(authentication.first_owner_setup_available())

        session = authentication.login("مالك-تجريبي", _OWNER_PASSWORD)
        self.assertEqual(session.user_id, owner_id)
        self.assertIs(session.role, UserRole.OWNER)
        self.services.authorization.require_permission(
            session.session_token,
            Permission.MANAGE_USERS,
        )
        authentication.logout(session.session_token)

    def test_staff_account_creation_flows_through_services(self) -> None:
        authentication = self.services.authentication
        owner_id = authentication.create_first_owner(
            "synthetic-owner",
            _OWNER_PASSWORD,
        )
        owner_session = authentication.login(
            "synthetic-owner",
            _OWNER_PASSWORD,
        )
        created = self.services.user_administration.create_user(
            owner_session.session_token,
            "استقبال-تجريبي",
            _ADMIN_PASSWORD,
            UserRole.RECEPTIONIST,
        )

        self.assertNotEqual(created.user_id, owner_id)
        staff_session = authentication.login(
            "استقبال-تجريبي",
            _ADMIN_PASSWORD,
        )
        self.assertIs(staff_session.role, UserRole.RECEPTIONIST)
        authentication.logout(staff_session.session_token)
        authentication.logout(owner_session.session_token)

    def test_first_owner_setup_is_not_available_after_accounts_exist(self) -> None:
        self.services.authentication.create_first_owner(
            "synthetic-owner",
            _OWNER_PASSWORD,
        )

        self.assertFalse(
            self.services.authentication.first_owner_setup_available()
        )


if __name__ == "__main__":
    unittest.main()
