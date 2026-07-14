import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
import unittest
from unittest.mock import patch

from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine
from sqlalchemy.engine import make_url

from backend.migrate_to_mysql import (
    MigrationConfig,
    TableStats,
    _actual_foreign_key_orphans,
    _assert_expected_source_sha256,
    _assert_reconciled,
    _assert_target_alembic_head,
    _cross_boundary_foreign_keys,
    _foreign_key_orphans,
    _migration_config,
    _modeled_destination_tables,
    _modeled_table_names,
    _record_batches,
    _reflect_required_tables,
    _table_stats,
    _validate_copy_columns,
    _validate_execution_flags,
    _validate_mysql_copy_preconditions,
    build_plan,
    build_parser,
    resolve_target_url,
    safe_target_summary,
    source_snapshot,
)


class MysqlMigrationSafetyTestCase(unittest.TestCase):
    def test_migration_app_disables_background_and_startup_data_writes(self):
        self.assertFalse(MigrationConfig.SCHEDULER_ENABLED)
        self.assertFalse(MigrationConfig.STARTUP_DATA_REPAIRS_ENABLED)

    def test_migration_config_reuses_connection_options(self):
        with patch.dict(
            "os.environ",
            {"MYSQL_CONNECT_TIMEOUT": "17", "MYSQL_POOL_SIZE": "3"},
            clear=True,
        ):
            config = _migration_config(
                "mysql+pymysql://app:secret@127.0.0.1/medical_db"
            )

        self.assertEqual(
            config.SQLALCHEMY_ENGINE_OPTIONS["connect_args"]["connect_timeout"],
            17,
        )
        self.assertEqual(config.SQLALCHEMY_ENGINE_OPTIONS["pool_size"], 3)
        self.assertFalse(config.DATABASE_REQUIRE_TLS)

    def test_remote_migration_target_requires_verified_tls(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "requires verified TLS"):
                _migration_config(
                    "mysql+pymysql://app:secret@db.example/medical_db"
                )

        with patch.dict(
            "os.environ", {"MYSQL_SSL_CA": "trusted-ca.pem"}, clear=True
        ):
            config = _migration_config(
                "mysql+pymysql://app:secret@db.example/medical_db"
            )

        self.assertTrue(config.DATABASE_REQUIRE_TLS)
        self.assertEqual(
            config.SQLALCHEMY_ENGINE_OPTIONS["connect_args"]["ssl_ca"],
            "trusted-ca.pem",
        )

    def test_migration_config_removes_tls_url_options_before_connecting(self):
        with patch.dict("os.environ", {}, clear=True):
            config = _migration_config(
                "mysql+pymysql://app:secret@db.example/medical_db"
                "?ssl_ca=%2Fsecure%2Fca.pem"
                "&ssl_verify_cert=true&ssl_verify_identity=true"
            )

        sanitized_query = {
            key.lower(): value
            for key, value in make_url(config.SQLALCHEMY_DATABASE_URI).query.items()
        }
        self.assertEqual(sanitized_query, {})
        connect_args = config.SQLALCHEMY_ENGINE_OPTIONS["connect_args"]
        self.assertEqual(connect_args["charset"], "utf8mb4")
        self.assertEqual(connect_args["ssl_ca"], "/secure/ca.pem")
        self.assertTrue(connect_args["ssl_verify_cert"])
        self.assertTrue(connect_args["ssl_verify_identity"])

    def test_migration_config_rejects_connection_time_sql_or_disabled_tls(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "ssl_disabled"):
                _migration_config(
                    "mysql+pymysql://app:secret@127.0.0.1/medical_db"
                    "?ssl_disabled=true"
                )
            with self.assertRaisesRegex(RuntimeError, "init_command"):
                _migration_config(
                    "mysql+pymysql://app:secret@127.0.0.1/medical_db"
                    "?init_command=SET%20sql_mode%3D%27%27"
                )

    def test_mysql_copy_preconditions_accept_strict_transactional_innodb(self):
        _validate_mysql_copy_preconditions(
            sql_mode="STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION",
            autocommit=0,
            transaction_read_only=0,
            global_read_only=0,
            global_super_read_only=0,
            table_engines={"user": "InnoDB", "patient": "INNODB"},
            required_table_names=("user", "patient"),
            isolation_level="READ COMMITTED",
        )

    def test_mysql_copy_preconditions_reject_non_strict_mode(self):
        with self.assertRaisesRegex(RuntimeError, "STRICT_TRANS_TABLES"):
            _validate_mysql_copy_preconditions(
                sql_mode="NO_ENGINE_SUBSTITUTION",
                autocommit=0,
                transaction_read_only=0,
                global_read_only=0,
                global_super_read_only=0,
                table_engines={"user": "InnoDB"},
                required_table_names=("user",),
            )

    def test_mysql_copy_preconditions_reject_autocommit_or_read_only(self):
        valid = {
            "sql_mode": "STRICT_ALL_TABLES",
            "transaction_read_only": 0,
            "global_read_only": 0,
            "global_super_read_only": 0,
            "table_engines": {"user": "InnoDB"},
            "required_table_names": ("user",),
        }
        with self.assertRaisesRegex(RuntimeError, "autocommit must be disabled"):
            _validate_mysql_copy_preconditions(autocommit=1, **valid)

        read_only = dict(valid)
        read_only["global_super_read_only"] = 1
        with self.assertRaisesRegex(RuntimeError, "global super_read_only"):
            _validate_mysql_copy_preconditions(autocommit=0, **read_only)

        with self.assertRaisesRegex(RuntimeError, "AUTOCOMMIT isolation"):
            _validate_mysql_copy_preconditions(
                autocommit=0,
                isolation_level="AUTOCOMMIT",
                **valid,
            )

    def test_mysql_copy_preconditions_reject_non_innodb_or_missing_tables(self):
        valid = {
            "sql_mode": "STRICT_TRANS_TABLES",
            "autocommit": 0,
            "transaction_read_only": 0,
            "global_read_only": 0,
            "global_super_read_only": 0,
        }
        with self.assertRaisesRegex(RuntimeError, "sample=MYISAM"):
            _validate_mysql_copy_preconditions(
                table_engines={"sample": "MyISAM"},
                required_table_names=("sample",),
                **valid,
            )

        with self.assertRaisesRegex(RuntimeError, "missing modeled tables: patient"):
            _validate_mysql_copy_preconditions(
                table_engines={"user": "InnoDB"},
                required_table_names=("user", "patient"),
                **valid,
            )

    def test_only_modeled_destination_tables_are_selected_for_clearing(self):
        model_metadata = MetaData()
        Table("user", model_metadata, Column("id", Integer, primary_key=True))
        Table("patient", model_metadata, Column("id", Integer, primary_key=True))

        destination_metadata = MetaData()
        Table("user", destination_metadata, Column("id", Integer, primary_key=True))
        Table("patient", destination_metadata, Column("id", Integer, primary_key=True))
        Table(
            "operations_audit",
            destination_metadata,
            Column("id", Integer, primary_key=True),
        )
        Table(
            "alembic_version",
            destination_metadata,
            Column("id", Integer, primary_key=True),
        )

        selected = _modeled_destination_tables(model_metadata, destination_metadata)

        self.assertEqual(_modeled_table_names(model_metadata), {"user", "patient"})
        self.assertEqual({table.name for table in selected}, {"user", "patient"})
        self.assertNotIn("operations_audit", {table.name for table in selected})
        self.assertNotIn("alembic_version", {table.name for table in selected})

    def test_missing_modeled_table_is_not_selected(self):
        model_metadata = MetaData()
        Table("user", model_metadata, Column("id", Integer, primary_key=True))
        Table("patient", model_metadata, Column("id", Integer, primary_key=True))

        destination_metadata = MetaData()
        Table("user", destination_metadata, Column("id", Integer, primary_key=True))
        Table(
            "operations_audit",
            destination_metadata,
            Column("id", Integer, primary_key=True),
        )

        selected = _modeled_destination_tables(model_metadata, destination_metadata)

        self.assertEqual([table.name for table in selected], ["user"])

    def test_database_url_is_primary_and_summary_hides_password(self):
        url = resolve_target_url(
            {
                "DATABASE_URL": (
                    "mysql+pymysql://medical:super-secret@db.example:3307/clinic"
                    "?ssl_ca=query-secret"
                )
            }
        )

        self.assertEqual(url.host, "db.example")
        self.assertEqual(url.port, 3307)
        self.assertEqual(url.database, "clinic")
        self.assertEqual(url.query["charset"], "utf8mb4")
        summary = safe_target_summary(url)
        self.assertIn("medical:***@db.example:3307/clinic", summary)
        self.assertNotIn("super-secret", summary)
        self.assertNotIn("query-secret", summary)

    def test_database_url_query_overrides_are_rejected_during_resolution(self):
        for query in (
            "host=other.example",
            "database=other_db",
            "init_command=SELECT%201",
            "charset=",
            "charset=utf8mb4&charset=utf8mb4",
        ):
            with self.subTest(query=query):
                with self.assertRaises(RuntimeError):
                    resolve_target_url(
                        {
                            "DATABASE_URL": (
                                "mysql+pymysql://app:secret@127.0.0.1/medical_db?"
                                + query
                            )
                        }
                    )

    def test_matching_legacy_configuration_is_allowed(self):
        url = resolve_target_url(
            {
                "DATABASE_URL": "mysql+pymysql://app:secret@127.0.0.1/medical_db",
                "MYSQL_USER": "app",
                "MYSQL_PASSWORD": "secret",
                "MYSQL_HOST": "127.0.0.1",
                "MYSQL_DB": "medical_db",
            }
        )

        self.assertEqual(url.username, "app")
        self.assertEqual(url.database, "medical_db")

    def test_conflicting_legacy_configuration_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "conflicts"):
            resolve_target_url(
                {
                    "DATABASE_URL": "mysql+pymysql://app:one@db/medical_db",
                    "MYSQL_USER": "app",
                    "MYSQL_PASSWORD": "two",
                    "MYSQL_HOST": "db",
                    "MYSQL_DB": "medical_db",
                }
            )

    def test_legacy_configuration_remains_a_supported_fallback(self):
        url = resolve_target_url(
            {
                "MYSQL_USER": "legacy",
                "MYSQL_PASSWORD": "secret",
                "MYSQL_HOST": "mysql.internal",
                "MYSQL_PORT": "3308",
                "MYSQL_DB": "legacy_db",
            }
        )

        self.assertEqual(url.username, "legacy")
        self.assertEqual(url.host, "mysql.internal")
        self.assertEqual(url.port, 3308)
        self.assertEqual(url.database, "legacy_db")

    def test_partial_legacy_configuration_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "MYSQL_PASSWORD"):
            resolve_target_url({"MYSQL_HOST": "mysql.internal"})

    def test_destructive_execution_requires_both_flags(self):
        _validate_execution_flags(False, False)
        _validate_execution_flags(True, True, "a" * 64)

        with self.assertRaisesRegex(RuntimeError, "both --execute and --yes"):
            _validate_execution_flags(True, False)
        with self.assertRaisesRegex(RuntimeError, "only valid"):
            _validate_execution_flags(False, True)

    def test_execute_requires_matching_dry_run_source_hash(self):
        with self.assertRaisesRegex(RuntimeError, "requires --expected-source-sha256"):
            _validate_execution_flags(True, True)
        with self.assertRaisesRegex(RuntimeError, "64 hex"):
            _validate_execution_flags(True, True, "not-a-sha256")
        with self.assertRaisesRegex(RuntimeError, "changed after dry-run"):
            _assert_expected_source_sha256("a" * 64, "b" * 64)

        _assert_expected_source_sha256("a" * 64, "A" * 64)

    def test_parser_defaults_to_dry_run(self):
        args = build_parser().parse_args([])

        self.assertFalse(args.execute)
        self.assertFalse(args.yes)
        self.assertEqual(args.batch_size, 1000)
        self.assertIsNone(args.expected_source_sha256)

    def test_target_must_have_exactly_the_expected_alembic_head(self):
        engine = create_engine("sqlite:///:memory:")
        try:
            with engine.connect() as connection:
                with self.assertRaisesRegex(RuntimeError, "unversioned"):
                    _assert_target_alembic_head(connection, "current-head")

            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
                )
                connection.exec_driver_sql(
                    "INSERT INTO alembic_version (version_num) VALUES ('old-head')"
                )
            with engine.connect() as connection:
                with self.assertRaisesRegex(RuntimeError, "not at the required"):
                    _assert_target_alembic_head(connection, "current-head")

            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "UPDATE alembic_version SET version_num = 'current-head'"
                )
            with engine.connect() as connection:
                _assert_target_alembic_head(connection, "current-head")
        finally:
            engine.dispose()

    def test_source_snapshot_is_consistent_and_temporary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.db"
            with closing(sqlite3.connect(source_path)) as connection:
                connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
                connection.execute("INSERT INTO sample (id) VALUES (1)")
                connection.commit()

            with source_snapshot(source_path) as first_snapshot:
                first_hash = first_snapshot.sha256
            with source_snapshot(source_path) as unchanged_snapshot:
                self.assertEqual(unchanged_snapshot.sha256, first_hash)

            with source_snapshot(source_path) as snapshot:
                snapshot_path = snapshot.path
                self.assertTrue(snapshot_path.is_file())
                self.assertEqual(len(snapshot.sha256), 64)

                with closing(sqlite3.connect(source_path)) as connection:
                    connection.execute("INSERT INTO sample (id) VALUES (2)")
                    connection.commit()
                with closing(sqlite3.connect(snapshot_path)) as connection:
                    count = connection.execute(
                        "SELECT COUNT(*) FROM sample"
                    ).fetchone()[0]
                self.assertEqual(count, 1)

            self.assertFalse(snapshot_path.exists())
            with source_snapshot(source_path) as changed_snapshot:
                self.assertNotEqual(changed_snapshot.sha256, first_hash)

    def test_foreign_key_orphans_are_detected_from_model_metadata(self):
        model_metadata = MetaData()
        Table("parent", model_metadata, Column("id", Integer, primary_key=True))
        Table(
            "child",
            model_metadata,
            Column("id", Integer, primary_key=True),
            Column("parent_id", Integer, ForeignKey("parent.id")),
        )
        engine = create_engine("sqlite:///:memory:")
        try:
            model_metadata.create_all(engine)
            with engine.begin() as connection:
                connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
                connection.exec_driver_sql(
                    "INSERT INTO child (id, parent_id) VALUES (1, 99)"
                )
            with engine.connect() as connection:
                reflected = _reflect_required_tables(
                    connection, model_metadata, "test database"
                )
                findings = _foreign_key_orphans(
                    connection, model_metadata, reflected
                )

            self.assertEqual(findings, {"child.parent_id -> parent.id": 1})
        finally:
            engine.dispose()

    def test_cross_boundary_foreign_keys_are_detected_in_both_directions(self):
        model_metadata = MetaData()
        Table(
            "visit",
            model_metadata,
            Column("id", Integer, primary_key=True),
            Column("catalog_id", Integer),
        )

        target_metadata = MetaData()
        Table(
            "extension_catalog",
            target_metadata,
            Column("id", Integer, primary_key=True),
        )
        Table(
            "visit",
            target_metadata,
            Column("id", Integer, primary_key=True),
            Column(
                "catalog_id",
                Integer,
                ForeignKey("extension_catalog.id"),
            ),
        )
        Table(
            "external_audit",
            target_metadata,
            Column("id", Integer, primary_key=True),
            Column("visit_id", Integer, ForeignKey("visit.id")),
        )

        self.assertEqual(
            _cross_boundary_foreign_keys(model_metadata, target_metadata),
            (
                "external_audit.visit_id -> visit.id",
                "visit.catalog_id -> extension_catalog.id",
            ),
        )

    def test_dry_run_rejects_extension_table_referencing_modeled_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_metadata = MetaData()
            visit = Table(
                "visit",
                model_metadata,
                Column("id", Integer, primary_key=True),
            )
            source_path = Path(temp_dir) / "source.db"
            target_path = Path(temp_dir) / "target.db"
            source_engine = create_engine(f"sqlite:///{source_path.as_posix()}")
            target_engine = create_engine(f"sqlite:///{target_path.as_posix()}")
            try:
                model_metadata.create_all(source_engine)
                model_metadata.create_all(target_engine)
                with source_engine.begin() as connection:
                    connection.execute(visit.insert(), {"id": 1})
                with target_engine.begin() as connection:
                    connection.execute(visit.insert(), {"id": 99})
                    connection.exec_driver_sql(
                        "CREATE TABLE external_audit ("
                        "id INTEGER PRIMARY KEY, "
                        "visit_id INTEGER NOT NULL, "
                        "FOREIGN KEY (visit_id) REFERENCES visit(id))"
                    )
                    connection.exec_driver_sql(
                        "INSERT INTO external_audit (id, visit_id) VALUES (1, 99)"
                    )
                    connection.exec_driver_sql(
                        "CREATE TABLE alembic_version "
                        "(version_num VARCHAR(32) NOT NULL)"
                    )
                    connection.exec_driver_sql(
                        "INSERT INTO alembic_version (version_num) "
                        "VALUES ('test-head')"
                    )

                with source_snapshot(source_path) as snapshot:
                    with self.assertRaisesRegex(
                        RuntimeError,
                        r"external_audit\.visit_id -> visit\.id",
                    ):
                        build_plan(
                            snapshot.path,
                            target_engine,
                            model_metadata,
                            expected_alembic_head="test-head",
                        )

                with target_engine.connect() as connection:
                    visit_count = connection.exec_driver_sql(
                        "SELECT COUNT(*) FROM visit"
                    ).scalar_one()
                    audit_count = connection.exec_driver_sql(
                        "SELECT COUNT(*) FROM external_audit"
                    ).scalar_one()
                self.assertEqual((visit_count, audit_count), (1, 1))
            finally:
                source_engine.dispose()
                target_engine.dispose()

    def test_actual_fk_orphan_scan_includes_extension_relationships(self):
        metadata = MetaData()
        Table(
            "extension_parent",
            metadata,
            Column("id", Integer, primary_key=True),
        )
        Table(
            "extension_child",
            metadata,
            Column("id", Integer, primary_key=True),
            Column(
                "parent_id",
                Integer,
                ForeignKey("extension_parent.id"),
            ),
        )
        engine = create_engine("sqlite:///:memory:")
        try:
            metadata.create_all(engine)
            with engine.begin() as connection:
                connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
                connection.exec_driver_sql(
                    "INSERT INTO extension_child (id, parent_id) VALUES (1, 42)"
                )
            with engine.connect() as connection:
                reflected = MetaData()
                reflected.reflect(bind=connection)
                findings = _actual_foreign_key_orphans(connection, reflected)

            self.assertEqual(
                findings,
                {
                    "extension_child.parent_id -> extension_parent.id": 1,
                },
            )
        finally:
            engine.dispose()

    def test_source_columns_missing_from_target_are_rejected(self):
        model_metadata = MetaData()
        Table("sample", model_metadata, Column("id", Integer, primary_key=True))
        source_metadata = MetaData()
        Table(
            "sample",
            source_metadata,
            Column("id", Integer, primary_key=True),
            Column("legacy_value", String(20)),
        )
        target_metadata = MetaData()
        Table("sample", target_metadata, Column("id", Integer, primary_key=True))

        with self.assertRaisesRegex(RuntimeError, "cannot preserve source columns"):
            _validate_copy_columns(
                model_metadata, source_metadata, target_metadata
            )

    def test_target_only_columns_are_rejected_before_clearing(self):
        model_metadata = MetaData()
        Table("sample", model_metadata, Column("id", Integer, primary_key=True))
        source_metadata = MetaData()
        Table("sample", source_metadata, Column("id", Integer, primary_key=True))
        target_metadata = MetaData()
        Table(
            "sample",
            target_metadata,
            Column("id", Integer, primary_key=True),
            Column("extension_value", String(20)),
        )

        with self.assertRaisesRegex(RuntimeError, "without data loss"):
            _validate_copy_columns(
                model_metadata, source_metadata, target_metadata
            )

    def test_records_are_read_in_bounded_batches(self):
        metadata = MetaData()
        sample = Table(
            "sample",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("value", String(20)),
        )
        engine = create_engine("sqlite:///:memory:")
        try:
            metadata.create_all(engine)
            with engine.begin() as connection:
                connection.execute(
                    sample.insert(),
                    [{"id": value, "value": str(value)} for value in range(1, 6)],
                )
            with engine.connect() as connection:
                batches = list(
                    _record_batches(
                        connection,
                        sample,
                        {"id", "value"},
                        batch_size=2,
                    )
                )

            self.assertEqual([len(batch) for batch in batches], [2, 2, 1])
            self.assertEqual(
                [row["id"] for batch in batches for row in batch],
                [1, 2, 3, 4, 5],
            )
        finally:
            engine.dispose()

    def test_preflight_plan_reports_source_and_target_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_metadata = MetaData()
            sample = Table(
                "sample",
                model_metadata,
                Column("id", Integer, primary_key=True),
            )
            source_path = Path(temp_dir) / "source.db"
            target_path = Path(temp_dir) / "target.db"
            source_engine = create_engine(f"sqlite:///{source_path.as_posix()}")
            target_engine = create_engine(f"sqlite:///{target_path.as_posix()}")
            try:
                model_metadata.create_all(source_engine)
                model_metadata.create_all(target_engine)
                with source_engine.begin() as connection:
                    connection.execute(sample.insert(), [{"id": 1}, {"id": 2}])
                with target_engine.begin() as connection:
                    connection.execute(sample.insert(), {"id": 9})
                    connection.exec_driver_sql(
                        "CREATE TABLE alembic_version "
                        "(version_num VARCHAR(32) NOT NULL)"
                    )
                    connection.exec_driver_sql(
                        "INSERT INTO alembic_version (version_num) "
                        "VALUES ('test-head')"
                    )

                with source_snapshot(source_path) as snapshot:
                    plan = build_plan(
                        snapshot.path,
                        target_engine,
                        model_metadata,
                        expected_alembic_head="test-head",
                    )

                self.assertEqual(plan.table_names, ("sample",))
                self.assertEqual(plan.source_stats["sample"].row_count, 2)
                self.assertEqual(plan.target_stats["sample"].row_count, 1)
            finally:
                source_engine.dispose()
                target_engine.dispose()

    def test_row_count_and_primary_key_reconciliation(self):
        metadata = MetaData()
        sample = Table(
            "sample",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("value", String(20)),
        )
        engine = create_engine("sqlite:///:memory:")
        try:
            metadata.create_all(engine)
            with engine.begin() as connection:
                connection.execute(
                    sample.insert(),
                    [{"id": 1, "value": "a"}, {"id": 2, "value": "b"}],
                )
            with engine.connect() as connection:
                expected = _table_stats(connection, metadata, ("sample",))

            _assert_reconciled(expected, expected)
            with self.assertRaisesRegex(RuntimeError, "row count"):
                _assert_reconciled(
                    expected,
                    {
                        "sample": TableStats(
                            row_count=1,
                            primary_key_digest=expected[
                                "sample"
                            ].primary_key_digest,
                        )
                    },
                )
            with self.assertRaisesRegex(RuntimeError, "primary-key digest"):
                _assert_reconciled(
                    expected,
                    {
                        "sample": TableStats(
                            row_count=2,
                            primary_key_digest="different",
                        )
                    },
                )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
