import unittest

from backend.app import create_app, db
from backend.app.models import Patient, User


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test-jwt-secret-key-at-least-32-bytes"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DoctorPatientSearchTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        u = User(username="doctor", real_name="张医生", role="doctor")
        u.set_password("123456")
        db.session.add(u)

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

        login_resp = self.client.post(
            "/api/auth/login",
            json={"username": "doctor", "password": "123456"},
        )
        self.token = login_resp.get_json()["access_token"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_search_by_student_id_returns_extended_patient_fields(self):
        resp = self.client.get(
            "/api/doctor/patient/search",
            query_string={"keyword": "2024001"},
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["student_id"], "2024001")
        self.assertEqual(data[0]["class_name"], "计算机1班")


if __name__ == "__main__":
    unittest.main()

