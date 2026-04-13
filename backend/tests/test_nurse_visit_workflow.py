import unittest

from backend.app import create_app, db
from backend.app.models import (
    Drug,
    Patient,
    PrescriptionItem,
    User,
    Visit,
    VISIT_STATUS_COMPLETED,
    VISIT_STATUS_NURSE_VERIFIED,
    VISIT_STATUS_PENDING,
    VISIT_STATUS_REJECTED,
    Payment,
)


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test-jwt"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class NurseVisitWorkflowTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        self.doctor = User(username="doctor1", real_name="张医生", role="doctor")
        self.doctor.set_password("123456")
        self.nurse = User(username="nurse1", real_name="李护士", role="nurse")
        self.nurse.set_password("123456")
        db.session.add_all([self.doctor, self.nurse])

        self.patient = Patient(name="王小明", gender="男", phone="13800138000")
        self.drug = Drug(
            name="阿司匹林",
            type=1,
            specification="100mg*10片",
            unit="盒",
            price=10.0,
            stock=100,
            status=1,
            has_scattered=False,
        )
        db.session.add_all([self.patient, self.drug])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _login(self, username, password):
        resp = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()["access_token"]

    def _auth_headers(self, token):
        return {"Authorization": f"Bearer {token}"}

    def _create_visit_with_item(self, status=VISIT_STATUS_PENDING, quantity=2, unit_price=10.0, consultation_fee=5.0):
        amount = float(quantity) * float(unit_price)
        visit = Visit(
            patient_id=self.patient.id,
            doctor_id=self.doctor.id,
            consultation_fee=consultation_fee,
            total_amount=consultation_fee + amount,
            status=status,
        )
        db.session.add(visit)
        db.session.flush()
        item = PrescriptionItem(
            visit_id=visit.id,
            drug_id=self.drug.id,
            usage="口服",
            dosage="1片",
            frequency="tid",
            timing="饭后",
            days=1,
            quantity=quantity,
            price_at_visit=unit_price,
            amount=amount,
            original_price=unit_price,
            original_amount=amount,
            new_price=unit_price,
            new_amount=amount,
            is_scattered=False,
        )
        db.session.add(item)
        db.session.commit()
        return visit.id, item.id

    def test_cannot_execute_before_verify(self):
        visit_id, _ = self._create_visit_with_item(status=VISIT_STATUS_PENDING)
        token = self._login("nurse1", "123456")

        resp = self.client.post(
            f"/api/nurse/visits/{visit_id}/execute",
            headers=self._auth_headers(token),
            json={"payment_method": "cash"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn(VISIT_STATUS_NURSE_VERIFIED, resp.get_json().get("msg", ""))

    def test_can_verify_then_execute(self):
        visit_id, _ = self._create_visit_with_item(status=VISIT_STATUS_PENDING)
        token = self._login("nurse1", "123456")

        resp = self.client.post(f"/api/nurse/visits/{visit_id}/verify", headers=self._auth_headers(token))
        self.assertEqual(resp.status_code, 200)

        resp = self.client.post(
            f"/api/nurse/visits/{visit_id}/execute",
            headers=self._auth_headers(token),
            json={"payment_method": "cash"},
        )
        self.assertEqual(resp.status_code, 200)

        visit = Visit.query.get(visit_id)
        self.assertEqual(visit.status, VISIT_STATUS_COMPLETED)
        self.assertIsNotNone(Payment.query.filter_by(visit_id=visit_id).first())

    def test_can_reject_with_reason(self):
        visit_id, _ = self._create_visit_with_item(status=VISIT_STATUS_PENDING)
        token = self._login("nurse1", "123456")

        resp = self.client.post(
            f"/api/nurse/visits/{visit_id}/reject",
            headers=self._auth_headers(token),
            json={"reason": "信息不完整"},
        )
        self.assertEqual(resp.status_code, 200)

        visit = Visit.query.get(visit_id)
        self.assertEqual(visit.status, VISIT_STATUS_REJECTED)
        self.assertEqual(visit.reject_reason, "信息不完整")

    def test_can_modify_price_after_verify_and_execute_uses_updated_total(self):
        visit_id, item_id = self._create_visit_with_item(status=VISIT_STATUS_PENDING, quantity=2, unit_price=10.0, consultation_fee=5.0)
        token = self._login("nurse1", "123456")

        resp = self.client.post(f"/api/nurse/visits/{visit_id}/verify", headers=self._auth_headers(token))
        self.assertEqual(resp.status_code, 200)

        resp = self.client.put(
            f"/api/nurse/visits/{visit_id}/items/{item_id}/modify",
            headers=self._auth_headers(token),
            json={"new_price": 12.0, "modify_reason": "手工调价"},
        )
        self.assertEqual(resp.status_code, 200)

        visit = Visit.query.get(visit_id)
        item = PrescriptionItem.query.get(item_id)
        self.assertEqual(item.quantity, 2)
        self.assertAlmostEqual(item.new_price, 12.0, places=6)
        self.assertAlmostEqual(item.new_amount, 24.0, places=6)
        self.assertAlmostEqual(item.price_at_visit, 12.0, places=6)
        self.assertAlmostEqual(item.amount, 24.0, places=6)
        self.assertEqual(item.modified_by, self.nurse.id)
        self.assertEqual(item.modify_reason, "手工调价")
        self.assertAlmostEqual(visit.total_amount, 29.0, places=6)

        resp = self.client.post(
            f"/api/nurse/visits/{visit_id}/execute",
            headers=self._auth_headers(token),
            json={"payment_method": "cash"},
        )
        self.assertEqual(resp.status_code, 200)
        payment = Payment.query.filter_by(visit_id=visit_id).first()
        self.assertIsNotNone(payment)
        self.assertAlmostEqual(payment.amount, 29.0, places=6)

    def test_cannot_modify_after_completed(self):
        visit_id, item_id = self._create_visit_with_item(status=VISIT_STATUS_PENDING)
        token = self._login("nurse1", "123456")

        resp = self.client.post(f"/api/nurse/visits/{visit_id}/verify", headers=self._auth_headers(token))
        self.assertEqual(resp.status_code, 200)

        resp = self.client.post(
            f"/api/nurse/visits/{visit_id}/execute",
            headers=self._auth_headers(token),
            json={"payment_method": "cash"},
        )
        self.assertEqual(resp.status_code, 200)

        resp = self.client.put(
            f"/api/nurse/visits/{visit_id}/items/{item_id}/modify",
            headers=self._auth_headers(token),
            json={"new_price": 9.0, "modify_reason": "完成后尝试改价"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_cannot_modify_quantity(self):
        visit_id, item_id = self._create_visit_with_item(status=VISIT_STATUS_PENDING, quantity=2)
        token = self._login("nurse1", "123456")

        resp = self.client.post(f"/api/nurse/visits/{visit_id}/verify", headers=self._auth_headers(token))
        self.assertEqual(resp.status_code, 200)

        resp = self.client.put(
            f"/api/nurse/visits/{visit_id}/items/{item_id}/modify",
            headers=self._auth_headers(token),
            json={"quantity": 3, "new_price": 9.0, "modify_reason": "试图改数量"},
        )
        self.assertEqual(resp.status_code, 400)

        item = PrescriptionItem.query.get(item_id)
        self.assertEqual(item.quantity, 2)


if __name__ == "__main__":
    unittest.main()

