import unittest

from backend.app import create_app, db
from backend.app.models import Patient, User, Visit


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret-key-at-least-32-characters"
    JWT_SECRET_KEY = "test-jwt-secret-key-at-least-32-characters"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CORS_ORIGINS = []


class UserDeactivationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()

        self.admin = User(username="admin-soft-delete", real_name="管理员", role="admin")
        self.admin.set_password("admin-password-123")
        self.doctor = User(username="doctor-soft-delete", real_name="历史医生", role="doctor")
        self.doctor.set_password("doctor-password-123")
        patient = Patient(name="审计患者", gender="女", patient_type="student")
        db.session.add_all([self.admin, self.doctor, patient])
        db.session.flush()
        self.visit = Visit(
            patient_id=patient.id,
            doctor_id=self.doctor.id,
            diagnosis="既往诊断",
            consultation_fee=0,
            total_amount=0,
            status="pending",
        )
        db.session.add(self.visit)
        db.session.commit()

        admin_login = self.client.post(
            "/api/auth/login",
            json={"username": self.admin.username, "password": "admin-password-123"},
        )
        doctor_login = self.client.post(
            "/api/auth/login",
            json={"username": self.doctor.username, "password": "doctor-password-123"},
        )
        self.admin_headers = {
            "Authorization": f"Bearer {admin_login.get_json()['access_token']}"
        }
        self.doctor_headers = {
            "Authorization": f"Bearer {doctor_login.get_json()['access_token']}"
        }

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_deactivation_preserves_visit_and_invalidates_access(self):
        doctor_id = self.doctor.id
        visit_id = self.visit.id

        disabled = self.client.delete(
            f"/api/admin/users/{doctor_id}",
            headers=self.admin_headers,
        )
        self.assertEqual(disabled.status_code, 200)

        db.session.expire_all()
        doctor = db.session.get(User, doctor_id)
        visit = db.session.get(Visit, visit_id)
        self.assertIsNotNone(doctor)
        self.assertFalse(doctor.is_active)
        self.assertEqual(visit.doctor_id, doctor_id)

        stale_token = self.client.get(
            "/api/doctor/visits/history",
            headers=self.doctor_headers,
        )
        self.assertEqual(stale_token.status_code, 401)

        disabled_login = self.client.post(
            "/api/auth/login",
            json={"username": doctor.username, "password": "doctor-password-123"},
        )
        self.assertEqual(disabled_login.status_code, 401)

        users = self.client.get("/api/admin/users", headers=self.admin_headers)
        listed_doctor = next(
            item for item in users.get_json()["data"] if item["id"] == doctor_id
        )
        self.assertFalse(listed_doctor["is_active"])

        enabled = self.client.put(
            f"/api/admin/users/{doctor_id}",
            headers=self.admin_headers,
            json={"is_active": True},
        )
        self.assertEqual(enabled.status_code, 200)

        still_stale = self.client.get(
            "/api/doctor/visits/history",
            headers=self.doctor_headers,
        )
        self.assertEqual(still_stale.status_code, 401)

        enabled_login = self.client.post(
            "/api/auth/login",
            json={"username": doctor.username, "password": "doctor-password-123"},
        )
        self.assertEqual(enabled_login.status_code, 200)


if __name__ == "__main__":
    unittest.main()
