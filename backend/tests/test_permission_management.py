import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "permission-tests-secret")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import create_auth_tables  # noqa: E402
from models import Base, User, UserPermissionAudit  # noqa: E402
from permissions import (  # noqa: E402
    ALL_PERMISSIONS,
    DEFAULT_USER_PERMISSIONS,
    get_user_permissions,
)
from repositories import UserRepository  # noqa: E402
from routes.users import (  # noqa: E402
    UserCreate,
    UserUpdate,
    create_user,
    get_profile,
    list_users,
    update_user,
)


class PermissionManagementTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_user(self, username="teacher", school="school-a", role="user", permissions=None):
        user = User(
            username=username,
            password_hash="hash",
            institucio=school,
            role=role,
            active=True,
            permissions=permissions,
        )
        self.db.add(user)
        self.db.commit()
        return user

    def test_legacy_null_empty_and_corrupt_permissions_are_distinct(self):
        legacy = self.add_user("legacy")
        empty = self.add_user("empty", permissions="[]")
        legacy_export = self.add_user("legacy-export", permissions='["exports.download"]')

        self.assertEqual(get_user_permissions(legacy), list(DEFAULT_USER_PERMISSIONS))
        self.assertEqual(get_user_permissions(empty), [])
        self.assertEqual(
            get_user_permissions(legacy_export), ["workbench.view", "exports.download"]
        )
        for username, raw in (("broken-json", "{"), ("non-string", "[1]")):
            with self.subTest(raw=raw), self.assertLogs("permissions", level="ERROR"):
                self.assertEqual(get_user_permissions(self.add_user(username, permissions=raw)), [])

    def test_admin_roles_always_have_every_permission(self):
        for role in ("admin", "super_admin"):
            with self.subTest(role=role):
                user = SimpleNamespace(role=role, permissions="{", username=role, id=1)
                self.assertEqual(get_user_permissions(user), list(ALL_PERMISSIONS))

    def test_create_list_and_profile_include_permissions(self):
        admin = self.add_user("admin", role="admin")
        with (
            patch("config.settings.Config.get_institucions_disponibles", return_value=["school-a"]),
            patch("routes.users.get_engine_for_institucio", return_value=self.engine),
            patch("routes.users.hash_password", return_value="hash"),
        ):
            created = create_user(
                UserCreate(username="no-access", password="password", permissions=[]),
                admin,
                self.db,
            )
            listed = list_users(admin, self.db)

        self.assertEqual(created.permissions, [])
        self.assertEqual(next(row.permissions for row in listed if row.id == created.id), [])
        profile = get_profile(self.db.get(User, created.id))
        self.assertEqual(profile["permissions"], [])

    def test_unknown_or_invalid_permission_combination_is_rejected(self):
        admin = self.add_user("admin", role="admin")
        target = self.add_user()
        for permissions in (["users.manage"], ["absence.create"], ["exports.download"]):
            with self.subTest(permissions=permissions), self.assertRaises(HTTPException) as raised:
                update_user(target.id, UserUpdate(permissions=permissions), admin, self.db)
            self.assertEqual(raised.exception.status_code, 400)

    def test_school_boundary_is_preserved(self):
        admin = self.add_user("admin", role="admin")
        target = self.add_user("other", school="school-b")

        with self.assertRaises(HTTPException) as raised:
            update_user(target.id, UserUpdate(permissions=[]), admin, self.db)

        self.assertEqual(raised.exception.status_code, 403)
        self.assertIsNone(target.permissions)

    def test_permission_update_writes_audit_in_same_auth_session(self):
        admin = self.add_user("admin", role="admin")
        target = self.add_user()
        with patch("routes.users.get_engine_for_institucio", return_value=self.engine):
            response = update_user(
                target.id,
                UserUpdate(permissions=["records.view"]),
                admin,
                self.db,
            )

        audit = self.db.query(UserPermissionAudit).one()
        self.assertEqual(response.permissions, ["records.view"])
        self.assertEqual(audit.institucio, "school-a")
        self.assertEqual(audit.actor_username, "admin")
        self.assertEqual(audit.target_user_id, target.id)
        self.assertEqual(audit.target_username, target.username)
        self.assertEqual(json.loads(audit.permissions_before), list(DEFAULT_USER_PERMISSIONS))
        self.assertEqual(json.loads(audit.permissions_after), ["records.view"])
        self.assertIsNotNone(audit.created_at)

    def test_legacy_users_table_migration_adds_nullable_column(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR NOT NULL)"
            )
            connection.exec_driver_sql("INSERT INTO users (username) VALUES ('legacy')")

        with patch("database.AUTH_ENGINE", engine):
            create_auth_tables()

        with engine.connect() as connection:
            columns = {
                row[1]: row for row in connection.exec_driver_sql("PRAGMA table_info(users)")
            }
            tables = {
                row[0]
                for row in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            row = connection.exec_driver_sql(
                "SELECT permissions FROM users WHERE username = 'legacy'"
            ).one()
        self.assertIn("permissions", columns)
        self.assertIn("user_permission_audits", tables)
        self.assertIsNone(row[0])
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
