import os
import tempfile
import unittest

from backend.app import create_app, db
from backend.app.models import Drug, InventoryRecord, OperationLog, User


class AdminSafetyWorkflowsTestCase(unittest.TestCase):
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

        admin = User(username="admin-test", real_name="管理员", role="admin")
        admin.set_password("123456")
        db.session.add(admin)
        db.session.commit()
        self.admin = admin
        login = self.client.post(
            "/api/auth/login",
            json={"username": "admin-test", "password": "123456"},
        )
        self.headers = {"Authorization": f"Bearer {login.get_json()['access_token']}"}

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()
        self.temp_dir.cleanup()

    def test_smart_inventory_requires_confirmation_and_preserves_batches(self):
        duplicate_a = Drug(
            name="药品A", type=1, specification="10片/盒", unit="盒",
            price=10, purchase_price=5, stock=2, status=1, batch_no="B1",
        )
        duplicate_b = Drug(
            name="药品A", type=1, specification="10片/盒", unit="盒",
            price=10, purchase_price=5, stock=3, status=1, batch_no="B1",
        )
        other_batch = Drug(
            name="药品A", type=1, specification="10片/盒", unit="盒",
            price=10, purchase_price=5, stock=7, status=1, batch_no="B2",
        )
        db.session.add_all([duplicate_a, duplicate_b, other_batch])
        db.session.flush()
        db.session.add_all([
            InventoryRecord(drug_id=duplicate_a.id, nurse_id=self.admin.id, old_stock=0, new_stock=2, remark="入库"),
            InventoryRecord(drug_id=duplicate_b.id, nurse_id=self.admin.id, old_stock=0, new_stock=3, remark="入库"),
        ])
        db.session.commit()

        scan = self.client.post(
            "/api/admin/drugs/smart-inventory",
            headers=self.headers,
            json={"threshold": 30},
        )
        self.assertEqual(scan.status_code, 200)
        scan_data = scan.get_json()["data"]
        self.assertTrue(scan_data["merge_confirmation_required"])
        self.assertEqual(len(scan_data["merge_candidates"]), 1)
        self.assertEqual(Drug.query.count(), 3)

        merge = self.client.post(
            "/api/admin/drugs/smart-inventory",
            headers=self.headers,
            json={
                "threshold": 30,
                "confirm_merge": True,
                "merge_candidate_ids": [
                    candidate["record_ids"] for candidate in scan_data["merge_candidates"]
                ],
            },
        )
        self.assertEqual(merge.status_code, 200)
        self.assertEqual(Drug.query.count(), 2)
        merged = Drug.query.filter_by(batch_no="B1").one()
        self.assertEqual(merged.stock, 5)
        self.assertEqual(Drug.query.filter_by(batch_no="B2").one().stock, 7)
        self.assertIsNotNone(OperationLog.query.filter_by(action_type="smart_inventory_merge").first())
        merge_record = InventoryRecord.query.filter_by(
            drug_id=merged.id,
            remark="智能盘库确认合并重复记录",
        ).one()
        self.assertEqual(merge_record.old_stock, merge_record.new_stock)
        total_delta = sum(
            record.new_stock - record.old_stock
            for record in InventoryRecord.query.filter_by(drug_id=merged.id).all()
        )
        self.assertEqual(total_delta, merged.stock)

    def test_sqlite_backup_get_downloads_database_file(self):
        response = self.client.get("/api/admin/backup", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/vnd.sqlite3")
        self.assertGreater(len(response.data), 0)
        backup_dir = os.path.join(self.temp_dir.name, "backups")
        self.assertEqual(len(os.listdir(backup_dir)), 1)
        response.close()
        self.assertEqual(len(os.listdir(backup_dir)), 0)

    def test_smart_inventory_rejects_stale_confirmation(self):
        drugs = [
            Drug(
                name="候选变化药品", type=1, specification="1盒", unit="盒",
                price=10, purchase_price=5, stock=1, status=1, batch_no="STALE",
            )
            for _ in range(2)
        ]
        db.session.add_all(drugs)
        db.session.commit()
        scan = self.client.post(
            "/api/admin/drugs/smart-inventory",
            headers=self.headers,
            json={"threshold": 30},
        ).get_json()["data"]
        preview_ids = scan["merge_candidates"][0]["record_ids"]

        db.session.add(Drug(
            name="候选变化药品", type=1, specification="1盒", unit="盒",
            price=10, purchase_price=5, stock=1, status=1, batch_no="STALE",
        ))
        db.session.commit()
        response = self.client.post(
            "/api/admin/drugs/smart-inventory",
            headers=self.headers,
            json={
                "threshold": 30,
                "confirm_merge": True,
                "merge_candidate_ids": [preview_ids],
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Drug.query.filter_by(batch_no="STALE").count(), 3)

    def test_admin_user_password_policy(self):
        weak = self.client.post(
            "/api/admin/users",
            headers=self.headers,
            json={
                "username": "weak-user",
                "real_name": "弱密码用户",
                "role": "finance",
                "password": "123456",
            },
        )
        self.assertEqual(weak.status_code, 400)

        strong = self.client.post(
            "/api/admin/users",
            headers=self.headers,
            json={
                "username": "strong-user",
                "real_name": "强密码用户",
                "role": "finance",
                "password": "strong-password-123",
            },
        )
        self.assertEqual(strong.status_code, 201)


if __name__ == "__main__":
    unittest.main()
