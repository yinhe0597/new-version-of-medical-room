import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from flask import Flask
from sqlalchemy.exc import OperationalError

from backend.app.api.admin import (
    _file_sha256,
    _mysql_backup_response,
    _mysql_dump_command,
)
from backend.production_cli import verify_backup_file


MYSQL_URI = "mysql+pymysql://medical:top-secret@db.example.test:3307/medical_db"
MYSQL_SERVER_UUID = "12345678-1234-5678-1234-567812345678"


class MysqlBackupTestCase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            MYSQLDUMP_PATH="mysqldump",
            DATABASE_REQUIRE_TLS=True,
            MYSQL_SSL_CA="/secure/ca.pem",
            MYSQL_SSL_CERT="",
            MYSQL_SSL_KEY="",
        )
        self.backup_state = {
            "server_uuid": MYSQL_SERVER_UUID,
            "alembic_heads": ["b6e1d8f3a2c4"],
            "gtid_executed_sha256": None,
        }

    def test_dump_command_is_consistent_and_hides_password(self):
        command = _mysql_dump_command(MYSQL_URI, self.app.config)

        joined = " ".join(command)
        self.assertNotIn("top-secret", joined)
        self.assertIn("--single-transaction", command)
        self.assertIn("--quick", command)
        self.assertIn("--hex-blob", command)
        self.assertIn("--set-gtid-purged=OFF", command)
        self.assertIn("--ssl-mode=VERIFY_IDENTITY", command)
        self.assertIn("--ssl-ca=/secure/ca.pem", command)
        self.assertEqual(command[-1], "medical_db")

    def test_dump_command_supports_unix_socket(self):
        command = _mysql_dump_command(
            "mysql+pymysql://medical:secret@localhost/medical_db"
            "?unix_socket=/var/run/mysqld/mysqld.sock",
            {
                "MYSQLDUMP_PATH": "mysqldump",
                "DATABASE_REQUIRE_TLS": False,
                "MYSQL_SSL_CA": "",
                "MYSQL_SSL_CERT": "",
                "MYSQL_SSL_KEY": "",
            },
        )

        self.assertIn("--protocol=SOCKET", command)
        self.assertIn("--socket=/var/run/mysqld/mysqld.sock", command)
        self.assertNotIn("--protocol=TCP", command)
        self.assertNotIn("-h", command)
        self.assertNotIn("-P", command)

    def test_dump_command_uses_tls_material_from_normalized_engine_options(self):
        command = _mysql_dump_command(
            "mysql+pymysql://medical:secret@db.example.test/medical_db",
            {
                "MYSQLDUMP_PATH": "mysqldump",
                "DATABASE_REQUIRE_TLS": True,
                "MYSQL_SSL_CA": "",
                "MYSQL_SSL_CERT": "",
                "MYSQL_SSL_KEY": "",
                "SQLALCHEMY_ENGINE_OPTIONS": {
                    "connect_args": {
                        "ssl_ca": "/normalized/ca.pem",
                        "ssl_cert": "/normalized/client.pem",
                        "ssl_key": "/normalized/client.key",
                    }
                },
            },
        )

        self.assertIn("--ssl-mode=VERIFY_IDENTITY", command)
        self.assertIn("--ssl-ca=/normalized/ca.pem", command)
        self.assertIn("--ssl-cert=/normalized/client.pem", command)
        self.assertIn("--ssl-key=/normalized/client.key", command)

    def test_tls_client_certificate_requires_matching_key(self):
        with self.assertRaisesRegex(RuntimeError, "certificate and key"):
            _mysql_dump_command(
                "mysql+pymysql://medical:secret@db.example.test/medical_db",
                {
                    "DATABASE_REQUIRE_TLS": True,
                    "MYSQL_SSL_CERT": "/secure/client.pem",
                    "MYSQL_SSL_KEY": "",
                },
            )

    def test_file_sha256_is_stable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "backup.sql")
            with open(path, "wb") as handle:
                handle.write(b"SELECT 1;\n")

            self.assertEqual(
                _file_sha256(path),
                "b4e0497804e46e0a0b0b8c31975b062152d551bac49c3c2e80932567b4085dcd",
            )

    def test_backup_response_hashes_actual_bytes_and_cleans_up_on_close(self):
        payload = b"-- MySQL dump\nCREATE TABLE sample (id INT);\n"
        expected_digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = os.path.join(temp_dir, "generated.sql")
            bundle_path = os.path.join(temp_dir, "generated.zip")
            backup_fd = os.open(backup_path, os.O_CREAT | os.O_RDWR)
            bundle_fd = os.open(bundle_path, os.O_CREAT | os.O_RDWR)

            def fake_run(command, *, stdout, **kwargs):
                stdout.write(payload)
                return subprocess.CompletedProcess(command, 0, stderr=b"")

            with self.app.test_request_context(), patch(
                "backend.app.api.admin.tempfile.mkstemp",
                side_effect=[
                    (backup_fd, backup_path),
                    (bundle_fd, bundle_path),
                ],
            ), patch(
                "backend.app.api.admin._capture_mysql_backup_state",
                side_effect=[dict(self.backup_state), dict(self.backup_state)],
            ), patch("backend.app.api.admin.subprocess.run", side_effect=fake_run):
                response = _mysql_backup_response(MYSQL_URI)
                response_bytes = response.get_data()
                manifest = json.loads(response.headers["X-Backup-Manifest"])

                self.assertEqual(response.mimetype, "application/zip")
                self.assertEqual(response.headers["X-Backup-SHA256"], expected_digest)
                self.assertEqual(
                    response.headers["X-Backup-Bundle-SHA256"],
                    hashlib.sha256(response_bytes).hexdigest(),
                )
                self.assertEqual(manifest["sha256"], expected_digest)
                self.assertEqual(manifest["size_bytes"], len(payload))
                self.assertEqual(manifest["schema_version"], 2)
                self.assertEqual(manifest["server_uuid"], MYSQL_SERVER_UUID)
                self.assertEqual(manifest["alembic_heads"], ["b6e1d8f3a2c4"])
                self.assertTrue(manifest["requires_write_quiescence"])
                self.assertTrue(manifest["created_at"].endswith("Z"))
                self.assertEqual(
                    manifest["database_target"],
                    "mysql://db.example.test:3307/medical_db",
                )
                with zipfile.ZipFile(io.BytesIO(response_bytes), "r") as archive:
                    self.assertEqual(
                        set(archive.namelist()),
                        {
                            manifest["backup_filename"],
                            f"{manifest['backup_filename']}.manifest.json",
                        },
                    )
                    self.assertEqual(
                        archive.read(manifest["backup_filename"]), payload
                    )
                    internal_manifest = json.loads(
                        archive.read(
                            f"{manifest['backup_filename']}.manifest.json"
                        ).decode("utf-8")
                    )
                self.assertEqual(internal_manifest, manifest)
                verified = verify_backup_file(bundle_path, MYSQL_URI)
                self.assertEqual(
                    verified["archive_entry"], manifest["backup_filename"]
                )
                self.assertFalse(os.path.exists(backup_path))
                self.assertTrue(os.path.exists(bundle_path))
                response.close()
                self.assertFalse(os.path.exists(bundle_path))

    def test_failed_subprocess_removes_partial_backup(self):
        partial_payload = b"partial dump"
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = os.path.join(temp_dir, "partial.sql")
            fd = os.open(backup_path, os.O_CREAT | os.O_RDWR)

            def fake_run(command, *, stdout, **kwargs):
                stdout.write(partial_payload)
                return subprocess.CompletedProcess(command, 2, stderr=b"dump failed")

            with self.app.test_request_context(), patch(
                "backend.app.api.admin.tempfile.mkstemp",
                return_value=(fd, backup_path),
            ), patch(
                "backend.app.api.admin._capture_mysql_backup_state",
                return_value=dict(self.backup_state),
            ), patch("backend.app.api.admin.subprocess.run", side_effect=fake_run):
                result = _mysql_backup_response(MYSQL_URI)

            self.assertEqual(result[1], 500)
            self.assertFalse(os.path.exists(backup_path))

    def test_gtid_query_failure_blocks_backup_before_mysqldump(self):
        gtid_error = OperationalError(
            "SELECT @@GLOBAL.gtid_executed",
            {},
            PermissionError("access denied"),
        )
        with self.app.test_request_context(), patch(
            "backend.app.api.admin._capture_mysql_backup_state",
            side_effect=gtid_error,
        ), patch("backend.app.api.admin.subprocess.run") as dump, self.assertLogs(
            level="ERROR"
        ):
            result = _mysql_backup_response(MYSQL_URI)

        self.assertEqual(result[1], 503)
        self.assertIn("备份已阻止", result[0].get_json()["msg"])
        dump.assert_not_called()

    def test_manifest_failure_removes_completed_temporary_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = os.path.join(temp_dir, "completed.sql")
            fd = os.open(backup_path, os.O_CREAT | os.O_RDWR)

            def fake_run(command, *, stdout, **kwargs):
                stdout.write(b"completed dump")
                return subprocess.CompletedProcess(command, 0, stderr=b"")

            with self.app.test_request_context(), patch(
                "backend.app.api.admin.tempfile.mkstemp",
                return_value=(fd, backup_path),
            ), patch(
                "backend.app.api.admin._capture_mysql_backup_state",
                side_effect=[dict(self.backup_state), dict(self.backup_state)],
            ), patch(
                "backend.app.api.admin.subprocess.run", side_effect=fake_run
            ), patch(
                "backend.app.api.admin._file_sha256",
                side_effect=OSError("digest read failed"),
            ):
                result = _mysql_backup_response(MYSQL_URI)

            self.assertEqual(result[1], 500)
            self.assertFalse(os.path.exists(backup_path))

    def test_bundle_failure_removes_sql_and_zip_temporary_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = os.path.join(temp_dir, "completed.sql")
            bundle_path = os.path.join(temp_dir, "failed.zip")
            backup_fd = os.open(backup_path, os.O_CREAT | os.O_RDWR)
            bundle_fd = os.open(bundle_path, os.O_CREAT | os.O_RDWR)

            def fake_run(command, *, stdout, **kwargs):
                stdout.write(b"completed dump")
                return subprocess.CompletedProcess(command, 0, stderr=b"")

            with self.app.test_request_context(), patch(
                "backend.app.api.admin.tempfile.mkstemp",
                side_effect=[
                    (backup_fd, backup_path),
                    (bundle_fd, bundle_path),
                ],
            ), patch(
                "backend.app.api.admin._capture_mysql_backup_state",
                side_effect=[dict(self.backup_state), dict(self.backup_state)],
            ), patch(
                "backend.app.api.admin.subprocess.run", side_effect=fake_run
            ), patch(
                "backend.app.api.admin._write_mysql_backup_bundle",
                side_effect=OSError("zip write failed"),
            ):
                result = _mysql_backup_response(MYSQL_URI)

            self.assertEqual(result[1], 500)
            self.assertFalse(os.path.exists(backup_path))
            self.assertFalse(os.path.exists(bundle_path))

    def test_gtid_change_during_dump_discards_backup_before_bundling(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = os.path.join(temp_dir, "changed.sql")
            fd = os.open(backup_path, os.O_CREAT | os.O_RDWR)
            before = {**self.backup_state, "gtid_executed_sha256": "a" * 64}
            after = {**self.backup_state, "gtid_executed_sha256": "b" * 64}

            def fake_run(command, *, stdout, **kwargs):
                stdout.write(b"dump made during writes")
                return subprocess.CompletedProcess(command, 0, stderr=b"")

            with self.app.test_request_context(), patch(
                "backend.app.api.admin.tempfile.mkstemp",
                return_value=(fd, backup_path),
            ), patch(
                "backend.app.api.admin._capture_mysql_backup_state",
                side_effect=[before, after],
            ), patch("backend.app.api.admin.subprocess.run", side_effect=fake_run):
                result = _mysql_backup_response(MYSQL_URI)

            self.assertEqual(result[1], 409)
            self.assertFalse(os.path.exists(backup_path))


if __name__ == "__main__":
    unittest.main()
