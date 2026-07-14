import unittest
from unittest.mock import patch

import run_prod
from backend.production_cli import (
    ProductionDatabaseBlocked,
    ProductionDatabaseUnavailable,
)


class ProductionEntryPointTestCase(unittest.TestCase):
    def test_database_log_target_is_useful_and_hides_passwords(self):
        sqlite_uri = "sqlite:///F:/deployment/data/app.db"
        mysql_uri = "mysql+pymysql://medical:top-secret@db.example/medical_db"

        self.assertEqual(run_prod._safe_database_log_target(sqlite_uri), sqlite_uri)
        rendered_mysql = run_prod._safe_database_log_target(mysql_uri)
        self.assertIn("db.example/medical_db", rendered_mysql)
        self.assertNotIn("top-secret", rendered_mysql)

    def _run_with_failure(self, error):
        with patch.object(run_prod, "initialize_runtime"), patch(
            "backend.production_cli.execute_cli", return_value=None
        ), patch.object(run_prod, "start_server", side_effect=error) as start, patch.object(
            run_prod.time_module, "sleep"
        ), patch.object(run_prod.logging, "error"), patch.object(
            run_prod.logging, "warning"
        ), patch.object(run_prod.logging, "info"), patch(
            "builtins.input", return_value=""
        ), patch("builtins.print"):
            status = run_prod.main([])
        return status, start.call_count

    def test_repeated_unexpected_crashes_return_failure(self):
        status, attempts = self._run_with_failure(RuntimeError("unexpected crash"))

        self.assertEqual(status, 2)
        self.assertEqual(attempts, 5)

    def test_temporary_database_failure_retries_then_returns_failure(self):
        status, attempts = self._run_with_failure(
            ProductionDatabaseUnavailable("database unavailable")
        )

        self.assertEqual(status, 2)
        self.assertEqual(attempts, 5)

    def test_permanent_database_block_does_not_restart(self):
        status, attempts = self._run_with_failure(
            ProductionDatabaseBlocked("unsafe database configuration")
        )

        self.assertEqual(status, 2)
        self.assertEqual(attempts, 1)

    def test_nonzero_system_exit_code_is_preserved(self):
        status, attempts = self._run_with_failure(SystemExit(7))

        self.assertEqual(status, 7)
        self.assertEqual(attempts, 1)

    def test_zero_or_empty_system_exit_is_successful(self):
        for exit_code in (0, None):
            with self.subTest(exit_code=exit_code):
                status, attempts = self._run_with_failure(SystemExit(exit_code))

                self.assertEqual(status, 0)
                self.assertEqual(attempts, 1)

    def test_noninteger_system_exit_returns_failure(self):
        status, attempts = self._run_with_failure(SystemExit("startup failed"))

        self.assertEqual(status, 1)
        self.assertEqual(attempts, 1)


if __name__ == "__main__":
    unittest.main()
