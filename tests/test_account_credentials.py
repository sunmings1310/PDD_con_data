from __future__ import annotations

import os
import unittest
from unittest.mock import patch

TEST_SERVER_ENV = {
    "APP_ENV": "test",
    "ORACLE_HOST": "127.0.0.1",
    "ORACLE_PORT": "1521",
    "ORACLE_SERVICE": "TEST_SERVICE",
    "ORACLE_USER": "TEST_USER",
    "ORACLE_PASSWORD": "test-only-password",
    "JWT_SECRET": "Test-only-JWT-secret-32-characters!",
}
for _key, _value in TEST_SERVER_ENV.items():
    os.environ.setdefault(_key, _value)

from server.init_rbac_schema import _bootstrap_admin_credentials  # noqa: E402


class AccountCredentialTest(unittest.TestCase):
    def test_bootstrap_admin_credentials_are_required(self):
        with patch.dict(os.environ, TEST_SERVER_ENV, clear=True):
            with self.assertRaisesRegex(RuntimeError, "INITIAL_ADMIN_USERNAME"):
                _bootstrap_admin_credentials()

    def test_bootstrap_admin_password_has_minimum_length(self):
        values = {
            **TEST_SERVER_ENV,
            "INITIAL_ADMIN_USERNAME": "bootstrap-admin",
            "INITIAL_ADMIN_PASSWORD": "short",
        }
        with patch.dict(os.environ, values, clear=True):
            with self.assertRaisesRegex(RuntimeError, "at least 12"):
                _bootstrap_admin_credentials()

    def test_bootstrap_admin_credentials_accept_external_values(self):
        values = {
            **TEST_SERVER_ENV,
            "INITIAL_ADMIN_USERNAME": "bootstrap-admin",
            "INITIAL_ADMIN_PASSWORD": "test-only-password-strong",
        }
        with patch.dict(os.environ, values, clear=True):
            username, password = _bootstrap_admin_credentials()
        self.assertEqual(username, values["INITIAL_ADMIN_USERNAME"])
        self.assertEqual(password, values["INITIAL_ADMIN_PASSWORD"])


if __name__ == "__main__":
    unittest.main()
