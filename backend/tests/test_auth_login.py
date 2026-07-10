import unittest

from backend.app import create_app, db
from backend.app.models import User


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test-jwt-secret-key-at-least-32-bytes"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class AuthLoginTestCase(unittest.TestCase):
    def setUp(self):
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

