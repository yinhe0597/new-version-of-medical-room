import unittest

from backend.app import create_app, db
from backend.app.models import Patient


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test-jwt-secret-key-at-least-32-bytes"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class PatientModelTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_patient_supports_student_and_class_fields(self):
        p = Patient(
            student_id="2024001",
            name="张三",
            gender="男",
            class_name="计算机1班",
            grade="2024",
            college="计算机学院",
            major="计算机科学与技术",
            phone="13800138000",
        )
        db.session.add(p)
        db.session.commit()

        loaded = db.session.get(Patient, p.id)
        self.assertEqual(loaded.student_id, "2024001")
        self.assertEqual(loaded.class_name, "计算机1班")
        self.assertEqual(loaded.grade, "2024")


if __name__ == "__main__":
    unittest.main()

