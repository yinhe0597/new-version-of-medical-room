import unittest
from unittest.mock import patch

from backend.app import create_app, db
from backend.app.models import Drug, Patient, User
import backend.init_db as init_db_module


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test-jwt-secret-key-at-least-32-bytes"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class InitDbTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_init_db_creates_schema_and_seed_data(self):
        with patch.dict("os.environ", {"BOOTSTRAP_PASSWORD": "temporary-password-123"}):
            init_db_module.init_db(self.app)

        self.assertIsNotNone(User.query.filter_by(username="admin").first())
        self.assertGreater(Drug.query.count(), 0)
        self.assertGreater(Patient.query.count(), 0)

    def test_init_db_rotates_legacy_default_password(self):
        admin = User(username="admin", real_name="管理员", role="admin")
        admin.set_password("123456")
        db.session.add(admin)
        db.session.commit()
        old_token_version = admin.token_version

        with patch.dict("os.environ", {"BOOTSTRAP_PASSWORD": "rotated-password-123"}):
            init_db_module.init_db(self.app)

        db.session.expire_all()
        admin = User.query.filter_by(username="admin").one()
        self.assertFalse(admin.check_password("123456"))
        self.assertTrue(admin.check_password("rotated-password-123"))
        self.assertGreater(admin.token_version, old_token_version)


if __name__ == "__main__":
    unittest.main()

