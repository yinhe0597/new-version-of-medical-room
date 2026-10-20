import time
import unittest

from backend.app import create_app, db
from backend.app.models import User
from backend.app.services.login_throttle import reset_login_throttle


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test-jwt-secret-key-at-least-32-bytes"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    LOGIN_MAX_ATTEMPTS = 3
    LOGIN_ATTEMPT_WINDOW_SECONDS = 60
    LOGIN_LOCKOUT_SECONDS = 1


class AuthLoginTestCase(unittest.TestCase):
    def setUp(self):
        reset_login_throttle()
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        u = User(username="doctor", real_name="张医生", role="doctor")
        u.set_password("123456")
        db.session.add(u)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        reset_login_throttle()

    def test_login_returns_token_and_user(self):
        resp = self.client.post(
            "/api/auth/login",
            json={"username": "doctor", "password": "123456"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("access_token", data)
        self.assertEqual(data["user"]["role"], "doctor")

    def test_password_policy_and_old_token_invalidation(self):
        login = self.client.post(
            "/api/auth/login",
            json={"username": "doctor", "password": "123456"},
        )
        token = login.get_json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        weak = self.client.post(
            "/api/auth/change-password",
            headers=headers,
            json={"old_password": "123456", "new_password": "short"},
        )
        self.assertEqual(weak.status_code, 400)

        changed = self.client.post(
            "/api/auth/change-password",
            headers=headers,
            json={"old_password": "123456", "new_password": "new-password-123"},
        )
        self.assertEqual(changed.status_code, 200)

        stale = self.client.post(
            "/api/auth/change-password",
            headers=headers,
            json={"old_password": "new-password-123", "new_password": "another-password-123"},
        )
        self.assertEqual(stale.status_code, 401)
        relogin = self.client.post(
            "/api/auth/login",
            json={"username": "doctor", "password": "new-password-123"},
        )
        self.assertEqual(relogin.status_code, 200)

    def test_login_locks_after_repeated_failures_and_recovers(self):
        for _ in range(2):
            failed = self.client.post(
                "/api/auth/login",
                json={"username": "doctor", "password": "wrong-password"},
            )
            self.assertEqual(failed.status_code, 401)

        locked = self.client.post(
            "/api/auth/login",
            json={"username": "doctor", "password": "wrong-password"},
        )
        self.assertEqual(locked.status_code, 429)
        self.assertGreaterEqual(int(locked.headers["Retry-After"]), 1)

        blocked = self.client.post(
            "/api/auth/login",
            json={"username": "doctor", "password": "123456"},
        )
        self.assertEqual(blocked.status_code, 429)

        time.sleep(1.1)
        recovered = self.client.post(
            "/api/auth/login",
            json={"username": "doctor", "password": "123456"},
        )
        self.assertEqual(recovered.status_code, 200)

    def test_login_rejects_non_object_json(self):
        response = self.client.post("/api/auth/login", json=["doctor", "123456"])
        self.assertEqual(response.status_code, 400)

        invalid_type = self.client.post(
            "/api/auth/login",
            json={"username": ["doctor"], "password": "123456"},
        )
        self.assertEqual(invalid_type.status_code, 400)

    def test_unknown_api_is_json_404_and_large_body_is_413(self):
        missing = self.client.get("/api/definitely-not-a-route")
        self.assertEqual(missing.status_code, 404)
        self.assertTrue(missing.is_json)

        oversized = self.client.post(
            "/api/auth/login",
            data=b"x" * (13 * 1024 * 1024),
            content_type="application/json",
        )
        self.assertEqual(oversized.status_code, 413)


if __name__ == "__main__":
    unittest.main()

