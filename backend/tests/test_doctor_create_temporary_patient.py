import unittest

from backend.app import create_app, db
from backend.app.models import Patient, User


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test-jwt-secret-key-at-least-32-bytes"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DoctorCreateTemporaryPatientTestCase(unittest.TestCase):
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

    def test_temporary_patient_requires_phone_and_age(self):
        resp = self.client.post(
            "/api/doctor/patient",
            json={"name": "临时人员", "gender": "男", "is_temporary": True, "age": 20},
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(resp.status_code, 400)

        resp2 = self.client.post(
            "/api/doctor/patient",
            json={"name": "临时人员", "gender": "男", "is_temporary": True, "phone": "13800138000"},
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(resp2.status_code, 400)

    def test_temporary_patient_id_card_validation(self):
        resp = self.client.post(
            "/api/doctor/patient",
            json={
                "name": "临时人员",
                "gender": "女",
                "is_temporary": True,
                "age": 22,
                "phone": "13800138000",
                "id_card": "110105194912310021",
            },
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(resp.status_code, 400)

        resp2 = self.client.post(
            "/api/doctor/patient",
            json={
                "name": "临时人员2",
                "gender": "女",
                "is_temporary": True,
                "age": 22,
                "phone": "13800138001",
                "id_card": "11010519491231002X",
            },
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(resp2.status_code, 201)
        pid = resp2.get_json()["data"]["id"]
        p = db.session.get(Patient, pid)
        self.assertIsNotNone(p)
        self.assertTrue(p.is_temporary)
        self.assertEqual(p.age, 22)
        self.assertEqual(p.phone, "13800138001")
        self.assertEqual(p.id_card, "11010519491231002X")


if __name__ == "__main__":
    unittest.main()

