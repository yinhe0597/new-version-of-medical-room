from concurrent.futures import ThreadPoolExecutor
import os
import tempfile
from threading import Event, Lock
import unittest
from unittest.mock import Mock, patch

from sqlalchemy.engine import make_url

from backend.app import create_app, db
from backend.app.api import routes
from backend.app.api.routes import _assert_mysql_runtime_ready


class HealthEndpointTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.temp_dir.name, "health.db")

        class TestConfig:
            TESTING = True
            SECRET_KEY = "health-test-secret"
            JWT_SECRET_KEY = "health-test-jwt-secret"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + db_path
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            CORS_ORIGINS = []
            SCHEDULER_ENABLED = False
            STARTUP_DATA_REPAIRS_ENABLED = False

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temp_dir.cleanup()

    def test_liveness_does_not_require_authentication(self):
        response = self.client.get("/api/health/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_readiness_queries_database(self):
        response = self.client.get("/api/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ready"})

    def test_readiness_hides_database_failure_details(self):
        with patch.object(db.session, "execute", side_effect=RuntimeError("secret host")):
            response = self.client.get("/api/health/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"status": "not_ready"})
        self.assertNotIn("secret host", response.get_data(as_text=True))

        recovered = self.client.get("/api/health/ready")
        self.assertEqual(recovered.status_code, 200)
        self.assertEqual(recovered.get_json(), {"status": "ready"})

    def test_readiness_stays_503_when_session_cleanup_also_fails(self):
        remove_failure = RuntimeError("remove failed")
        with (
            patch.object(
                db.session,
                "execute",
                side_effect=RuntimeError("secret query failure"),
            ),
            patch.object(
                db.session,
                "rollback",
                side_effect=RuntimeError("rollback failed"),
            ),
            patch.object(
                db.session,
                "remove",
                side_effect=[remove_failure, None],
            ) as remove,
        ):
            response = self.client.get("/api/health/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"status": "not_ready"})
        self.assertNotIn("secret", response.get_data(as_text=True))
        self.assertGreaterEqual(remove.call_count, 1)

    def test_mysql_runtime_readiness_rejects_failover_and_unsafe_grants(self):
        healthy = {
            "database_name": "medical_db",
            "read_only": 0,
            "super_read_only": 0,
            "transaction_read_only": 0,
            "sql_mode": "STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION",
        }
        direct_dml = [
            "GRANT SELECT, INSERT, UPDATE, DELETE ON `medical_db`.* "
            "TO `app`@`localhost`"
        ]
        _assert_mysql_runtime_ready(
            healthy,
            expected_database="medical_db",
            expected_heads=("head",),
            current_heads=("head",),
            grants=direct_dml,
            model_tables={"patient", "visit"},
        )

        for field in ("read_only", "super_read_only", "transaction_read_only"):
            with self.subTest(field=field):
                failed = {**healthy, field: 1}
                with self.assertRaisesRegex(RuntimeError, "read-only"):
                    _assert_mysql_runtime_ready(
                        failed,
                        expected_database="medical_db",
                        expected_heads=("head",),
                        current_heads=("head",),
                        grants=direct_dml,
                        model_tables={"patient", "visit"},
                    )

        with self.assertRaisesRegex(RuntimeError, "grants"):
            _assert_mysql_runtime_ready(
                healthy,
                expected_database="medical_db",
                expected_heads=("head",),
                current_heads=("head",),
                grants=["GRANT SELECT ON `medical_db`.* TO `app`@`localhost`"],
                model_tables={"patient", "visit"},
            )

    def test_mysql_readiness_queries_session_transaction_read_only(self):
        result = Mock()
        result.mappings.return_value.one.return_value = {
            "database_name": make_url(
                self.app.config["SQLALCHEMY_DATABASE_URI"]
            ).database,
            "read_only": 0,
            "super_read_only": 0,
            "transaction_read_only": 1,
            "sql_mode": "STRICT_TRANS_TABLES",
        }
        with self.app.app_context():
            with (
                patch.object(db.engine.dialect, "name", "mysql"),
                patch.object(db.session, "execute", return_value=result) as execute,
                patch.object(routes, "_check_cached_mysql_deep_readiness") as deep_check,
            ):
                with self.assertRaisesRegex(RuntimeError, "read-only"):
                    routes._check_database_readiness()

        self.assertIn("@@SESSION.transaction_read_only", str(execute.call_args.args[0]))
        deep_check.assert_not_called()

    def test_mysql_deep_readiness_cache_expires_and_tracks_fingerprint(self):
        clock = [100.0]
        with (
            patch.object(routes, "monotonic", side_effect=lambda: clock[0]),
            patch.object(routes, "_run_mysql_deep_readiness") as deep_check,
        ):
            with self.app.app_context():
                routes._check_cached_mysql_deep_readiness(
                    expected_database="medical_db",
                    expected_heads=("head-a",),
                    model_tables={"visit"},
                )
                routes._check_cached_mysql_deep_readiness(
                    expected_database="medical_db",
                    expected_heads=("head-a",),
                    model_tables={"visit"},
                )
                self.assertEqual(deep_check.call_count, 1)

                routes._check_cached_mysql_deep_readiness(
                    expected_database="medical_db",
                    expected_heads=("head-b",),
                    model_tables={"visit"},
                )
                self.assertEqual(deep_check.call_count, 2)

                clock[0] += routes._MYSQL_DEEP_READINESS_TTL_SECONDS + 0.1
                routes._check_cached_mysql_deep_readiness(
                    expected_database="medical_db",
                    expected_heads=("head-b",),
                    model_tables={"visit"},
                )
                self.assertEqual(deep_check.call_count, 3)

    def test_mysql_deep_readiness_cache_is_single_flight(self):
        entered = Event()
        release = Event()
        counter_lock = Lock()
        calls = 0

        def run_deep_check(**_kwargs):
            nonlocal calls
            with counter_lock:
                calls += 1
            entered.set()
            if not release.wait(timeout=5):
                raise RuntimeError("test deep check timed out")

        def check_from_thread():
            with self.app.app_context():
                routes._check_cached_mysql_deep_readiness(
                    expected_database="medical_db",
                    expected_heads=("head",),
                    model_tables={"visit"},
                )

        with (
            patch.object(routes, "monotonic", return_value=100.0),
            patch.object(
                routes,
                "_run_mysql_deep_readiness",
                side_effect=run_deep_check,
            ),
            ThreadPoolExecutor(max_workers=4) as executor,
        ):
            futures = [executor.submit(check_from_thread) for _ in range(4)]
            self.assertTrue(entered.wait(timeout=5))
            release.set()
            for future in futures:
                future.result(timeout=5)

        self.assertEqual(calls, 1)

    def test_mysql_deep_readiness_failure_is_cached_conservatively(self):
        clock = [100.0]
        with (
            patch.object(routes, "monotonic", side_effect=lambda: clock[0]),
            patch.object(
                routes,
                "_run_mysql_deep_readiness",
                side_effect=RuntimeError("deep check failed"),
            ) as deep_check,
        ):
            with self.app.app_context():
                with self.assertRaisesRegex(RuntimeError, "deep check failed"):
                    routes._check_cached_mysql_deep_readiness(
                        expected_database="medical_db",
                        expected_heads=("head",),
                        model_tables={"visit"},
                    )
                with self.assertRaisesRegex(RuntimeError, "temporarily unavailable"):
                    routes._check_cached_mysql_deep_readiness(
                        expected_database="medical_db",
                        expected_heads=("head",),
                        model_tables={"visit"},
                    )
                self.assertEqual(deep_check.call_count, 1)

                clock[0] += routes._MYSQL_DEEP_READINESS_TTL_SECONDS + 0.1
                with self.assertRaisesRegex(RuntimeError, "deep check failed"):
                    routes._check_cached_mysql_deep_readiness(
                        expected_database="medical_db",
                        expected_heads=("head",),
                        model_tables={"visit"},
                    )
                self.assertEqual(deep_check.call_count, 2)


if __name__ == "__main__":
    unittest.main()
