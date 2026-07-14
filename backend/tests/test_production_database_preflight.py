import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlalchemy import (
    Column,
    Double,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect as sa_inspect,
    text,
)
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError

from scripts import check_production_database as preflight


TEST_HEAD = preflight.discover_expected_head()


def healthy_mysql_settings():
    return {
        "version": "8.0.26",
        "version_comment": "MySQL Community Server - GPL",
        "default_storage_engine": "InnoDB",
        "character_set_server": "utf8mb4",
        "character_set_database": "utf8mb4",
        "character_set_connection": "utf8mb4",
        "collation_server": "utf8mb4_unicode_ci",
        "collation_database": "utf8mb4_unicode_ci",
        "collation_connection": "utf8mb4_unicode_ci",
        "session_sql_mode": "STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION",
        "global_sql_mode": "STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION",
        "global_time_zone": "+00:00",
        "session_time_zone": "+00:00",
        "utc_offset_seconds": 0,
        "read_only": 0,
        "super_read_only": 0,
    }


class FakeInspector:
    default_schema_name = "medical_db"

    def get_table_names(self):
        return ["sample", "extension_table"]

    def get_columns(self, table_name):
        if table_name != "sample":
            return [{"name": "id", "type": mysql.INTEGER(), "nullable": False}]
        return [
            {
                "name": "id",
                "type": mysql.INTEGER(),
                "nullable": False,
                "default": None,
            },
            {
                "name": "name",
                "type": mysql.VARCHAR(5),
                "nullable": False,
                "default": None,
            },
            {
                "name": "legacy_note",
                "type": mysql.VARCHAR(20),
                "nullable": True,
                "default": None,
            },
        ]

    def get_pk_constraint(self, table_name):
        return {"constrained_columns": ["id"]}

    def get_indexes(self, table_name):
        return []

    def get_unique_constraints(self, table_name):
        return []

    def get_foreign_keys(self, table_name):
        return []


class ProductionDatabasePreflightTestCase(unittest.TestCase):
    def test_mysql_identity_query_avoids_reserved_alias(self):
        self.assertIn("AS authenticated_account", preflight.MYSQL_IDENTITY_SQL)
        self.assertNotIn("as current_user", preflight.MYSQL_IDENTITY_SQL.lower())

    def test_sqlite_text_affinity_accepts_legacy_text_for_varchar(self):
        self.assertTrue(
            preflight._type_compatible(
                sqlite.TEXT(), String(50), dialect_name="sqlite"
            )
        )
        self.assertFalse(
            preflight._type_compatible(
                mysql.TEXT(), String(50), dialect_name="mysql"
            )
        )

    def test_double_precision_is_required_on_mysql_and_affinity_safe_on_sqlite(self):
        self.assertTrue(
            preflight._type_compatible(
                mysql.DOUBLE(), Double(), dialect_name="mysql"
            )
        )
        self.assertFalse(
            preflight._type_compatible(
                mysql.FLOAT(), Double(), dialect_name="mysql"
            )
        )
        self.assertTrue(
            preflight._type_compatible(
                sqlite.FLOAT(), Double(), dialect_name="sqlite"
            )
        )

    def test_parse_database_urls_and_redact_secrets(self):
        password = "p@ss/word"
        target = preflight.parse_database_url(
            "mysql+pymysql://medroom:p%40ss%2Fword@db.local:3306/medical_db"
            "?charset=utf8mb4&ssl_key=C%3A%5Csecret.pem"
        )

        self.assertEqual(target.database_type, "mysql")
        self.assertEqual(target.database, "medical_db")
        self.assertEqual(target.driver, "pymysql")
        self.assertNotIn(password, target.safe_url)
        self.assertNotIn("secret.pem", target.safe_url)
        self.assertIn("***", target.safe_url)

        sqlite_target = preflight.parse_database_url("sqlite:///data/app.db")
        self.assertEqual(sqlite_target.database_type, "sqlite")
        self.assertEqual(sqlite_target.database, "data/app.db")

    def test_mysql_query_overrides_and_malformed_options_never_connect(self):
        invalid_uris = (
            "mysql+pymysql://user:password@127.0.0.1/medical_db?host=remote",
            "mysql+pymysql://user:password@127.0.0.1/medical_db?database=other",
            "mysql+pymysql://user:password@127.0.0.1/medical_db?charset=",
            "mysql+pymysql://user:password@127.0.0.1/medical_db?charset=utf8mb4&charset=utf8mb4",
            "mysql+pymysql://user:password@127.0.0.1/medical_db?charset=%ZZ",
            "mysql+pymysql://user:password@127.0.0.1/medical_db?unix_socket=%2Ftmp%2Fmysql.sock",
        )
        for uri in invalid_uris:
            with self.subTest(uri=uri):
                with mock.patch.object(preflight, "create_engine") as create_engine_mock:
                    report = preflight.inspect_database(
                        uri,
                        expected_head=TEST_HEAD,
                        require_tls=False,
                    )

                create_engine_mock.assert_not_called()
                self.assertEqual(report["summary"]["overall"], "blocked")

    def test_unsafe_configured_connect_args_never_connect(self):
        uri = "mysql+pymysql://user:password@127.0.0.1/medical_db"
        with mock.patch.object(preflight, "create_engine") as create_engine_mock:
            report = preflight.inspect_database(
                uri,
                expected_head=TEST_HEAD,
                require_tls=False,
                configured_connect_args={
                    "host": "remote.example",
                    "database": "other_db",
                    "ssl_disabled": True,
                },
            )

        create_engine_mock.assert_not_called()
        self.assertEqual(report["summary"]["overall"], "blocked")
        check = next(
            item for item in report["checks"] if item["id"] == "config.options"
        )
        self.assertIn("unsupported options", check["details"]["error"])

        target = preflight.parse_database_url(uri)
        with self.assertRaisesRegex(ValueError, "must be a mapping"):
            preflight.mysql_connection_configuration(
                target,
                5,
                configured_connect_args=[],
            )

    def test_read_only_executor_rejects_mutating_sql(self):
        connection = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "Refusing non-read-only"):
            preflight._execute_read_only(connection, "DELETE FROM patient")
        connection.execute.assert_not_called()

        preflight._execute_read_only(connection, "SELECT 1")
        connection.execute.assert_called_once()

    def test_supported_mysql_state_passes(self):
        report = preflight._base_report(TEST_HEAD, True)
        preflight.evaluate_mysql_server_state(
            report,
            healthy_mysql_settings(),
            "TLS_AES_256_GCM_SHA384",
            require_tls=True,
        )
        preflight._finalize(report)

        self.assertEqual(report["summary"]["overall"], "passed")
        self.assertEqual(
            {item["id"] for item in report["checks"]},
            {
                "mysql.version",
                "mysql.tls",
                "mysql.utf8mb4",
                "mysql.strict_mode",
                "mysql.default_engine",
                "mysql.read_only",
                "mysql.time_zone",
            },
        )

    def test_mysql_policy_reports_blockers_and_warnings(self):
        settings = healthy_mysql_settings()
        settings.update(
            {
                "version": "10.11.6-MariaDB",
                "version_comment": "MariaDB Server",
                "character_set_database": "utf8",
                "session_sql_mode": "NO_ENGINE_SUBSTITUTION",
                "default_storage_engine": "MyISAM",
                "read_only": 1,
                "utc_offset_seconds": 28800,
                "session_time_zone": "+08:00",
            }
        )
        report = preflight._base_report(TEST_HEAD, True)
        preflight.evaluate_mysql_server_state(
            report, settings, "", require_tls=True
        )
        preflight._finalize(report)

        self.assertEqual(report["summary"]["overall"], "blocked")
        blocking_ids = {
            item["id"]
            for item in report["checks"]
            if item["severity"] == "blocking"
        }
        self.assertTrue(
            {
                "mysql.version",
                "mysql.tls",
                "mysql.utf8mb4",
                "mysql.strict_mode",
                "mysql.default_engine",
                "mysql.read_only",
            }.issubset(blocking_ids)
        )
        self.assertEqual(
            next(item for item in report["checks"] if item["id"] == "mysql.time_zone")[
                "severity"
            ],
            "warning",
        )

    def test_model_schema_diff_separates_blocking_and_extension_differences(self):
        metadata = MetaData()
        sample = Table(
            "sample",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String(10), nullable=False),
        )
        Index("ix_sample_name", sample.c.name)

        differences = preflight.collect_model_schema_diff(FakeInspector(), metadata)
        blocking_kinds = {item["kind"] for item in differences["blocking"]}
        warning_kinds = {item["kind"] for item in differences["warnings"]}

        self.assertIn("type_mismatch", blocking_kinds)
        self.assertIn("missing_index", blocking_kinds)
        self.assertIn("extra_table", warning_kinds)
        self.assertIn("extra_column", warning_kinds)

    def test_missing_sqlite_file_is_blocked_without_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.db"
            uri = URL.create("sqlite+pysqlite", database=str(path)).render_as_string(
                hide_password=False
            )

            report = preflight.inspect_database(uri)

            self.assertFalse(path.exists())
            self.assertEqual(report["summary"]["overall"], "blocked")
            self.assertIn("was not created", preflight.format_human_report(report))

    def test_sqlite_preflight_does_not_change_database_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "production.db"
            uri = URL.create("sqlite+pysqlite", database=str(path)).render_as_string(
                hide_password=False
            )
            metadata = preflight._load_model_metadata()
            engine = create_engine(uri)
            metadata.create_all(engine)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE alembic_version "
                        "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                    )
                )
                connection.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:head)"),
                    {"head": TEST_HEAD},
                )
            engine.dispose()

            before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            before_mtime = path.stat().st_mtime_ns
            report = preflight.inspect_database(uri, require_tls=False)
            after_hash = hashlib.sha256(path.read_bytes()).hexdigest()

            self.assertEqual(after_hash, before_hash)
            self.assertEqual(path.stat().st_mtime_ns, before_mtime)
            self.assertEqual(report["summary"]["overall"], "passed", report)
            self.assertTrue(report["read_only"])

    def test_connection_error_and_reports_never_expose_password(self):
        password = "top-secret-password"
        uri = f"mysql+pymysql://user:{password}@127.0.0.1:3306/medical_db"
        with mock.patch.object(
            preflight,
            "create_engine",
            side_effect=RuntimeError(f"could not connect with {password}"),
        ):
            report = preflight.inspect_database(uri)

        json_output = preflight.format_json_report(report)
        human_output = preflight.format_human_report(report)
        self.assertNotIn(password, json_output)
        self.assertNotIn(password, human_output)
        self.assertEqual(json.loads(json_output)["summary"]["overall"], "blocked")

        private_ca = "C:/private/mysql/production-ca.pem"
        with mock.patch.object(
            preflight,
            "create_engine",
            side_effect=RuntimeError(f"could not read {private_ca}"),
        ):
            report = preflight.inspect_database(
                "mysql+pymysql://user:password@127.0.0.1/medical_db",
                require_tls=False,
                configured_connect_args={"ssl_ca": private_ca},
            )
        self.assertNotIn(private_ca, preflight.format_json_report(report))

    def test_unsupported_backend_is_blocked_without_connecting(self):
        with mock.patch.object(preflight, "create_engine") as create_engine_mock:
            report = preflight.inspect_database(
                "postgresql://user:password@localhost/medical_db"
            )

        create_engine_mock.assert_not_called()
        self.assertEqual(report["summary"]["overall"], "blocked")
        self.assertEqual(report["target"]["database_type"], "unsupported")

    def test_expected_head_is_discovered_and_requires_one_head(self):
        with tempfile.TemporaryDirectory() as directory:
            versions = Path(directory)
            (versions / "a.py").write_text(
                "revision = 'a'\ndown_revision = None\n", encoding="utf-8"
            )
            (versions / "b.py").write_text(
                "revision: str = 'b'\ndown_revision: str = 'a'\n", encoding="utf-8"
            )
            self.assertEqual(preflight.discover_expected_head(versions), "b")

            (versions / "c.py").write_text(
                "revision = 'c'\ndown_revision = 'a'\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "exactly one migration head"):
                preflight.discover_expected_head(versions)

    def test_expected_head_discovery_fails_when_resources_are_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "not-packaged"
            with self.assertRaisesRegex(RuntimeError, "directory is missing"):
                preflight.discover_expected_head(missing)

        with (
            mock.patch.object(
                preflight,
                "discover_expected_head",
                side_effect=RuntimeError("packaged migrations missing"),
            ),
            mock.patch.object(preflight, "create_engine") as create_engine_mock,
        ):
            report = preflight.inspect_database("sqlite:///does-not-matter.db")
        create_engine_mock.assert_not_called()
        self.assertEqual(report["summary"]["overall"], "blocked")
        self.assertEqual(report["checks"][0]["id"], "release.head")

    def test_mysql_tls_environment_is_mapped_to_pymysql(self):
        target = preflight.parse_database_url(
            "mysql+pymysql://user:password@db.local/medical_db"
        )
        args = preflight.mysql_connect_args(
            target,
            7,
            {
                "MYSQL_SSL_CA": "ca.pem",
                "MYSQL_SSL_CERT": "client.pem",
                "MYSQL_SSL_KEY": "client-key.pem",
                "MYSQL_SSL_VERIFY_CERT": "true",
                "MYSQL_SSL_VERIFY_IDENTITY": "1",
            },
        )

        self.assertEqual(args["connect_timeout"], 7)
        self.assertEqual(args["read_timeout"], 30)
        self.assertEqual(args["write_timeout"], 30)
        self.assertEqual(args["ssl_ca"], "ca.pem")
        self.assertEqual(args["ssl_cert"], "client.pem")
        self.assertEqual(args["ssl_key"], "client-key.pem")
        self.assertTrue(args["ssl_verify_cert"])
        self.assertTrue(args["ssl_verify_identity"])

    def test_mysql_tls_url_is_sanitized_before_sqlalchemy_sees_it(self):
        target = preflight.parse_database_url(
            "mysql+pymysql://user:password@db.example.com/medical_db"
            "?charset=utf8mb4&ssl_ca=ca.pem&ssl_cert=client.pem"
            "&ssl_key=client-key.pem&ssl_verify_cert=true"
            "&ssl_verify_identity=true"
        )
        connection_url, args, policy = preflight.mysql_connection_configuration(
            target,
            7,
            {},
            read_timeout=11,
            write_timeout=13,
        )

        self.assertEqual(dict(connection_url.query), {})
        engine = create_engine(connection_url)
        try:
            _positional, dialect_args = engine.dialect.create_connect_args(
                connection_url
            )
        finally:
            engine.dispose()
        self.assertNotIn("ssl", dialect_args)
        self.assertEqual(args["connect_timeout"], 7)
        self.assertEqual(args["read_timeout"], 11)
        self.assertEqual(args["write_timeout"], 13)
        self.assertEqual(args["charset"], "utf8mb4")
        self.assertEqual(args["ssl_ca"], "ca.pem")
        self.assertTrue(policy["verified"])

    def test_configured_tls_args_survive_a_sanitized_config_url(self):
        target = preflight.parse_database_url(
            "mysql+pymysql://user:password@db.example.com/medical_db"
            "?charset=utf8mb4"
        )
        _url, args, policy = preflight.mysql_connection_configuration(
            target,
            5,
            {},
            configured_connect_args={
                "ssl_ca": "ca-from-config.pem",
                "ssl_verify_cert": True,
                "ssl_verify_identity": True,
            },
        )

        self.assertEqual(args["ssl_ca"], "ca-from-config.pem")
        self.assertTrue(policy["verified"])

    def test_ssl_disabled_is_rejected_before_connecting(self):
        uri = (
            "mysql+pymysql://user:password@127.0.0.1/medical_db"
            "?ssl_disabled=true"
        )
        with mock.patch.object(preflight, "create_engine") as create_engine_mock:
            report = preflight.inspect_database(uri, require_tls=False)

        create_engine_mock.assert_not_called()
        self.assertEqual(report["summary"]["overall"], "blocked")
        self.assertEqual(report["summary"]["permanent_blocking"], 1)

    def test_remote_mysql_without_tls_material_never_connects(self):
        uri = "mysql+pymysql://user:password@db.example.com/medical_db"
        with (
            mock.patch.dict(
                preflight.os.environ,
                {
                    "MYSQL_SSL_CA": "",
                    "MYSQL_SSL_CERT": "",
                    "MYSQL_SSL_KEY": "",
                },
                clear=False,
            ),
            mock.patch.object(preflight, "create_engine") as create_engine_mock,
        ):
            report = preflight.inspect_database(uri, require_tls=True)

        create_engine_mock.assert_not_called()
        check = next(item for item in report["checks"] if item["id"] == "config.tls")
        self.assertEqual(check["severity"], "blocking")

        with mock.patch.object(
            preflight,
            "create_engine",
            side_effect=RuntimeError("connection attempted"),
        ) as create_engine_mock:
            preflight.inspect_database(uri, require_tls=False)
        create_engine_mock.assert_called_once()

    def test_remote_mysql_requires_ca_and_identity_verification(self):
        ssl_only_uri = (
            "mysql+pymysql://user:password@db.example.com/medical_db?ssl=true"
        )
        with mock.patch.object(preflight, "create_engine") as create_engine_mock:
            report = preflight.inspect_database(ssl_only_uri, require_tls=True)
        create_engine_mock.assert_not_called()
        self.assertEqual(report["summary"]["overall"], "blocked")

        no_identity_uri = (
            "mysql+pymysql://user:password@db.example.com/medical_db"
            "?ssl_ca=ca.pem&ssl_verify_cert=true&ssl_verify_identity=false"
        )
        with mock.patch.object(preflight, "create_engine") as create_engine_mock:
            report = preflight.inspect_database(no_identity_uri, require_tls=True)
        create_engine_mock.assert_not_called()
        self.assertEqual(report["summary"]["overall"], "blocked")

        local_no_verify_uri = (
            "mysql+pymysql://user:password@127.0.0.1/medical_db"
            "?ssl_verify_identity=false"
        )
        with mock.patch.object(preflight, "create_engine") as create_engine_mock:
            report = preflight.inspect_database(local_no_verify_uri, require_tls=True)
        create_engine_mock.assert_not_called()
        self.assertEqual(report["summary"]["overall"], "blocked")

        target = preflight.parse_database_url(
            "mysql+pymysql://user:password@db.example.com/medical_db?ssl_ca=ca.pem"
        )
        args = preflight.mysql_connect_args(target, 5, {})
        self.assertTrue(args["ssl_verify_cert"])
        self.assertTrue(args["ssl_verify_identity"])

    def test_mysql_grants_require_dml_for_every_model_table(self):
        report = preflight._base_report(TEST_HEAD, True)
        preflight.evaluate_mysql_grants(
            report,
            [
                "GRANT USAGE ON *.* TO `app`@`localhost`",
                "GRANT SELECT, INSERT, UPDATE, DELETE ON `medical_db`.* "
                "TO `app`@`localhost`"
            ],
            "medical_db",
            {"user", "patient"},
        )
        preflight._finalize(report)
        self.assertEqual(report["summary"]["overall"], "passed")

        report = preflight._base_report(TEST_HEAD, True)
        preflight.evaluate_mysql_grants(
            report,
            ["GRANT SELECT ON `medical_db`.* TO `app`@`localhost`"],
            "medical_db",
            {"user", "patient"},
        )
        preflight._finalize(report)
        self.assertEqual(report["summary"]["overall"], "blocked")
        missing = report["checks"][0]["details"]["missing_by_table"]
        self.assertEqual(missing["patient"], ["DELETE", "INSERT", "UPDATE"])

    def test_mysql_grants_block_overprivileged_runtime_account(self):
        report = preflight._base_report(TEST_HEAD, True)
        preflight.evaluate_mysql_grants(
            report,
            [
                "GRANT ALL PRIVILEGES ON *.* TO `app`@`localhost` "
                "WITH GRANT OPTION"
            ],
            "medical_db",
            {"user", "patient"},
        )
        preflight._finalize(report)

        self.assertEqual(report["summary"]["overall"], "blocked")
        elevated = next(
            item for item in report["checks"] if item["id"] == "mysql.grants_elevated"
        )
        self.assertEqual(elevated["severity"], "blocking")
        self.assertEqual(
            elevated["details"]["findings"][0]["privileges"],
            ["ALL PRIVILEGES", "GRANT OPTION"],
        )

        migration_report = preflight._base_report(TEST_HEAD, True)
        preflight.evaluate_mysql_grants(
            migration_report,
            [
                "GRANT ALL PRIVILEGES ON *.* TO `migration`@`localhost` "
                "WITH GRANT OPTION"
            ],
            "medical_db",
            {"user", "patient"},
            enforce_runtime_least_privilege=False,
        )
        preflight._finalize(migration_report)
        self.assertEqual(migration_report["summary"]["overall"], "warning")

    def test_mysql_global_dml_is_too_broad_for_runtime_account(self):
        global_dml = (
            "GRANT SELECT, INSERT, UPDATE, DELETE ON *.* TO `app`@`localhost`"
        )
        report = preflight._base_report(TEST_HEAD, True)
        preflight.evaluate_mysql_grants(
            report,
            [global_dml],
            "medical_db",
            {"user", "patient"},
        )
        preflight._finalize(report)

        self.assertEqual(report["summary"]["overall"], "blocked")
        self.assertEqual(
            next(item for item in report["checks"] if item["id"] == "mysql.grants")[
                "status"
            ],
            "pass",
        )
        broad = next(
            item
            for item in report["checks"]
            if item["id"] == "mysql.grants_global_scope"
        )
        self.assertEqual(broad["severity"], "blocking")
        self.assertEqual(
            broad["details"]["findings"][0]["privileges"],
            ["DELETE", "INSERT", "SELECT", "UPDATE"],
        )

        migration_report = preflight._base_report(TEST_HEAD, True)
        preflight.evaluate_mysql_grants(
            migration_report,
            [global_dml],
            "medical_db",
            {"user", "patient"},
            enforce_runtime_least_privilege=False,
        )
        preflight._finalize(migration_report)
        self.assertEqual(migration_report["summary"]["overall"], "warning")

    def test_mysql_role_grant_is_unresolved_but_default_role_line_is_not_a_grant(self):
        role_grant = "GRANT `medical_runtime`@`%` TO `app`@`localhost`"
        default_role = (
            "SET DEFAULT ROLE `medical_runtime`@`%` TO `app`@`localhost`"
        )
        report = preflight._base_report(TEST_HEAD, True)
        preflight.evaluate_mysql_grants(
            report,
            [role_grant, default_role],
            "medical_db",
            {"user", "patient"},
        )
        preflight._finalize(report)

        self.assertEqual(report["summary"]["overall"], "blocked")
        unresolved = next(
            item
            for item in report["checks"]
            if item["id"] == "mysql.grants_unresolved"
        )
        self.assertEqual(unresolved["severity"], "blocking")
        self.assertEqual(
            unresolved["details"]["findings"],
            [{"kind": "role_grant", "statement": role_grant}],
        )

        migration_report = preflight._base_report(TEST_HEAD, True)
        preflight.evaluate_mysql_grants(
            migration_report,
            [role_grant, default_role],
            "medical_db",
            {"user", "patient"},
            enforce_runtime_least_privilege=False,
        )
        preflight._finalize(migration_report)
        self.assertEqual(migration_report["summary"]["overall"], "warning")
        self.assertTrue(
            all(
                item["severity"] != "blocking"
                for item in migration_report["checks"]
            )
        )

    def test_transient_connection_failure_is_marked_retryable(self):
        transient = OperationalError(
            "connect", {}, Exception(2003, "Can't connect to MySQL server")
        )
        with mock.patch.object(preflight, "create_engine", side_effect=transient):
            report = preflight.inspect_database(
                "mysql+pymysql://user:password@127.0.0.1/medical_db",
                require_tls=False,
            )

        self.assertEqual(report["summary"]["overall"], "blocked")
        self.assertTrue(report["summary"]["retryable"])
        self.assertEqual(report["summary"]["permanent_blocking"], 0)

        permanent = OperationalError(
            "connect", {}, Exception(1045, "Access denied for user")
        )
        with mock.patch.object(preflight, "create_engine", side_effect=permanent):
            report = preflight.inspect_database(
                "mysql+pymysql://user:password@127.0.0.1/medical_db",
                require_tls=False,
            )
        self.assertFalse(report["summary"]["retryable"])

    def test_mysql_orphan_scan_has_server_side_query_deadline(self):
        metadata = MetaData()
        Table("parent", metadata, Column("id", Integer, primary_key=True))
        Table(
            "child",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("parent_id", Integer, ForeignKey("parent.id")),
        )
        inspector = mock.Mock()
        inspector.get_table_names.return_value = ["parent", "child"]
        inspector.get_columns.side_effect = lambda table: (
            [{"name": "id"}]
            if table == "parent"
            else [{"name": "id"}, {"name": "parent_id"}]
        )
        connection = mock.Mock()
        connection.dialect = mysql.dialect()
        connection.execute.return_value.scalar_one.return_value = 0
        report = preflight._base_report(TEST_HEAD, True)

        preflight._check_model_orphans(
            report,
            connection,
            inspector,
            metadata,
            query_timeout=7,
        )

        statement = str(connection.execute.call_args.args[0])
        self.assertIn("MAX_EXECUTION_TIME(7000)", statement)

    def test_model_foreign_key_orphans_are_blocking(self):
        metadata = MetaData()
        Table("parent", metadata, Column("id", Integer, primary_key=True))
        Table(
            "child",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("parent_id", Integer, ForeignKey("parent.id")),
        )
        engine = create_engine("sqlite+pysqlite:///:memory:")
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO child (id, parent_id) VALUES (1, 99)"))
        report = preflight._base_report(TEST_HEAD, False)
        with engine.connect() as connection:
            preflight._check_model_orphans(
                report, connection, sa_inspect(connection), metadata
            )
        engine.dispose()
        preflight._finalize(report)

        self.assertEqual(report["summary"]["overall"], "blocked")
        self.assertEqual(
            report["checks"][0]["details"]["violations"][0]["orphan_count"], 1
        )


if __name__ == "__main__":
    unittest.main()
