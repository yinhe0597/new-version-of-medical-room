import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.engine import make_url

from backend.app import create_app, create_migration_app
from backend.app.models import Drug
from backend.app.utils.query import nulls_last_asc
from backend.runtime_secrets import SECRET_NAMES, ensure_runtime_secrets
from backend.config import (
    _database_requires_tls,
    _engine_configuration,
    _engine_options,
    _resolve_database_uri,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class RuntimeSecretsTestCase(unittest.TestCase):
    def test_generated_secrets_are_stable_across_repeated_loads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = ensure_runtime_secrets(temp_dir, {})
            second = ensure_runtime_secrets(temp_dir, {})

            self.assertEqual(first, second)
            for name in SECRET_NAMES:
                self.assertGreaterEqual(len(first[name]), 32)

            with open(
                os.path.join(temp_dir, ".runtime-secrets.json"),
                "r",
                encoding="utf-8",
            ) as handle:
                self.assertEqual(json.load(handle), first)

    def test_concurrent_loads_share_one_secret_pair(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(
                    executor.map(
                        lambda _: ensure_runtime_secrets(temp_dir, {}),
                        range(8),
                    )
                )

            self.assertTrue(all(result == results[0] for result in results))

    def test_concurrent_processes_share_one_secret_pair(self):
        script = (
            "import json; "
            "from backend.config import Config; "
            "print(json.dumps({"
            "'SECRET_KEY': Config.SECRET_KEY, "
            "'JWT_SECRET_KEY': Config.JWT_SECRET_KEY"
            "}, sort_keys=True))"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            child_env = os.environ.copy()
            for name in SECRET_NAMES:
                child_env.pop(name, None)
            child_env["APP_ROOT"] = temp_dir
            child_env["PYTHON_DOTENV_DISABLED"] = "1"
            processes = [
                subprocess.Popen(
                    [sys.executable, "-c", script],
                    cwd=PROJECT_ROOT,
                    env=child_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(4)
            ]
            results = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, stderr)
                results.append(json.loads(stdout))

            self.assertTrue(all(result == results[0] for result in results))

    def test_explicit_placeholder_secret_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(RuntimeError):
                ensure_runtime_secrets(
                    temp_dir,
                    {
                        "SECRET_KEY": "replace-with-at-least-32-random-characters",
                        "JWT_SECRET_KEY": "valid-jwt-secret-value-with-at-least-32-characters",
                    },
                )


class PortableOrderingTestCase(unittest.TestCase):
    def test_nulls_last_ordering_compiles_for_mysql_and_sqlite(self):
        statement = select(Drug.id).order_by(
            *nulls_last_asc(Drug.storage_location),
            Drug.id.desc(),
        )

        for dialect in (mysql.dialect(), sqlite.dialect()):
            sql = str(statement.compile(dialect=dialect)).upper()
            self.assertNotIn("NULLS LAST", sql)
            self.assertIn("CASE WHEN", sql)
            self.assertIn("IS NULL", sql)


class ExternalDatabaseConfigurationTestCase(unittest.TestCase):
    def _load_config_in_subprocess(self, updates):
        child_env = os.environ.copy()
        child_env.update(updates)
        child_env.pop("SQLALCHEMY_DATABASE_URI", None)
        return subprocess.run(
            [sys.executable, "-c", "from backend.config import Config"],
            cwd=PROJECT_ROOT,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_mysql_config_defaults_to_versioned_schema_without_runtime_sync(self):
        script = (
            "import json; from backend.config import Config; "
            "print(json.dumps({"
            "'head': Config.REQUIRE_ALEMBIC_HEAD, "
            "'sync': Config.RUNTIME_SCHEMA_SYNC_ENABLED, "
            "'preflight': Config.PRODUCTION_DATABASE_PREFLIGHT_ENABLED}))"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            child_env = os.environ.copy()
            child_env.update({
                "APP_ROOT": temp_dir,
                "PYTHON_DOTENV_DISABLED": "1",
                "DATABASE_URL": (
                    "mysql+pymysql://app:secret@127.0.0.1:3306/medical_db"
                ),
            })
            child_env.pop("SQLALCHEMY_DATABASE_URI", None)
            for name in (
                "REQUIRE_ALEMBIC_HEAD",
                "RUNTIME_SCHEMA_SYNC_ENABLED",
                "PRODUCTION_DATABASE_PREFLIGHT_ENABLED",
            ):
                child_env.pop(name, None)
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=PROJECT_ROOT,
                env=child_env,
                capture_output=True,
                text=True,
                timeout=20,
                check=True,
            )

        self.assertEqual(
            json.loads(completed.stdout),
            {"head": True, "sync": False, "preflight": True},
        )

    def test_maintenance_write_switches_are_loaded_from_environment(self):
        script = (
            "import json; from backend.config import Config; "
            "print(json.dumps({"
            "'scheduler': Config.SCHEDULER_ENABLED, "
            "'repairs': Config.STARTUP_DATA_REPAIRS_ENABLED, "
            "'bootstrap': Config.BOOTSTRAP_USERS_ENABLED}))"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            child_env = os.environ.copy()
            child_env.update(
                {
                    "APP_ROOT": temp_dir,
                    "PYTHON_DOTENV_DISABLED": "1",
                    "DATABASE_URL": "sqlite:///maintenance-test.db",
                    "SCHEDULER_ENABLED": "0",
                    "STARTUP_DATA_REPAIRS_ENABLED": "0",
                    "BOOTSTRAP_USERS_ENABLED": "0",
                }
            )
            child_env.pop("SQLALCHEMY_DATABASE_URI", None)
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=PROJECT_ROOT,
                env=child_env,
                capture_output=True,
                text=True,
                timeout=20,
                check=True,
            )

        self.assertEqual(
            json.loads(completed.stdout),
            {"scheduler": False, "repairs": False, "bootstrap": False},
        )

    def test_conflicting_database_environment_variables_are_rejected(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "mysql+pymysql://app:secret@primary/medical_db",
                "SQLALCHEMY_DATABASE_URI": (
                    "mysql+pymysql://app:secret@stale-host/medical_db"
                ),
            },
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "conflicts"):
                _resolve_database_uri()

    def test_remote_mysql_requires_tls_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_REQUIRE_TLS", None)
            self.assertTrue(
                _database_requires_tls(
                    "mysql+pymysql://user:secret@db.example.test/medical_db"
                )
            )
            self.assertFalse(
                _database_requires_tls(
                    "mysql+pymysql://user:secret@127.0.0.1/medical_db"
                )
            )

    def test_all_mysql_targets_reject_unsafe_runtime_switches(self):
        safe = {
            "APP_ROOT": tempfile.gettempdir(),
            "PYTHON_DOTENV_DISABLED": "1",
            "DATABASE_URL": "mysql+pymysql://app:secret@127.0.0.1/medical_db",
            "REQUIRE_ALEMBIC_HEAD": "1",
            "RUNTIME_SCHEMA_SYNC_ENABLED": "0",
            "PRODUCTION_DATABASE_PREFLIGHT_ENABLED": "1",
        }
        unsafe_values = {
            "REQUIRE_ALEMBIC_HEAD": "0",
            "RUNTIME_SCHEMA_SYNC_ENABLED": "1",
            "PRODUCTION_DATABASE_PREFLIGHT_ENABLED": "0",
        }
        for name, value in unsafe_values.items():
            with self.subTest(name=name):
                completed = self._load_config_in_subprocess({**safe, name: value})
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn(name, completed.stderr)

    def test_migration_backup_max_age_has_a_bounded_range(self):
        base = {
            "APP_ROOT": tempfile.gettempdir(),
            "PYTHON_DOTENV_DISABLED": "1",
            "DATABASE_URL": "mysql+pymysql://app:secret@127.0.0.1/medical_db",
            "REQUIRE_ALEMBIC_HEAD": "1",
            "RUNTIME_SCHEMA_SYNC_ENABLED": "0",
            "PRODUCTION_DATABASE_PREFLIGHT_ENABLED": "1",
        }
        valid = self._load_config_in_subprocess(
            {**base, "MIGRATION_BACKUP_MAX_AGE_MINUTES": "60"}
        )
        self.assertEqual(valid.returncode, 0, valid.stderr)
        for value in ("0", "1441", "not-an-integer"):
            with self.subTest(value=value):
                invalid = self._load_config_in_subprocess(
                    {**base, "MIGRATION_BACKUP_MAX_AGE_MINUTES": value}
                )
                self.assertNotEqual(invalid.returncode, 0)
                self.assertIn("MIGRATION_BACKUP_MAX_AGE_MINUTES", invalid.stderr)

    def test_remote_mysql_rejects_explicit_plaintext_policy(self):
        completed = self._load_config_in_subprocess(
            {
                "APP_ROOT": tempfile.gettempdir(),
                "PYTHON_DOTENV_DISABLED": "1",
                "DATABASE_URL": "mysql+pymysql://app:secret@db.example.test/medical_db",
                "DATABASE_REQUIRE_TLS": "0",
                "REQUIRE_ALEMBIC_HEAD": "1",
                "RUNTIME_SCHEMA_SYNC_ENABLED": "0",
                "PRODUCTION_DATABASE_PREFLIGHT_ENABLED": "1",
            }
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("DATABASE_REQUIRE_TLS", completed.stderr)

    def test_mysql_engine_options_include_bounded_timeouts_and_pooling(self):
        names = {
            "MYSQL_CONNECT_TIMEOUT",
            "MYSQL_READ_TIMEOUT",
            "MYSQL_WRITE_TIMEOUT",
            "MYSQL_POOL_RECYCLE",
            "MYSQL_POOL_TIMEOUT",
            "MYSQL_POOL_SIZE",
            "MYSQL_MAX_OVERFLOW",
            "MYSQL_SSL_CA",
            "MYSQL_SSL_CERT",
            "MYSQL_SSL_KEY",
        }
        with patch.dict(os.environ, {"MYSQL_SSL_CA": "/secure/ca.pem"}, clear=False):
            for name in names:
                if name != "MYSQL_SSL_CA":
                    os.environ.pop(name, None)
            options = _engine_options(
                "mysql+pymysql://user:secret@db.example.test/medical_db"
            )

        self.assertTrue(options["pool_pre_ping"])
        self.assertEqual(options["pool_recycle"], 1800)
        self.assertEqual(options["pool_size"], 5)
        self.assertEqual(options["connect_args"]["connect_timeout"], 10)
        self.assertEqual(options["connect_args"]["read_timeout"], 30)
        self.assertTrue(options["connect_args"]["ssl_verify_identity"])

    def test_remote_mysql_without_verified_tls_is_rejected_before_connecting(self):
        with patch.dict(os.environ, {}, clear=False):
            for name in ("MYSQL_SSL_CA", "MYSQL_SSL_CERT", "MYSQL_SSL_KEY"):
                os.environ.pop(name, None)
            with self.assertRaisesRegex(RuntimeError, "requires verified TLS"):
                _engine_options(
                    "mysql+pymysql://user:secret@db.example.test/medical_db"
                )

    def test_url_ca_enables_certificate_and_hostname_verification(self):
        with patch.dict(os.environ, {}, clear=False):
            for name in ("MYSQL_SSL_CA", "MYSQL_SSL_CERT", "MYSQL_SSL_KEY"):
                os.environ.pop(name, None)
            options = _engine_options(
                "mysql+pymysql://user:secret@db.example.test/medical_db"
                "?ssl_ca=%2Fsecure%2Fca.pem"
            )

        self.assertTrue(options["connect_args"]["ssl_verify_cert"])
        self.assertTrue(options["connect_args"]["ssl_verify_identity"])

    def test_tls_url_options_are_removed_and_mapped_to_direct_arguments(self):
        uri, options = _engine_configuration(
            "mysql+pymysql://user:secret@db.example.test/medical_db"
            "?charset=utf8mb4&ssl_ca=%2Fsecure%2Fca.pem"
            "&ssl_cert=client.pem&ssl_key=client-key.pem"
            "&ssl_verify_cert=1&ssl_verify_identity=true",
            {"DATABASE_REQUIRE_TLS": "1"},
        )

        self.assertEqual(dict(make_url(uri).query), {})
        args = options["connect_args"]
        self.assertEqual(args["ssl_ca"], "/secure/ca.pem")
        self.assertEqual(args["ssl_cert"], "client.pem")
        self.assertEqual(args["ssl_key"], "client-key.pem")
        self.assertTrue(args["ssl_verify_cert"])
        self.assertTrue(args["ssl_verify_identity"])

    def test_mysql_url_rejects_all_query_override_options(self):
        override_options = {
            "host": "127.0.0.1",
            "port": "3307",
            "user": "other",
            "username": "other",
            "password": "other-secret",
            "database": "other_db",
            "db": "other_db",
            "connect_timeout": "300",
            "read_timeout": "300",
            "write_timeout": "300",
            "autocommit": "true",
            "init_command": "SELECT%201",
            "unknown_option": "value",
        }
        for name, value in override_options.items():
            with self.subTest(name=name):
                with self.assertRaisesRegex(RuntimeError, "unsupported query option"):
                    _engine_configuration(
                        "mysql+pymysql://user:secret@127.0.0.1/medical_db"
                        f"?{name}={value}",
                        {},
                    )

    def test_mysql_url_rejects_blank_duplicate_or_invalid_options(self):
        invalid_queries = (
            "charset=utf8",
            "charset=",
            "charset=utf8mb4&charset=utf8mb4",
            "Charset=utf8mb4&charset=utf8mb4",
            "unix_socket=",
            "unix_socket=%2Ftmp%2Fmysql.sock&unix_socket=%2Ftmp%2Fother.sock",
            "charset=%20utf8mb4",
            "charset=utf8mb4%00",
            "charset=%ZZ",
        )
        for query in invalid_queries:
            with self.subTest(query=query):
                with self.assertRaises(RuntimeError):
                    _engine_configuration(
                        "mysql+pymysql://user:secret@/medical_db?" + query,
                        {},
                    )

        with self.assertRaisesRegex(RuntimeError, "authority host or port"):
            _engine_configuration(
                "mysql+pymysql://user:secret@127.0.0.1/medical_db"
                "?unix_socket=%2Ftmp%2Fmysql.sock",
                {},
            )

    def test_mysql_unix_socket_is_moved_to_direct_connection_arguments(self):
        uri, options = _engine_configuration(
            "mysql+pymysql://user:secret@/medical_db"
            "?charset=utf8mb4&unix_socket=%2Fvar%2Frun%2Fmysqld%2Fmysqld.sock",
            {},
        )

        self.assertEqual(dict(make_url(uri).query), {})
        self.assertIsNone(make_url(uri).host)
        self.assertEqual(
            options["connect_args"]["unix_socket"],
            "/var/run/mysqld/mysqld.sock",
        )
        self.assertEqual(options["connect_args"]["charset"], "utf8mb4")
        self.assertFalse(
            _database_requires_tls(
                uri,
                {},
                unix_socket=options["connect_args"]["unix_socket"],
            )
        )

    def test_mysql_do_connect_receives_only_normalized_direct_arguments(self):
        uri, options = _engine_configuration(
            "mysql+pymysql://user:secret@127.0.0.1:3306/medical_db"
            "?charset=utf8mb4",
            {},
        )
        captured = {}
        engine = create_engine(uri, **options)

        @event.listens_for(engine, "do_connect")
        def capture_connection_arguments(_dialect, _record, _cargs, cparams):
            captured.update(cparams)
            raise RuntimeError("connection captured")

        try:
            with self.assertRaisesRegex(RuntimeError, "connection captured"):
                engine.connect()
        finally:
            engine.dispose()

        self.assertEqual(dict(make_url(uri).query), {})
        self.assertEqual(captured["host"], "127.0.0.1")
        self.assertEqual(captured["port"], 3306)
        self.assertEqual(captured["user"], "user")
        self.assertEqual(captured["password"], "secret")
        self.assertEqual(captured["database"], "medical_db")
        self.assertEqual(captured["charset"], "utf8mb4")
        self.assertEqual(captured["connect_timeout"], 10)

    def test_mysql_connection_rejects_ssl_disable_and_init_command(self):
        with self.assertRaisesRegex(RuntimeError, "ssl_disabled"):
            _engine_configuration(
                "mysql+pymysql://user:secret@127.0.0.1/medical_db"
                "?ssl_disabled=true",
                {},
            )
        with self.assertRaisesRegex(RuntimeError, "init_command"):
            _engine_configuration(
                "mysql+pymysql://user:secret@127.0.0.1/medical_db"
                "?init_command=SELECT%201",
                {},
            )

    def test_app_factory_rechecks_mysql_runtime_policy_before_connecting(self):
        class UnsafeConfig:
            SQLALCHEMY_DATABASE_URI = (
                "mysql+pymysql://user:secret@127.0.0.1/medical_db"
            )
            SQLALCHEMY_ENGINE_OPTIONS = {
                "connect_args": {
                    "charset": "utf8mb4",
                    "connect_timeout": 10,
                    "read_timeout": 30,
                    "write_timeout": 30,
                }
            }
            REQUIRE_ALEMBIC_HEAD = False
            RUNTIME_SCHEMA_SYNC_ENABLED = False
            PRODUCTION_DATABASE_PREFLIGHT_ENABLED = True
            DATABASE_REQUIRE_TLS = False

        with self.assertRaisesRegex(RuntimeError, "REQUIRE_ALEMBIC_HEAD"):
            create_app(UnsafeConfig)

    def test_app_factory_rejects_query_authority_override_before_initializing_db(self):
        class QueryOverrideConfig:
            SQLALCHEMY_DATABASE_URI = (
                "mysql+pymysql://user:secret@127.0.0.1/medical_db"
                "?host=db.example.test"
            )
            REQUIRE_ALEMBIC_HEAD = True
            RUNTIME_SCHEMA_SYNC_ENABLED = False
            PRODUCTION_DATABASE_PREFLIGHT_ENABLED = True
            DATABASE_REQUIRE_TLS = False

        with patch("backend.app.db.init_app") as init_app:
            with self.assertRaisesRegex(RuntimeError, "unsupported query options"):
                create_app(QueryOverrideConfig)

        init_app.assert_not_called()

    def test_app_factory_rejects_direct_authority_override_before_initializing_db(self):
        class DirectOverrideConfig:
            SQLALCHEMY_DATABASE_URI = (
                "mysql+pymysql://user:secret@127.0.0.1/medical_db"
            )
            SQLALCHEMY_ENGINE_OPTIONS = {
                "connect_args": {
                    "charset": "utf8mb4",
                    "connect_timeout": 10,
                    "read_timeout": 30,
                    "write_timeout": 30,
                    "host": "db.example.test",
                    "database": "other_db",
                    "ssl_disabled": True,
                }
            }
            REQUIRE_ALEMBIC_HEAD = True
            RUNTIME_SCHEMA_SYNC_ENABLED = False
            PRODUCTION_DATABASE_PREFLIGHT_ENABLED = True
            DATABASE_REQUIRE_TLS = False

        with patch("backend.app.db.init_app") as init_app:
            with self.assertRaisesRegex(RuntimeError, "unsupported options"):
                create_app(DirectOverrideConfig)

        init_app.assert_not_called()

    def test_app_factory_rejects_conflicting_unix_socket_sources(self):
        class ConflictingSocketConfig:
            SQLALCHEMY_DATABASE_URI = "mysql+pymysql://user:secret@/medical_db"
            SQLALCHEMY_ENGINE_OPTIONS = {
                "connect_args": {
                    "charset": "utf8mb4",
                    "connect_timeout": 10,
                    "read_timeout": 30,
                    "write_timeout": 30,
                    "unix_socket": "/run/mysql/actual.sock",
                }
            }
            MYSQL_UNIX_SOCKET = "/run/mysql/declared.sock"
            REQUIRE_ALEMBIC_HEAD = True
            RUNTIME_SCHEMA_SYNC_ENABLED = False
            PRODUCTION_DATABASE_PREFLIGHT_ENABLED = True
            DATABASE_REQUIRE_TLS = False

        with patch("backend.app.db.init_app") as init_app:
            with self.assertRaisesRegex(RuntimeError, "must match"):
                create_app(ConflictingSocketConfig)

        init_app.assert_not_called()

    def test_migration_factory_still_rejects_raw_query_overrides(self):
        class UnsafeMigrationConfig:
            SQLALCHEMY_DATABASE_URI = (
                "mysql+pymysql://user:secret@127.0.0.1/medical_db"
                "?host=db.example.test&database=other_db"
            )

        with patch("backend.app.db.init_app") as init_app:
            with self.assertRaisesRegex(RuntimeError, "unsupported query options"):
                create_migration_app(UnsafeMigrationConfig)

        init_app.assert_not_called()

    def test_remote_custom_config_requires_actual_verified_tls_arguments(self):
        class MissingTlsConfig:
            SQLALCHEMY_DATABASE_URI = (
                "mysql+pymysql://user:secret@db.example.test/medical_db"
            )
            SQLALCHEMY_ENGINE_OPTIONS = {
                "connect_args": {
                    "charset": "utf8mb4",
                    "connect_timeout": 10,
                    "read_timeout": 30,
                    "write_timeout": 30,
                }
            }
            REQUIRE_ALEMBIC_HEAD = True
            RUNTIME_SCHEMA_SYNC_ENABLED = False
            PRODUCTION_DATABASE_PREFLIGHT_ENABLED = True
            DATABASE_REQUIRE_TLS = True

        with patch("backend.app.db.init_app") as init_app:
            with self.assertRaisesRegex(RuntimeError, "verified TLS"):
                create_app(MissingTlsConfig)

        init_app.assert_not_called()

    def test_app_factory_accepts_normalized_unix_socket_configuration(self):
        class SocketConfig:
            SQLALCHEMY_DATABASE_URI = (
                "mysql+pymysql://user:secret@/medical_db"
            )
            SQLALCHEMY_ENGINE_OPTIONS = {
                "connect_args": {
                    "charset": "utf8mb4",
                    "connect_timeout": 10,
                    "read_timeout": 30,
                    "write_timeout": 30,
                    "unix_socket": "/var/run/mysqld/mysqld.sock",
                }
            }
            MYSQL_UNIX_SOCKET = "/var/run/mysqld/mysqld.sock"
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            REQUIRE_ALEMBIC_HEAD = True
            RUNTIME_SCHEMA_SYNC_ENABLED = False
            PRODUCTION_DATABASE_PREFLIGHT_ENABLED = True
            DATABASE_REQUIRE_TLS = False
            STARTUP_DATA_REPAIRS_ENABLED = False
            SCHEDULER_ENABLED = False
            CORS_ORIGINS = []
            SECRET_KEY = "test-secret"
            JWT_SECRET_KEY = "test-jwt-secret"

        with patch(
            "backend.app._assert_database_at_alembic_head",
            return_value={"expected-head"},
        ):
            app = create_app(SocketConfig)

        self.assertEqual(
            app.config["SQLALCHEMY_ENGINE_OPTIONS"]["connect_args"]["unix_socket"],
            "/var/run/mysqld/mysqld.sock",
        )

    def test_remote_mysql_cannot_disable_hostname_verification(self):
        with patch.dict(os.environ, {}, clear=False):
            for name in ("MYSQL_SSL_CA", "MYSQL_SSL_CERT", "MYSQL_SSL_KEY"):
                os.environ.pop(name, None)
            with self.assertRaisesRegex(RuntimeError, "may not disable"):
                _engine_options(
                    "mysql+pymysql://user:secret@db.example.test/medical_db"
                    "?ssl_ca=%2Fsecure%2Fca.pem&ssl_verify_identity=false"
                )

    def test_remote_mysql_cannot_disable_environment_certificate_verification(self):
        with patch.dict(
            os.environ,
            {
                "MYSQL_SSL_CA": "/secure/ca.pem",
                "MYSQL_SSL_VERIFY_CERT": "0",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "may not disable"):
                _engine_options(
                    "mysql+pymysql://user:secret@db.example.test/medical_db"
                )


if __name__ == "__main__":
    unittest.main()
