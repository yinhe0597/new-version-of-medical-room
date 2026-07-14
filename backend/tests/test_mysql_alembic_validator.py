import os
from types import SimpleNamespace
import unittest
from unittest import mock

from sqlalchemy.dialects import mysql

from scripts import validate_mysql_alembic as validator


class RecordingAdmin:
    def __init__(self):
        self.mutations = []
        self.reads = []
        self.fail_mutation_labels = {}
        self.existing_databases = set()
        self.target_checks = []
        self.target_failure = None

    def assert_target(self, label, **kwargs):
        self.target_checks.append((label, kwargs))
        if self.target_failure is not None:
            raise self.target_failure
        return {"server_uuid": kwargs["expected_server_uuid"], "log_bin": "0"}

    def run_mutation(self, sql, label, **kwargs):
        self.mutations.append((sql, label, kwargs))
        failure = self.fail_mutation_labels.get(label)
        if failure is not None:
            raise failure
        if label.startswith("create database "):
            self.existing_databases.add(label.removeprefix("create database "))
        if label.startswith("drop database "):
            self.existing_databases.discard(label.removeprefix("drop database "))
        return ""

    def run(self, sql, label):
        self.reads.append((sql, label))
        if label.startswith("check database "):
            database = label.removeprefix("check database ")
            return f"{int(database in self.existing_databases)}\n"
        if label.startswith("verify database ownership "):
            return "2\n"
        if label.startswith("verify temporary account "):
            return "1\t1\n"
        raise AssertionError(f"Unexpected fake admin read: {label}")

    def run_guarded(self, sql, label, **_kwargs):
        return self.run(sql, label)


def deterministic_resources(admin, scenarios=("fresh",)):
    with (
        mock.patch.object(
            validator.secrets,
            "token_hex",
            side_effect=("a" * 32, "b" * 64),
        ),
        mock.patch.object(
            validator.secrets,
            "token_urlsafe",
            return_value="c" * 32,
        ),
    ):
        return validator.TemporaryResources(
            admin,
            expected_server_uuid="12345678-1234-1234-1234-123456789abc",
            allow_binlog=False,
            scenarios=scenarios,
            account_host="172.18.0.1",
        )


class MysqlAdminTestCase(unittest.TestCase):
    def test_preflight_reads_and_validates_server_observed_client_host(self):
        values = (
            "12345678-1234-1234-1234-123456789abc",
            "mysql-container",
            "3306",
            "8.0.36",
            "MySQL Community Server - GPL",
            "InnoDB",
            "utf8mb4",
            "utf8mb4_0900_ai_ci",
            "STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION",
            "0",
            "0",
            "1",
            "0",
            "172.18.0.1",
        )
        admin = validator.MysqlAdmin(
            "codex-medroom", "127.0.0.1", 3306, "mysql.exe"
        )
        with mock.patch.object(admin, "run", return_value="\t".join(values)) as run:
            details = admin.preflight()

        self.assertEqual(details["client_host"], "172.18.0.1")
        self.assertIn("SUBSTRING_INDEX(USER(), '@', -1)", run.call_args.args[0])

    def test_account_host_validation_rejects_wildcards_and_sql_metacharacters(self):
        for host in ("172.18.0.1", "::1", "runner-1.internal", "localhost"):
            with self.subTest(valid=host):
                self.assertEqual(validator.validated_account_host(host), host)

        for host in (
            "",
            "%",
            "172.18.%",
            "runner_host",
            "host' OR '1'='1",
            "host\\name",
            "-invalid.example",
        ):
            with self.subTest(invalid=host):
                with self.assertRaises(ValueError):
                    validator.validated_account_host(host)

    def test_run_uses_login_path_only_and_sends_sql_through_stdin(self):
        completed = SimpleNamespace(returncode=0, stdout="ok\n", stderr="")
        sql = "CREATE USER 'temporary' IDENTIFIED BY 'stdin-secret';"

        with (
            mock.patch.dict(
                os.environ,
                {
                    "KEEP_ME": "yes",
                    "MYSQL_PWD": "environment-secret",
                    "MYSQL_DEBUG": "trace-file",
                    "MYSQL_HOME": "unsafe-options",
                    "TEST_LOGIN_FILE": "alternate-login-file",
                },
                clear=True,
            ),
            mock.patch.object(
                validator.subprocess, "run", return_value=completed
            ) as run_mock,
        ):
            admin = validator.MysqlAdmin(
                "codex-medroom", "127.0.0.1", 3306, "mysql.exe"
            )
            self.assertEqual(admin.run(sql, "test stdin"), "ok\n")

        args, kwargs = run_mock.call_args
        command = args[0]
        self.assertEqual(command[0:3], [
            "mysql.exe",
            "--no-defaults",
            "--login-path=codex-medroom",
        ])
        self.assertIn("--disable-reconnect", command)
        self.assertNotIn("-e", command)
        self.assertFalse(any("stdin-secret" in part for part in command))
        self.assertEqual(kwargs["input"], sql)
        self.assertEqual(kwargs["env"]["KEEP_ME"], "yes")
        self.assertFalse(
            any(key.upper().startswith("MYSQL_") for key in kwargs["env"])
        )
        self.assertNotIn("TEST_LOGIN_FILE", kwargs["env"])

    def test_cleanup_mutation_allows_configuration_drift_but_checks_uuid(self):
        admin = validator.MysqlAdmin(
            "codex-medroom", "127.0.0.1", 3306, "mysql.exe"
        )
        details = {
            "server_uuid": "expected",
            "log_bin": "1",
        }
        with (
            mock.patch.object(admin, "preflight", return_value=details) as preflight,
            mock.patch.object(admin, "run", return_value="") as run,
        ):
            admin.run_mutation(
                "DROP DATABASE `temporary`;",
                "cleanup",
                expected_server_uuid="expected",
                allow_binlog=False,
                cleanup=True,
            )

        preflight.assert_called_once_with(cleanup=True)
        run.assert_called_once()
        guarded_sql = run.call_args.args[0]
        self.assertIn("PREPARE medmig_guard_stmt", guarded_sql)
        self.assertLess(
            guarded_sql.index("PREPARE medmig_guard_stmt"),
            guarded_sql.index("DROP DATABASE"),
        )


class TemporaryResourcesTestCase(unittest.TestCase):
    def test_selected_scenario_uses_mysql_safe_names_and_account_marker(self):
        admin = RecordingAdmin()
        resources = deterministic_resources(admin, scenarios=("history",))

        self.assertLessEqual(len(resources.user), 32)
        self.assertEqual(set(resources.scenario_databases), {"history"})
        self.assertEqual(resources.account_hosts, ("172.18.0.1",))
        resources.create()

        statements = "\n".join(sql for sql, _label, _kwargs in admin.mutations)
        self.assertIn(resources.scenario_databases["history"], statements)
        self.assertNotIn("_fresh", statements)
        self.assertNotIn("_retry", statements)
        first_database_create = next(
            index
            for index, (_sql, label, _kwargs) in enumerate(admin.mutations)
            if label.startswith("create database ")
        )
        account_creates = [
            index
            for index, (_sql, label, _kwargs) in enumerate(admin.mutations)
            if label.startswith("create temporary account ")
        ]
        self.assertTrue(account_creates)
        self.assertLess(max(account_creates), first_database_create)
        create_user_sql = admin.mutations[account_creates[0]][0]
        self.assertIn('"medmig_databases"', create_user_sql)
        self.assertIn(resources.databases[0], create_user_sql)
        self.assertIn(resources.owner_token, create_user_sql)
        self.assertIn(f"'{resources.user}'@'172.18.0.1'", create_user_sql)
        self.assertNotIn("@'%'", statements)

    def test_cleanup_continues_databases_and_retains_markers_after_interrupt(self):
        admin = RecordingAdmin()
        resources = deterministic_resources(admin, scenarios=("fresh", "history"))
        resources.attempted_databases.extend(resources.databases)
        resources.created_databases.extend(resources.databases)
        admin.existing_databases.update(resources.databases)
        resources.attempted_accounts.extend(resources.account_hosts)
        resources.created_accounts.extend(resources.account_hosts)
        database = resources.databases[-1]
        admin.fail_mutation_labels[f"drop database {database}"] = KeyboardInterrupt()

        with self.assertRaisesRegex(RuntimeError, "KeyboardInterrupt"):
            resources.cleanup()

        mutation_labels = [label for _sql, label, _kwargs in admin.mutations]
        self.assertIn(f"drop database {database}", mutation_labels)
        self.assertIn(f"drop database {resources.databases[0]}", mutation_labels)
        self.assertIn("lock temporary account 172.18.0.1", mutation_labels)
        self.assertNotIn("drop temporary account 172.18.0.1", mutation_labels)
        cleanup_flags = [
            kwargs["cleanup"]
            for _sql, label, kwargs in admin.mutations
            if label.startswith("drop ")
        ]
        self.assertTrue(all(cleanup_flags))

    def test_unowned_preexisting_account_is_not_dropped(self):
        admin = RecordingAdmin()
        resources = deterministic_resources(admin)
        resources.attempted_accounts.append(resources.account_hosts[0])

        def unowned_account(_sql, label):
            admin.reads.append((_sql, label))
            return "1\t0\n"

        admin.run = unowned_account
        resources.cleanup()

        self.assertFalse(
            any(label.startswith("drop temporary account") for _sql, label, _kwargs in admin.mutations)
        )

    def test_cleanup_does_not_accept_absence_from_a_different_server(self):
        admin = RecordingAdmin()
        resources = deterministic_resources(admin)
        database = resources.databases[0]
        resources.attempted_databases.append(database)
        admin.target_failure = RuntimeError("MySQL server UUID changed")

        with self.assertRaisesRegex(RuntimeError, "UUID changed"):
            resources.cleanup()

        self.assertFalse(admin.reads)
        self.assertFalse(admin.mutations)


class SchemaParityHelperTestCase(unittest.TestCase):
    @staticmethod
    def _record_sql(callback, stop_after=None):
        calls = []

        class RecordingComplete(Exception):
            pass

        class RecordingConnection:
            def execute(self, statement, parameters=None):
                calls.append((statement, parameters))
                if stop_after and str(statement).startswith(stop_after):
                    raise RecordingComplete

        try:
            callback(RecordingConnection())
        except RecordingComplete:
            pass
        return calls

    def test_unicode_fixture_quotes_mysql_reserved_usage_column(self):
        calls = []

        class FixtureCaptured(Exception):
            pass

        def capture_fixture(_resources, _database, callback):
            calls.extend(
                self._record_sql(callback, "INSERT INTO prescription_item")
            )
            raise FixtureCaptured

        with mock.patch.object(
            validator,
            "run_sql",
            side_effect=capture_fixture,
        ):
            with self.assertRaises(FixtureCaptured):
                validator.insert_unicode_fixture(object(), "fixture")

        statements = [str(statement) for statement, _parameters in calls]
        prescription_insert = next(
            statement
            for statement in statements
            if statement.startswith("INSERT INTO prescription_item")
        )
        self.assertIn("drug_id, `usage`, quantity", prescription_insert)

    def test_history_fixture_binds_json_without_creating_numeric_parameter(self):
        calls = []
        with (
            mock.patch.object(validator, "run_upgrade"),
            mock.patch.object(validator, "migration_app") as migration_app,
            mock.patch.object(validator, "_sync_model_schema"),
            mock.patch.object(
                validator,
                "run_sql",
                side_effect=lambda _resources, _database, callback: calls.extend(
                    self._record_sql(callback)
                ),
            ),
        ):
            migration_app.return_value.__enter__.return_value = object()
            validator.setup_history(object(), "fixture")

        parked_statement, parameters = next(
            (statement, parameters)
            for statement, parameters in calls
            if str(statement).startswith("INSERT INTO parked_visit")
        )
        self.assertEqual(set(parked_statement._bindparams), {"items_json", "expires_at"})
        self.assertEqual(parameters["items_json"], '[{"drug_id":1}]')

    def test_history_extra_column_contract_matches_ture_database(self):
        self.assertEqual(
            sum(len(columns) for columns in validator.HISTORY_EXTRA_COLUMNS.values()),
            22,
        )
        declared = {
            (table_name, column_name)
            for table_name, columns in validator.HISTORY_EXTRA_COLUMNS.items()
            for column_name in columns
        }
        self.assertEqual(declared, set(validator.EXTRA_COLUMN_SPECS))

    def test_boolean_default_is_accepted_and_tinytext_is_rejected(self):
        validator.validate_extra_column(
            "drug",
            "is_herb",
            {
                "type": mysql.TINYINT(display_width=1),
                "nullable": True,
                "default": "0",
            },
        )
        with self.assertRaisesRegex(AssertionError, "unexpected type"):
            validator.validate_extra_column(
                "visit",
                "tcm_diagnosis_desc",
                {
                    "type": mysql.TINYTEXT(),
                    "nullable": True,
                    "default": None,
                },
            )


if __name__ == "__main__":
    unittest.main()
