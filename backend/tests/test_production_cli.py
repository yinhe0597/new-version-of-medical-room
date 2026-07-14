import hashlib
import json
import os
import tempfile
import unittest
import warnings
import zipfile
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import OperationalError, TimeoutError as SQLAlchemyTimeoutError

from backend import production_cli


MYSQL_URI = "mysql+pymysql://medical:secret@db.example.test:3307/medical_db"
MYSQL_SERVER_UUID = "12345678-1234-5678-1234-567812345678"
ALEMBIC_HEADS = ["b6e1d8f3a2c4"]


class ProductionCliTestCase(unittest.TestCase):
    def _manifest_state(self, **overrides):
        state = {
            "created_at": datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
            "server_uuid": MYSQL_SERVER_UUID,
            "alembic_heads": list(ALEMBIC_HEADS),
            "gtid_executed_sha256": None,
            "gtid_check": "unavailable",
            "requires_write_quiescence": True,
        }
        state.update(overrides)
        return state

    def _current_target_state(self, **overrides):
        state = {
            "server_uuid": MYSQL_SERVER_UUID,
            "alembic_heads": list(ALEMBIC_HEADS),
            "gtid_executed_sha256": None,
        }
        state.update(overrides)
        return state

    def _write_backup(self, temp_dir, payload=b"-- MySQL dump\nSELECT 1;\n", **overrides):
        backup_path = Path(temp_dir) / "medical.sql"
        backup_path.write_bytes(payload)
        manifest = {
            "schema_version": production_cli.BACKUP_MANIFEST_SCHEMA_VERSION,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
            "database_target": production_cli.database_target_identity(MYSQL_URI),
            "backup_filename": backup_path.name,
            **self._manifest_state(),
        }
        manifest.update(overrides)
        production_cli.backup_manifest_path(backup_path).write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return backup_path

    def _write_bundle(
        self,
        temp_dir,
        payload=b"-- MySQL dump\nSELECT 1;\n",
        *,
        declared_payload=None,
        sql_name="medical.sql",
        manifest_name=None,
        manifest_overrides=None,
    ):
        declared_payload = payload if declared_payload is None else declared_payload
        manifest = {
            "schema_version": production_cli.BACKUP_MANIFEST_SCHEMA_VERSION,
            "sha256": hashlib.sha256(declared_payload).hexdigest(),
            "size_bytes": len(declared_payload),
            "database_target": production_cli.database_target_identity(MYSQL_URI),
            "backup_filename": sql_name,
            **self._manifest_state(),
        }
        manifest.update(manifest_overrides or {})
        bundle_path = Path(temp_dir) / "medical-backup.zip"
        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(sql_name, payload)
            archive.writestr(
                manifest_name or f"{sql_name}.manifest.json",
                json.dumps(manifest),
            )
        return bundle_path

    def test_no_database_mode_starts_server(self):
        self.assertIsNone(production_cli.execute_cli([]))

    def test_orphan_confirmation_flags_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "explicit command mode"):
            production_cli.execute_cli(["--yes"])

    def test_check_database_returns_blocking_exit_code(self):
        report = {"summary": {"overall": "blocked"}, "checks": [], "target": None}
        with patch.object(
            production_cli, "inspect_configured_database", return_value=report
        ), patch(
            "scripts.check_production_database.format_human_report",
            return_value="blocked",
        ):
            self.assertEqual(production_cli.execute_cli(["--check-database"]), 2)

    def test_configured_preflight_forwards_tls_timeouts_and_depth_policy(self):
        connect_args = {
            "connect_timeout": 7,
            "read_timeout": 11,
            "write_timeout": 13,
            "ssl_ca": "ca.pem",
            "ssl_verify_cert": True,
            "ssl_verify_identity": True,
        }
        with patch(
            "backend.config.Config.SQLALCHEMY_DATABASE_URI", MYSQL_URI
        ), patch(
            "backend.config.Config.DATABASE_REQUIRE_TLS", True
        ), patch(
            "backend.config.Config.SQLALCHEMY_ENGINE_OPTIONS",
            {"connect_args": connect_args},
        ), patch(
            "backend.config.Config.MYSQL_PREFLIGHT_QUERY_TIMEOUT", 17
        ), patch(
            "scripts.check_production_database.inspect_database",
            return_value={"summary": {"overall": "passed"}},
        ) as inspect:
            production_cli.inspect_configured_database(
                deep_checks=False,
                enforce_runtime_least_privilege=False,
            )

        kwargs = inspect.call_args.kwargs
        self.assertEqual(kwargs["read_timeout"], 11)
        self.assertEqual(kwargs["write_timeout"], 13)
        self.assertEqual(kwargs["query_timeout"], 17)
        self.assertFalse(kwargs["deep_checks"])
        self.assertFalse(kwargs["enforce_runtime_least_privilege"])
        self.assertIs(kwargs["configured_connect_args"], connect_args)

    def test_retryable_preflight_uses_distinct_startup_exception(self):
        retryable_report = {
            "summary": {"overall": "blocked", "retryable": True},
            "checks": [],
            "target": None,
        }
        with patch.object(
            production_cli,
            "inspect_configured_database",
            return_value=retryable_report,
        ), patch(
            "scripts.check_production_database.format_human_report",
            return_value="unavailable",
        ):
            with self.assertRaises(production_cli.ProductionDatabaseUnavailable):
                production_cli.ensure_configured_database_ready(
                    log_report=False, deep_checks=False
                )

        permanent_report = {
            "summary": {"overall": "blocked", "retryable": False},
            "checks": [],
            "target": None,
        }
        with patch.object(
            production_cli,
            "inspect_configured_database",
            return_value=permanent_report,
        ), patch(
            "scripts.check_production_database.format_human_report",
            return_value="blocked",
        ):
            with self.assertRaises(production_cli.ProductionDatabaseBlocked) as raised:
                production_cli.ensure_configured_database_ready(
                    log_report=False, deep_checks=False
                )
        self.assertNotIsInstance(
            raised.exception, production_cli.ProductionDatabaseUnavailable
        )

    def test_backup_file_and_target_bound_manifest_are_verified(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = self._write_backup(temp_dir)

            verified = production_cli.verify_backup_file(backup_path, MYSQL_URI)

        self.assertEqual(verified["size_bytes"], len(b"-- MySQL dump\nSELECT 1;\n"))
        self.assertEqual(
            verified["database_target"],
            "mysql://db.example.test:3307/medical_db",
        )

    def test_v1_backup_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = self._write_backup(temp_dir, schema_version=1)

            with self.assertRaisesRegex(RuntimeError, "schema_version must be 2"):
                production_cli.verify_backup_file(backup_path, MYSQL_URI)

    def test_expired_and_future_backup_timestamps_are_rejected(self):
        reference = datetime(2026, 7, 13, 6, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            expired = self._write_backup(
                temp_dir,
                created_at=(reference - timedelta(minutes=61)).isoformat(),
            )
            with self.assertRaisesRegex(RuntimeError, "older than"):
                production_cli.verify_backup_file(
                    expired,
                    MYSQL_URI,
                    max_age_minutes=60,
                    now=reference,
                )

            future = self._write_backup(
                temp_dir,
                created_at=(reference + timedelta(seconds=1)).isoformat(),
            )
            with self.assertRaisesRegex(RuntimeError, "in the future"):
                production_cli.verify_backup_file(
                    future,
                    MYSQL_URI,
                    max_age_minutes=60,
                    now=reference,
                )

    def test_live_target_binding_rejects_instance_schema_and_gtid_changes(self):
        manifest = {
            **self._manifest_state(
                gtid_executed_sha256="a" * 64,
                gtid_check="unchanged",
            )
        }
        with self.assertRaisesRegex(RuntimeError, "server_uuid"):
            production_cli.verify_backup_target_state(
                manifest,
                self._current_target_state(
                    server_uuid="87654321-4321-8765-4321-876543218765"
                ),
            )
        with self.assertRaisesRegex(RuntimeError, "Alembic heads"):
            production_cli.verify_backup_target_state(
                manifest,
                self._current_target_state(alembic_heads=["different_head"]),
            )
        with self.assertRaisesRegex(RuntimeError, "GTID state changed"):
            production_cli.verify_backup_target_state(
                manifest,
                self._current_target_state(gtid_executed_sha256="b" * 64),
            )

    def test_dump_state_binding_detects_changes_during_backup(self):
        before = self._current_target_state(gtid_executed_sha256="a" * 64)
        after = self._current_target_state(gtid_executed_sha256="b" * 64)

        with self.assertRaisesRegex(RuntimeError, "stop all writes"):
            production_cli.backup_state_manifest_fields(before, after)

    def test_gtid_query_failures_are_never_reported_as_unavailable(self):
        failures = (
            OperationalError(
                "SELECT @@GLOBAL.gtid_executed",
                {},
                PermissionError("access denied"),
            ),
            SQLAlchemyTimeoutError("GTID query timed out"),
            ConnectionError("connection dropped"),
            PermissionError("GTID permission denied"),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                connection = MagicMock()
                uuid_result = MagicMock()
                uuid_result.scalar_one.return_value = MYSQL_SERVER_UUID
                connection.execute.side_effect = [uuid_result, failure]
                inspector = MagicMock()
                inspector.has_table.return_value = False

                with patch.object(
                    production_cli,
                    "sqlalchemy_inspect",
                    return_value=inspector,
                ), self.assertRaises(type(failure)) as raised:
                    production_cli.read_mysql_target_state(connection)
                self.assertIs(raised.exception, failure)

    def test_successful_empty_gtid_query_is_marked_unavailable(self):
        connection = MagicMock()
        uuid_result = MagicMock()
        uuid_result.scalar_one.return_value = MYSQL_SERVER_UUID
        gtid_result = MagicMock()
        gtid_result.scalar_one.return_value = ""
        connection.execute.side_effect = [uuid_result, gtid_result]
        inspector = MagicMock()
        inspector.has_table.return_value = False

        with patch.object(
            production_cli,
            "sqlalchemy_inspect",
            return_value=inspector,
        ):
            state = production_cli.read_mysql_target_state(connection)

        manifest_fields = production_cli.backup_state_manifest_fields(state, state)
        self.assertIsNone(state["gtid_executed_sha256"])
        self.assertEqual(manifest_fields["gtid_check"], "unavailable")

    def test_zip_bundle_streams_and_verifies_internal_sql(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = self._write_bundle(temp_dir)

            verified = production_cli.verify_backup_file(bundle_path, MYSQL_URI)

        self.assertEqual(verified["archive_entry"], "medical.sql")
        self.assertEqual(verified["size_bytes"], len(b"-- MySQL dump\nSELECT 1;\n"))
        self.assertTrue(verified["manifest_path"].endswith("!/medical.sql.manifest.json"))

    def test_zip_bundle_rejects_tampered_internal_sql(self):
        original = b"-- MySQL dump\nSELECT 1;\n"
        tampered = b"-- MySQL dump\nSELECT 2;\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = self._write_bundle(
                temp_dir,
                payload=tampered,
                declared_payload=original,
            )

            with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
                production_cli.verify_backup_file(bundle_path, MYSQL_URI)

    def test_zip_bundle_rejects_unsafe_entry_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = self._write_bundle(
                temp_dir,
                sql_name="../medical.sql",
            )

            with self.assertRaisesRegex(RuntimeError, "unsafe entry"):
                production_cli.verify_backup_file(bundle_path, MYSQL_URI)

    def test_zip_bundle_rejects_missing_or_misnamed_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = self._write_bundle(
                temp_dir,
                manifest_name="manifest.json",
            )

            with self.assertRaisesRegex(RuntimeError, "manifest name"):
                production_cli.verify_backup_file(bundle_path, MYSQL_URI)

    def test_zip_bundle_rejects_missing_manifest_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "missing-manifest.zip"
            with zipfile.ZipFile(bundle_path, "w") as archive:
                archive.writestr("medical.sql", b"backup")

            with self.assertRaisesRegex(RuntimeError, "exactly one SQL and one manifest"):
                production_cli.verify_backup_file(bundle_path, MYSQL_URI)

    def test_zip_bundle_rejects_duplicate_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "duplicate.zip"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(bundle_path, "w") as archive:
                    archive.writestr("medical.sql", b"first")
                    archive.writestr("medical.sql", b"second")

            with self.assertRaisesRegex(RuntimeError, "duplicate entry"):
                production_cli.verify_backup_file(bundle_path, MYSQL_URI)

    def test_zip_bundle_rejects_oversized_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "oversized.zip"
            with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("medical.sql", b"backup")
                archive.writestr(
                    "medical.sql.manifest.json",
                    b" " * (production_cli.MAX_BACKUP_MANIFEST_BYTES + 1),
                )

            with self.assertRaisesRegex(RuntimeError, "manifest is unexpectedly large"):
                production_cli.verify_backup_file(bundle_path, MYSQL_URI)

    def test_zip_bundle_rejects_corrupted_entry_bytes(self):
        payload = b"unique-sql-backup-payload"
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "corrupt.zip"
            manifest = {
                "schema_version": production_cli.BACKUP_MANIFEST_SCHEMA_VERSION,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
                "database_target": production_cli.database_target_identity(MYSQL_URI),
                "backup_filename": "medical.sql",
                **self._manifest_state(),
            }
            with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("medical.sql", payload)
                archive.writestr("medical.sql.manifest.json", json.dumps(manifest))
            bundle_bytes = bundle_path.read_bytes()
            self.assertEqual(bundle_bytes.count(payload), 1)
            bundle_path.write_bytes(bundle_bytes.replace(payload, b"X" + payload[1:]))

            with self.assertRaisesRegex(RuntimeError, "safely verified"):
                production_cli.verify_backup_file(bundle_path, MYSQL_URI)

    def test_unix_socket_target_identity_is_stable_and_does_not_expose_path(self):
        socket_path = "/run/secrets/mysql.sock"
        identity = production_cli.database_target_identity(
            "mysql+pymysql://medical@localhost/medical_db",
            unix_socket=socket_path,
        )

        self.assertNotIn(socket_path, identity)
        self.assertRegex(identity, r"\?unix_socket_sha256=[0-9a-f]{64}$")
        self.assertNotEqual(
            identity,
            production_cli.database_target_identity(
                "mysql+pymysql://medical@localhost/medical_db",
                unix_socket="/run/mysql/other.sock",
            ),
        )

    def test_backup_file_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = self._write_backup(temp_dir)
            backup_path.write_bytes(b"tampered but same file")

            with self.assertRaisesRegex(RuntimeError, "size mismatch|SHA-256 mismatch"):
                production_cli.verify_backup_file(backup_path, MYSQL_URI)

    def test_backup_manifest_size_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = self._write_backup(temp_dir, size_bytes=999)

            with self.assertRaisesRegex(RuntimeError, "size mismatch"):
                production_cli.verify_backup_file(backup_path, MYSQL_URI)

    def test_backup_manifest_target_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = self._write_backup(
                temp_dir,
                database_target="mysql://other.example.test:3306/medical_db",
            )

            with self.assertRaisesRegex(RuntimeError, "migration target"):
                production_cli.verify_backup_file(backup_path, MYSQL_URI)

    def test_backup_manifest_is_required(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = Path(temp_dir) / "medical.sql"
            backup_path.write_bytes(b"backup")

            with self.assertRaisesRegex(RuntimeError, "manifest does not exist"):
                production_cli.verify_backup_file(backup_path, MYSQL_URI)

    def test_legacy_digest_only_gate_is_removed(self):
        with self.assertRaises(SystemExit):
            production_cli.execute_cli(
                ["--migrate-database", "--backup-sha256", "a" * 64, "--yes"]
            )

    def test_migration_command_forwards_backup_file(self):
        backup_path = os.path.join("C:\\", "backups", "medical.sql")
        with patch.object(
            production_cli, "migrate_configured_database", return_value={}
        ) as migrate:
            result = production_cli.execute_cli(
                ["--migrate-database", "--backup-file", backup_path, "--yes"]
            )

        self.assertEqual(result, 0)
        migrate.assert_called_once_with(backup_file=backup_path, confirmed=True)

    def test_migration_logs_original_failure_but_returns_sanitized_error(self):
        class FakeApp:
            def app_context(self):
                return nullcontext()

        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = self._write_backup(temp_dir)
            with patch(
                "backend.config.Config.SQLALCHEMY_DATABASE_URI", MYSQL_URI
            ), patch(
                "backend.migration_app.create_app", return_value=FakeApp()
            ), patch.object(
                production_cli,
                "_read_migration_target_state",
                return_value=self._current_target_state(),
            ), patch(
                "flask_migrate.upgrade",
                side_effect=ValueError("raw server detail top-secret"),
            ), self.assertLogs(level="ERROR") as captured:
                with self.assertRaises(RuntimeError) as raised:
                    production_cli.migrate_configured_database(
                        backup_file=str(backup_path), confirmed=True
                    )

        self.assertNotIn("top-secret", str(raised.exception))
        self.assertIn("raw server detail top-secret", "\n".join(captured.output))

    def test_migration_live_binding_failure_never_runs_ddl(self):
        class FakeApp:
            def app_context(self):
                return nullcontext()

        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = self._write_backup(temp_dir)
            with patch(
                "backend.config.Config.SQLALCHEMY_DATABASE_URI", MYSQL_URI
            ), patch(
                "backend.migration_app.create_app", return_value=FakeApp()
            ), patch.object(
                production_cli,
                "_read_migration_target_state",
                return_value=self._current_target_state(
                    server_uuid="87654321-4321-8765-4321-876543218765"
                ),
            ), patch("flask_migrate.upgrade") as upgrade:
                with self.assertRaisesRegex(RuntimeError, "server_uuid"):
                    production_cli.migrate_configured_database(
                        backup_file=str(backup_path), confirmed=True
                    )

        upgrade.assert_not_called()

    def test_migration_gtid_query_failure_never_runs_ddl(self):
        class FakeApp:
            def app_context(self):
                return nullcontext()

        gtid_error = OperationalError(
            "SELECT @@GLOBAL.gtid_executed",
            {},
            TimeoutError("query timed out"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = self._write_backup(temp_dir)
            with patch(
                "backend.config.Config.SQLALCHEMY_DATABASE_URI", MYSQL_URI
            ), patch(
                "backend.migration_app.create_app", return_value=FakeApp()
            ), patch.object(
                production_cli,
                "_read_migration_target_state",
                side_effect=gtid_error,
            ), patch("flask_migrate.upgrade") as upgrade, self.assertLogs(
                level="ERROR"
            ):
                with self.assertRaisesRegex(RuntimeError, "no DDL was attempted"):
                    production_cli.migrate_configured_database(
                        backup_file=str(backup_path), confirmed=True
                    )

        upgrade.assert_not_called()

    def test_packaged_sqlite_import_defaults_to_dry_run(self):
        with patch("backend.migrate_to_mysql.run_migration") as migrate:
            result = production_cli.execute_cli(
                ["--import-sqlite", "C:/backups/app.db"]
            )

        self.assertEqual(result, 0)
        self.assertFalse(migrate.call_args.kwargs["execute"])
        self.assertIsNone(migrate.call_args.kwargs["expected_source_sha256"])

    def test_packaged_sqlite_import_forwards_source_digest(self):
        digest = "b" * 64
        with patch("backend.migrate_to_mysql.run_migration") as migrate:
            result = production_cli.execute_cli(
                [
                    "--import-sqlite",
                    "C:/backups/app.db",
                    "--execute",
                    "--yes",
                    "--expected-source-sha256",
                    digest,
                ]
            )

        self.assertEqual(result, 0)
        self.assertTrue(migrate.call_args.kwargs["execute"])
        self.assertEqual(migrate.call_args.kwargs["expected_source_sha256"], digest)


if __name__ == "__main__":
    unittest.main()
