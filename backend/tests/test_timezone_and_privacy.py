import io
import unittest
from datetime import datetime, timedelta, timezone

from openpyxl import load_workbook

from backend.app import create_app, db
from backend.app.api.admin import _mask_patient_name
from backend.app.api.doctor import _format_local_dt as format_doctor_local_dt
from backend.app.api.nurse import _format_local_dt as format_nurse_local_dt
from backend.app.models import Drug, OperationLog, Patient, Payment, PrescriptionItem, User, Visit
from backend.app.services.time_utils import (
    local_naive_to_utc,
    parse_local_datetime,
    utc_naive_to_local,
)


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
        self.admin = User(username="admin-time", real_name="管理员", role="admin")
        for user in (self.doctor, self.nurse, self.finance, self.admin):
            user.set_password("password-123456")
        self.patient = Patient(student_id="SENSITIVE-001", name="张三", patient_type="student")
        self.drug = Drug(name="测试药品", type=1, specification="10片/盒", unit="盒", price=10, stock=9)
        db.session.add_all([
            self.doctor,
            self.nurse,
            self.finance,
            self.admin,
            self.patient,
            self.drug,
        ])
        db.session.flush()

        self.visit = Visit(
            patient_id=self.patient.id,
            doctor_id=self.doctor.id,
            diagnosis="敏感诊断",
            chief_complaint="敏感主诉",
            consultation_fee=0,
            total_amount=10,
            status="completed",
            timestamp=datetime(2026, 7, 9, 16, 30),
        )
        db.session.add(self.visit)
        db.session.flush()
        db.session.add(PrescriptionItem(
            visit_id=self.visit.id,
            drug_id=self.drug.id,
            quantity=1,
            price_at_visit=10,
            amount=10,
            new_amount=10,
            purchase_cost=5,
        ))
        # 2026-07-09 16:30 UTC is 2026-07-10 00:30 in China.
        db.session.add(Payment(
            visit_id=self.visit.id,
            nurse_id=self.nurse.id,
            amount=10,
            payment_method="cash",
            payment_date=datetime(2026, 7, 9, 16, 30),
        ))
        db.session.commit()

        self.finance_headers = self._login("finance-time")
        self.doctor_headers = self._login("doctor-time")
        self.nurse_headers = self._login("nurse-time")
        self.admin_headers = self._login("admin-time")
        self.headers = self.finance_headers

    def _login(self, username):
        login = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": "password-123456"},
        )
        self.assertEqual(login.status_code, 200)
        return {"Authorization": f"Bearer {login.get_json()['access_token']}"}

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
        self.assertEqual(detail["date"], "2026-07-10 00:30:00")
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

    def test_time_utils_preserve_utc_contract_and_end_precision(self):
        self.assertEqual(
            local_naive_to_utc(datetime(2026, 7, 10, 0, 0)),
            datetime(2026, 7, 9, 16, 0),
        )
        aware = datetime(2026, 7, 10, 12, 0, tzinfo=timezone(timedelta(hours=-4)))
        self.assertEqual(utc_naive_to_local(aware), datetime(2026, 7, 11, 0, 0))
        self.assertEqual(
            parse_local_datetime("2026-07-10", is_end=True),
            datetime(2026, 7, 10, 16, 0),
        )
        self.assertEqual(
            parse_local_datetime("2026-07-10 23:59", is_end=True),
            datetime(2026, 7, 10, 16, 0),
        )

    def test_doctor_history_filter_uses_local_midnight(self):
        previous_day = Visit(
            patient_id=self.patient.id,
            doctor_id=self.doctor.id,
            diagnosis="前一日",
            status="pending",
            timestamp=datetime(2026, 7, 9, 15, 59, 59),
        )
        db.session.add(previous_day)
        db.session.commit()

        response = self.client.get(
            "/api/doctor/visits/history",
            headers=self.doctor_headers,
            query_string={"start_date": "2026-07-10"},
        )
        self.assertEqual(response.status_code, 200)
        rows = response.get_json()["data"]
        ids = {row["id"] for row in rows}
        self.assertIn(self.visit.id, ids)
        self.assertNotIn(previous_day.id, ids)
        self.assertEqual(rows[0]["date"], "2026-07-10 00:30")

    def test_nurse_history_range_excludes_next_local_day(self):
        next_day = Visit(
            patient_id=self.patient.id,
            doctor_id=self.doctor.id,
            diagnosis="次日",
            status="pending",
            timestamp=datetime(2026, 7, 10, 16, 30),
        )
        db.session.add(next_day)
        db.session.commit()

        response = self.client.get(
            "/api/nurse/my-history",
            headers=self.nurse_headers,
            query_string={"date_from": "2026-07-10", "date_to": "2026-07-10"},
        )
        self.assertEqual(response.status_code, 200)
        ids = {row["visit_id"] for row in response.get_json()["data"]}
        self.assertIn(self.visit.id, ids)
        self.assertNotIn(next_day.id, ids)

    def test_operation_log_end_date_includes_fractional_last_second(self):
        included = OperationLog(
            user_id=self.admin.id,
            action_type="timezone-boundary",
            target_type="test",
            target_id=1,
            summary="included",
            timestamp=datetime(2026, 7, 10, 15, 59, 59, 500000),
        )
        excluded = OperationLog(
            user_id=self.admin.id,
            action_type="timezone-boundary",
            target_type="test",
            target_id=2,
            summary="excluded",
            timestamp=datetime(2026, 7, 10, 16, 0),
        )
        db.session.add_all([included, excluded])
        db.session.commit()

        response = self.client.get(
            "/api/admin/operation-logs",
            headers=self.admin_headers,
            query_string={"action_type": "timezone-boundary", "end_date": "2026-07-10"},
        )
        self.assertEqual(response.status_code, 200)
        rows = response.get_json()["data"]
        self.assertEqual([row["id"] for row in rows], [included.id])
        self.assertEqual(rows[0]["timestamp"], "2026-07-10 23:59:59")

    def test_drug_outbound_export_uses_local_range_labels(self):
        response = self.client.get(
            "/api/admin/statistics/drug-outbound/export",
            headers=self.finance_headers,
            query_string={
                "start_time": "2026-07-10 00:00:00",
                "end_time": "2026-07-10 23:59:59",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "drug_outbound_20260710_0000_20260710_2359.xlsx",
            response.headers["Content-Disposition"],
        )
        workbook = load_workbook(io.BytesIO(response.data), read_only=True)
        summary = workbook["summary"]
        self.assertEqual(summary["B1"].value, "2026-07-10 00:00:00")
        self.assertEqual(summary["B2"].value, "2026-07-10 23:59:59")

    def test_drug_inbound_time_is_stored_as_utc_and_returned_as_local(self):
        response = self.client.post(
            "/api/admin/drugs",
            headers=self.admin_headers,
            json={
                "name": "时区药品",
                "type": 1,
                "specification": "1盒",
                "unit": "盒",
                "purchase_price": 1,
                "price": 2,
                "stock": 0,
                "inbound_at": "2026-07-10 09:15",
            },
        )
        self.assertEqual(response.status_code, 201)
        drug_id = response.get_json()["data"]["id"]
        self.assertEqual(db.session.get(Drug, drug_id).inbound_at, datetime(2026, 7, 10, 1, 15))

        response = self.client.get(
            "/api/nurse/drugs",
            headers=self.nurse_headers,
            query_string={"inbound_start": "2026-07-10", "inbound_end": "2026-07-10"},
        )
        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.get_json()["data"] if item["id"] == drug_id)
        self.assertEqual(row["inbound_at"], "2026-07-10 09:15")

    def test_single_character_patient_name_is_masked(self):
        self.assertEqual(_mask_patient_name("王", True), "*")


if __name__ == "__main__":
    unittest.main()
