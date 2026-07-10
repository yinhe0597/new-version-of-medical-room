import unittest
from datetime import datetime

from backend.app import create_app, db
from backend.app.api.admin import _mask_patient_name
from backend.app.api.doctor import _format_local_dt as format_doctor_local_dt
from backend.app.api.nurse import _format_local_dt as format_nurse_local_dt
from backend.app.models import Drug, Patient, Payment, PrescriptionItem, User, Visit


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret-key-at-least-32-characters"
    JWT_SECRET_KEY = "test-jwt-secret-key-at-least-32-characters"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CORS_ORIGINS = []


class TimezoneAndPrivacyTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()

        self.doctor = User(username="doctor-time", real_name="医生", role="doctor")
        self.nurse = User(username="nurse-time", real_name="护士", role="nurse")
        self.finance = User(username="finance-time", real_name="财务", role="finance")
        for user in (self.doctor, self.nurse, self.finance):
            user.set_password("password-123456")
        patient = Patient(student_id="SENSITIVE-001", name="张三", patient_type="student")
        drug = Drug(name="测试药品", type=1, specification="10片/盒", unit="盒", price=10, stock=9)
        db.session.add_all([self.doctor, self.nurse, self.finance, patient, drug])
        db.session.flush()

        visit = Visit(
            patient_id=patient.id,
            doctor_id=self.doctor.id,
            diagnosis="敏感诊断",
            chief_complaint="敏感主诉",
            consultation_fee=0,
            total_amount=10,
            status="completed",
        )
        db.session.add(visit)
        db.session.flush()
        db.session.add(PrescriptionItem(
            visit_id=visit.id,
            drug_id=drug.id,
            quantity=1,
            price_at_visit=10,
            amount=10,
            new_amount=10,
            purchase_cost=5,
        ))
        # 2026-07-09 16:30 UTC is 2026-07-10 00:30 in China.
        db.session.add(Payment(
            visit_id=visit.id,
            nurse_id=self.nurse.id,
            amount=10,
            payment_method="cash",
            payment_date=datetime(2026, 7, 9, 16, 30),
        ))
        db.session.commit()

        login = self.client.post(
            "/api/auth/login",
            json={"username": "finance-time", "password": "password-123456"},
        )
        self.headers = {"Authorization": f"Bearer {login.get_json()['access_token']}"}

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_revenue_uses_china_day_boundary_and_hides_clinical_identity(self):
        response = self.client.get(
            "/api/admin/statistics/revenue",
            headers=self.headers,
            query_string={"type": "daily", "date": "2026-07-10"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["total_revenue"], 10)
        self.assertEqual(data["range"]["start"], "2026-07-10 00:00:00")
        detail = data["details"][0]
        self.assertNotEqual(detail["patient_name"], "张三")
        self.assertEqual(detail["student_id"], "")
        self.assertEqual(detail["diagnosis"], "")
        self.assertEqual(detail["chief_complaint"], "")

    def test_finance_outbound_detail_is_deidentified(self):
        response = self.client.get(
            "/api/admin/statistics/drug-outbound",
            headers=self.headers,
            query_string={
                "start_time": "2026-07-10 00:00:00",
                "end_time": "2026-07-10 23:59:59",
            },
        )
        self.assertEqual(response.status_code, 200)
        detail = response.get_json()["data"]["details"][0]
        self.assertNotEqual(detail["patient_name"], "张三")
        self.assertEqual(detail["student_id"], "")

    def test_local_datetime_formatting_is_fixed_to_china_time(self):
        value = datetime(2026, 7, 9, 16, 30)
        self.assertEqual(format_doctor_local_dt(value), "2026-07-10 00:30")
        self.assertEqual(format_nurse_local_dt(value), "2026-07-10 00:30")

    def test_single_character_patient_name_is_masked(self):
        self.assertEqual(_mask_patient_name("王", True), "*")


if __name__ == "__main__":
    unittest.main()
