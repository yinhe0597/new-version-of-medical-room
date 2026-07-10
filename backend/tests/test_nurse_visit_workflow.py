import unittest
from datetime import timedelta

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
    InventoryRecord,
    OperationLog,
    INVENTORY_OPERATION_DISPENSE,
    INVENTORY_OPERATION_REVERSAL,
    utcnow,
)
from backend.app.services.inventory_ledger import backfill_revoked_inventory_movements


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test-jwt-secret-key-at-least-32-bytes"
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

        visit = db.session.get(Visit, visit_id)
        self.assertEqual(visit.status, VISIT_STATUS_COMPLETED)
        self.assertIsNotNone(Payment.query.filter_by(visit_id=visit_id).first())

    def test_execute_and_revoke_write_balancing_inventory_ledger(self):
        visit_id, _ = self._create_visit_with_item(
            status=VISIT_STATUS_NURSE_VERIFIED,
            quantity=2,
        )
        token = self._login("nurse1", "123456")
        headers = self._auth_headers(token)

        executed = self.client.post(
            f"/api/nurse/visits/{visit_id}/execute",
            headers=headers,
            json={"payment_method": "cash"},
        )
        self.assertEqual(executed.status_code, 200)
        dispense = InventoryRecord.query.filter_by(
            visit_id=visit_id,
            operation_type=INVENTORY_OPERATION_DISPENSE,
        ).one()
        self.assertEqual((dispense.old_stock, dispense.new_stock), (100, 98))

        reason = "收费录入错误" * 50
        revoked = self.client.post(
            f"/api/nurse/visits/{visit_id}/revoke",
            headers=headers,
            json={"reason": reason},
        )
        self.assertEqual(revoked.status_code, 200)
        reversal = InventoryRecord.query.filter_by(
            visit_id=visit_id,
            operation_type=INVENTORY_OPERATION_REVERSAL,
        ).one()
        self.assertEqual((reversal.old_stock, reversal.new_stock), (98, 100))
        self.assertLessEqual(len(reversal.remark), 200)
        self.assertEqual(db.session.get(Visit, visit_id).revoke_reason, reason)
        self.assertEqual(db.session.get(Drug, self.drug.id).stock, 100)
        self.assertIsNone(Payment.query.filter_by(visit_id=visit_id).first())

    def test_legacy_revoked_visit_ledger_backfill_is_idempotent(self):
        visit_id, _ = self._create_visit_with_item(status="revoked", quantity=2)
        visit = db.session.get(Visit, visit_id)
        verified_at = utcnow() - timedelta(days=2)
        executed_at = utcnow() - timedelta(days=3)
        visit.verified_by = self.doctor.id
        visit.verified_at = verified_at
        visit.revoked_by = self.nurse.id
        visit.revoked_at = utcnow() - timedelta(days=1)
        db.session.add(OperationLog(
            user_id=self.nurse.id,
            action_type="nurse_execute",
            target_type="visit",
            target_id=visit.id,
            summary="历史执行日志",
            timestamp=executed_at,
        ))
        db.session.commit()

        self.assertEqual(backfill_revoked_inventory_movements(), 2)
        self.assertEqual(backfill_revoked_inventory_movements(), 0)
        records = InventoryRecord.query.filter_by(visit_id=visit_id).all()
        self.assertEqual(
            {record.operation_type for record in records},
            {INVENTORY_OPERATION_DISPENSE, INVENTORY_OPERATION_REVERSAL},
        )
        dispense = next(
            record for record in records
            if record.operation_type == INVENTORY_OPERATION_DISPENSE
        )
        self.assertEqual(dispense.timestamp, executed_at)
        self.assertEqual(dispense.nurse_id, self.nurse.id)

    def test_can_reject_with_reason(self):
        visit_id, _ = self._create_visit_with_item(status=VISIT_STATUS_PENDING)
        token = self._login("nurse1", "123456")

        resp = self.client.post(
            f"/api/nurse/visits/{visit_id}/reject",
            headers=self._auth_headers(token),
            json={"reason": "信息不完整"},
        )
        self.assertEqual(resp.status_code, 200)

        visit = db.session.get(Visit, visit_id)
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

        visit = db.session.get(Visit, visit_id)
        item = db.session.get(PrescriptionItem, item_id)
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

        item = db.session.get(PrescriptionItem, item_id)
        self.assertEqual(item.quantity, 2)

    def test_execute_rejects_invalid_payment_values(self):
        visit_id, _ = self._create_visit_with_item(status=VISIT_STATUS_NURSE_VERIFIED)
        token = self._login("nurse1", "123456")
        headers = self._auth_headers(token)

        invalid_method = self.client.post(
            f"/api/nurse/visits/{visit_id}/execute",
            headers=headers,
            json={"payment_method": "crypto"},
        )
        self.assertEqual(invalid_method.status_code, 400)

        non_staff_discount = self.client.post(
            f"/api/nurse/visits/{visit_id}/execute",
            headers=headers,
            json={
                "payment_method": "cash",
                "employee_discount": True,
                "actual_consultation_fee": 1,
                "actual_drug_amount": 10,
            },
        )
        self.assertEqual(non_staff_discount.status_code, 400)

        self.patient.patient_type = "staff"
        db.session.commit()
        negative_discount = self.client.post(
            f"/api/nurse/visits/{visit_id}/execute",
            headers=headers,
            json={
                "payment_method": "cash",
                "employee_discount": True,
                "actual_consultation_fee": -1,
                "actual_drug_amount": 10,
            },
        )
        self.assertEqual(negative_discount.status_code, 400)
        self.assertIsNone(Payment.query.filter_by(visit_id=visit_id).first())
        self.assertEqual(self.drug.stock, 100)

    def test_employee_discount_uses_validated_split_amounts(self):
        self.patient.patient_type = "staff"
        db.session.commit()
        visit_id, _ = self._create_visit_with_item(
            status=VISIT_STATUS_NURSE_VERIFIED,
            quantity=2,
            unit_price=10,
            consultation_fee=5,
        )
        token = self._login("nurse1", "123456")

        response = self.client.post(
            f"/api/nurse/visits/{visit_id}/execute",
            headers=self._auth_headers(token),
            json={
                "payment_method": "card",
                "employee_discount": True,
                "actual_consultation_fee": 2,
                "actual_drug_amount": 15,
            },
        )
        self.assertEqual(response.status_code, 200)
        payment = Payment.query.filter_by(visit_id=visit_id).first()
        self.assertAlmostEqual(payment.amount, 17.0, places=6)
        self.assertAlmostEqual(payment.original_amount, 25.0, places=6)
        self.assertAlmostEqual(payment.actual_consultation_fee, 2.0, places=6)
        self.assertAlmostEqual(payment.actual_drug_amount, 15.0, places=6)

    def test_execute_rejects_legacy_negative_visit_amount(self):
        visit_id, _ = self._create_visit_with_item(
            status=VISIT_STATUS_NURSE_VERIFIED,
            quantity=2,
            unit_price=10,
            consultation_fee=-30,
        )
        token = self._login("nurse1", "123456")
        response = self.client.post(
            f"/api/nurse/visits/{visit_id}/execute",
            headers=self._auth_headers(token),
            json={"payment_method": "cash"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(Payment.query.filter_by(visit_id=visit_id).first())
        self.assertEqual(self.drug.stock, 100)


if __name__ == "__main__":
    unittest.main()

