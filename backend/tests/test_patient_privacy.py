import os
import tempfile
import unittest

from backend.app import create_app, db
from backend.app.models import Patient, User


class PatientSearchPrivacyTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.temp_dir.name, "app.db")

        class TestConfig:
            TESTING = True
            SECRET_KEY = "test-secret-key-that-is-long-enough"
            JWT_SECRET_KEY = "test-jwt-key-that-is-long-enough"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + db_path
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            CORS_ORIGINS = []

        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()

        doctor = User(username="doctor-privacy", real_name="医生", role="doctor")
        doctor.set_password("123456")
        db.session.add(doctor)
        db.session.add(Patient(
            name="隐私测试",
            student_id="privacy-001",
            id_card="11010519491231002X",
            patient_type="staff",
        ))
        db.session.commit()

        login = self.client.post(
            "/api/auth/login",
            json={"username": "doctor-privacy", "password": "123456"},
        )
        self.headers = {"Authorization": f"Bearer {login.get_json()['access_token']}"}

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()
        self.temp_dir.cleanup()

    def test_patient_search_does_not_return_full_id_card(self):
        response = self.client.get(
            "/api/doctor/patient/search",
            headers=self.headers,
            query_string={"keyword": "隐私测试"},
        )
        self.assertEqual(response.status_code, 200)
        result = response.get_json()["data"][0]
        self.assertEqual(result["name"], "隐私测试")
        self.assertNotIn("id_card", result)


if __name__ == "__main__":
    unittest.main()
