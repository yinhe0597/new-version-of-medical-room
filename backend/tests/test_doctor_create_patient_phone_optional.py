import unittest

from backend.app import create_app, db
from backend.app.models import Patient, User


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test-jwt"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DoctorCreatePatientPhoneOptionalTestCase(unittest.TestCase):
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

        login_resp = self.client.post(
            "/api/auth/login",
            json={"username": "doctor", "password": "123456"},
        )
        self.token = login_resp.get_json()["access_token"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_create_patient_without_phone(self):
        resp = self.client.post(
            "/api/doctor/patient",
            json={"name": "王小明", "gender": "男"},
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(resp.status_code, 201)
        pid = resp.get_json()["data"]["id"]
        patient = Patient.query.get(pid)
        self.assertIsNotNone(patient)
        self.assertEqual(patient.name, "王小明")
        self.assertIsNone(patient.phone)


if __name__ == "__main__":
    unittest.main()

