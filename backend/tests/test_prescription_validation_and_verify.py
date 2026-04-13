import unittest

from backend.app import create_app, db
from backend.app.models import Drug, Patient, User, Visit


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test-jwt"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class PrescriptionValidationAndVerifyTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        self.doctor = User(username="doctor", real_name="张医生", role="doctor")
        self.doctor.set_password("123456")
        self.nurse = User(username="nurse", real_name="李护士", role="nurse")
        self.nurse.set_password("123456")
        db.session.add(self.doctor)
        db.session.add(self.nurse)

        self.patient = Patient(student_id="2024001", name="张三", gender="男", phone="13800000000")
        db.session.add(self.patient)

        self.drug = Drug(
            name="药品A",
            type=1,
            specification="20 mg×100粒/瓶",
            unit="瓶",
            price=10.0,
            purchase_price=8.0,
            stock=10,
            status=1,
        )
        db.session.add(self.drug)
        db.session.commit()

        d_login = self.client.post("/api/auth/login", json={"username": "doctor", "password": "123456"})
        self.assertEqual(d_login.status_code, 200)
        self.doctor_headers = {"Authorization": f"Bearer {d_login.get_json()['access_token']}"}

        n_login = self.client.post("/api/auth/login", json={"username": "nurse", "password": "123456"})
        self.assertEqual(n_login.status_code, 200)
        self.nurse_headers = {"Authorization": f"Bearer {n_login.get_json()['access_token']}"}

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_create_visit_requires_diagnosis(self):
        payload = {
            "patient_id": self.patient.id,
            "consultation_fee": 0,
            "items": [
                {
                    "drug_id": self.drug.id,
                    "quantity": 1,
                    "usage": "口服",
                    "dosage": "1粒",
                    "frequency": "每日1次",
                    "timing": "餐后",
                    "days": 1,
                }
            ],
        }
        resp = self.client.post("/api/doctor/visits", json=payload, headers=self.doctor_headers)
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data.get("field"), "diagnosis")

    def test_create_visit_requires_items(self):
        payload = {
            "patient_id": self.patient.id,
            "diagnosis": "感冒",
            "items": [],
        }
        resp = self.client.post("/api/doctor/visits", json=payload, headers=self.doctor_headers)
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data.get("field"), "items")

    def test_create_visit_requires_dosage_for_drug(self):
        payload = {
            "patient_id": self.patient.id,
            "diagnosis": "感冒",
            "items": [
                {
                    "drug_id": self.drug.id,
                    "quantity": 1,
                    "usage": "口服",
                    "dosage": "",
                    "frequency": "每日1次",
                    "timing": "餐后",
                    "days": 1,
                }
            ],
        }
        resp = self.client.post("/api/doctor/visits", json=payload, headers=self.doctor_headers)
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data.get("field"), "dosage")
        self.assertEqual(data.get("item_index"), 0)

    def test_nurse_verify_checks_stock(self):
        payload = {
            "patient_id": self.patient.id,
            "diagnosis": "感冒",
            "items": [
                {
                    "drug_id": self.drug.id,
                    "quantity": 1,
                    "usage": "口服",
                    "dosage": "1粒",
                    "frequency": "每日1次",
                    "timing": "餐后",
                    "days": 1,
                }
            ],
        }
        resp = self.client.post("/api/doctor/visits", json=payload, headers=self.doctor_headers)
        self.assertEqual(resp.status_code, 201)
        visit_id = resp.get_json()["data"]["visit_id"]

        self.drug.stock = 0
        db.session.commit()

        vresp = self.client.post(f"/api/nurse/visits/{visit_id}/verify", json={}, headers=self.nurse_headers)
        self.assertEqual(vresp.status_code, 400)

    def test_create_visit_success(self):
        payload = {
            "patient_id": self.patient.id,
            "diagnosis": "感冒",
            "consultation_fee": 0,
            "items": [
                {
                    "drug_id": self.drug.id,
                    "quantity": 1,
                    "usage": "口服",
                    "dosage": "1粒",
                    "frequency": "每日1次",
                    "timing": "餐后",
                    "days": 1,
                }
            ],
        }
        resp = self.client.post("/api/doctor/visits", json=payload, headers=self.doctor_headers)
        self.assertEqual(resp.status_code, 201)
        vid = resp.get_json()["data"]["visit_id"]
        v = Visit.query.get(vid)
        self.assertIsNotNone(v)


if __name__ == "__main__":
    unittest.main()

