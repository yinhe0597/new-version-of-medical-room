import unittest

from backend.app import create_app, db
from backend.app.models import Drug, DrugStockGroup, User


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test-jwt"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DrugInboundStockTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        nurse = User(username="nurse", real_name="护士", role="nurse")
        nurse.set_password("123456")
        db.session.add(nurse)
        db.session.commit()

        resp = self.client.post("/api/auth/login", json={"username": "nurse", "password": "123456"})
        self.assertEqual(resp.status_code, 200)
        token = resp.get_json()["access_token"]
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_inbound_creates_pack_and_retail_and_group(self):
        payload = {
            "type": 1,
            "name": "药品A",
            "batch_no": "B001",
            "pack_specification": "20 mg×100粒/瓶",
            "pack_price": 10.0,
            "inbound_quantity": 3,
            "retail_enabled": True,
            "min_sale_unit": "2粒",
            "min_sale_price": 0.30,
        }
        resp = self.client.post("/api/nurse/inbound", json=payload, headers=self.headers)
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()["data"]
        self.assertIn("group_code", data)

        drugs = Drug.query.filter(Drug.batch_no == "B001").all()
        self.assertEqual(len(drugs), 2)

        group = DrugStockGroup.query.filter_by(group_code=data["group_code"]).first()
        self.assertIsNotNone(group)
        self.assertEqual(group.total_units, 300)
        self.assertEqual(group.pack_amount, 100)
        self.assertEqual(group.retail_amount, 2)

        pack = Drug.query.get(data["pack_drug_id"])
        retail = Drug.query.get(data["retail_drug_id"])
        self.assertEqual(pack.stock, 3)
        self.assertEqual(retail.stock, 150)

    def test_inbound_rejects_low_min_sale_price(self):
        payload = {
            "type": 1,
            "name": "药品B",
            "batch_no": "B002",
            "pack_specification": "20 mg×100粒/瓶",
            "pack_price": 10.0,
            "inbound_quantity": 1,
            "retail_enabled": True,
            "min_sale_unit": "1粒",
            "min_sale_price": 0.05,
        }
        resp = self.client.post("/api/nurse/inbound", json=payload, headers=self.headers)
        self.assertEqual(resp.status_code, 400)

    def test_inbound_duplicate_batch_returns_409(self):
        payload = {
            "type": 1,
            "name": "药品C",
            "batch_no": "B003",
            "pack_specification": "20 mg×100粒/瓶",
            "pack_price": 10.0,
            "inbound_quantity": 1,
            "retail_enabled": False,
        }
        r1 = self.client.post("/api/nurse/inbound", json=payload, headers=self.headers)
        self.assertEqual(r1.status_code, 201)
        r2 = self.client.post("/api/nurse/inbound", json=payload, headers=self.headers)
        self.assertEqual(r2.status_code, 409)


if __name__ == "__main__":
    unittest.main()

