import unittest

from backend.app import create_app, db
from backend.app.models import Drug, Patient, User
import backend.init_db as init_db_module


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test-jwt"
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
        init_db_module.init_db(self.app)

        self.assertIsNotNone(User.query.filter_by(username="admin").first())
        self.assertGreater(Drug.query.count(), 0)
        self.assertGreater(Patient.query.count(), 0)


if __name__ == "__main__":
    unittest.main()

