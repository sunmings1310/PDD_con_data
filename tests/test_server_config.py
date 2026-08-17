from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BASE_ENV = {
    "APP_ENV": "test",
    "ORACLE_HOST": "127.0.0.1",
    "ORACLE_PORT": "1521",
    "ORACLE_SERVICE": "TEST_SERVICE",
    "ORACLE_USER": "TEST_USER",
    "ORACLE_PASSWORD": "test-only-password",
    "JWT_SECRET": "Test-only-JWT-secret-32-characters!",
    "JWT_ALGORITHM": "HS256",
    "JWT_EXPIRE_SEC": "3600",
}

# server.config intentionally validates at import time; test discovery supplies a
# complete isolated configuration before importing the module under test.
for _key, _value in BASE_ENV.items():
    os.environ.setdefault(_key, _value)

from server.config import ConfigurationError, Settings, load_settings  # noqa: E402


class ServerConfigTest(unittest.TestCase):
    def load_from(self, values: dict[str, str]):
        with patch.dict(os.environ, values, clear=True):
            return load_settings(env_file=None)

    def assert_config_error(self, values: dict[str, str], field: str) -> str:
        with self.assertRaises(ConfigurationError) as caught:
            self.load_from(values)
        message = str(caught.exception)
        self.assertIn(field, message)
        return message

    def test_oracle_required_field_missing(self):
        values = BASE_ENV.copy()
        values.pop("ORACLE_HOST")
        self.assert_config_error(values, "ORACLE_HOST")

    def test_oracle_port_invalid_type_and_range(self):
        for invalid in ("abc", "0", "65536"):
            with self.subTest(invalid=invalid):
                values = {**BASE_ENV, "ORACLE_PORT": invalid}
                self.assert_config_error(values, "ORACLE_PORT")

    def test_jwt_secret_missing(self):
        values = BASE_ENV.copy()
        values.pop("JWT_SECRET")
        self.assert_config_error(values, "JWT_SECRET")

    def test_production_rejects_weak_jwt_secret(self):
        values = {**BASE_ENV, "APP_ENV": "production", "JWT_SECRET": "CHANGE_ME"}
        self.assert_config_error(values, "JWT_SECRET")

    def test_valid_jwt_configuration(self):
        settings = self.load_from(BASE_ENV)
        self.assertEqual(settings.jwt_algorithm, "HS256")
        self.assertEqual(settings.jwt_expire_sec, 3600)

    def test_jwt_algorithm_allowlist(self):
        values = {**BASE_ENV, "JWT_ALGORITHM": "none"}
        self.assert_config_error(values, "JWT_ALGORITHM")

    def test_token_expire_range(self):
        for invalid in ("0", "59", "604801"):
            with self.subTest(invalid=invalid):
                values = {**BASE_ENV, "JWT_EXPIRE_SEC": invalid}
                self.assert_config_error(values, "JWT_EXPIRE_SEC")

    def test_test_environment_can_be_fully_injected(self):
        settings = self.load_from(BASE_ENV)
        self.assertEqual(settings.app_env, "test")
        self.assertEqual(settings.oracle_host, BASE_ENV["ORACLE_HOST"])

    def test_environment_overrides_dotenv(self):
        with tempfile.TemporaryDirectory() as directory:
            dotenv = Path(directory) / ".env"
            dotenv.write_text(
                "\n".join(
                    [
                        "APP_ENV=development",
                        "ORACLE_HOST=dotenv-host",
                        "ORACLE_PORT=1521",
                        "ORACLE_SERVICE=DOTENV_SERVICE",
                        "ORACLE_USER=DOTENV_USER",
                        "ORACLE_PASSWORD=dotenv-password",
                        "JWT_SECRET=Dotenv-only-JWT-secret-32-characters!",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, BASE_ENV, clear=True):
                settings = load_settings(env_file=dotenv)
            self.assertEqual(settings.oracle_host, BASE_ENV["ORACLE_HOST"])
            self.assertEqual(settings.app_env, "test")

    def test_exception_does_not_expose_secret(self):
        sentinel = "UNIQUE_SECRET_SENTINEL_DO_NOT_LOG"
        values = {
            **BASE_ENV,
            "APP_ENV": "production",
            "JWT_SECRET": sentinel,
            "ORACLE_PASSWORD": sentinel,
        }
        message = self.assert_config_error(values, "JWT_SECRET")
        self.assertNotIn(sentinel, message)

    def test_secret_repr_is_redacted(self):
        settings = Settings(_env_file=None, **{k.lower(): v for k, v in BASE_ENV.items()})
        self.assertNotIn(BASE_ENV["JWT_SECRET"], repr(settings))
        self.assertNotIn(BASE_ENV["ORACLE_PASSWORD"], repr(settings))


if __name__ == "__main__":
    unittest.main()
