import io
import re
import unittest

from backend.app import create_app, db
from backend.app.models import Patient, User


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test-jwt-secret-key-at-least-32-bytes"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class AdminPatientImportRequiredFieldsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        admin = User(username="admin", real_name="管理员", role="admin")
        admin.set_password("123456")
        db.session.add(admin)
        db.session.commit()

        login_resp = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "123456"},
        )
        self.token = login_resp.get_json()["access_token"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _upload_csv(self, csv_text):
        payload = csv_text.encode("utf-8-sig")
        data = {
            "file": (io.BytesIO(payload), "students.csv"),
        }
        return self.client.post(
            "/api/admin/patients/import",
            data=data,
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def _parse_counts(self, msg):
        m = re.search(r"Success:\s*(\d+),\s*Errors:\s*(\d+)", msg or "")
        self.assertIsNotNone(m)
        return int(m.group(1)), int(m.group(2))

    def test_import_requires_all_fields_except_phone(self):
        csv_text = (
            "学号,姓名,性别,手机号码,年级,学院,专业,班级,年龄,辅导员姓名\n"
            "2024001,张三,男,,2024级,计算机学院,软件工程,软件一班,19,\n"
        )
        resp = self._upload_csv(csv_text)
        self.assertEqual(resp.status_code, 200)
        success, errors = self._parse_counts(resp.get_json()["msg"])
        self.assertEqual(success, 0)
        self.assertEqual(errors, 1)
        self.assertEqual(Patient.query.count(), 0)

    def test_import_allows_empty_phone_and_persists_other_fields(self):
        csv_text = (
            "学号,姓名,性别,手机号码,年级,学院,专业,班级,年龄,辅导员姓名\n"
            "2024001,张三,,,2024级,,,软件一班,,王老师\n"
        )
        resp = self._upload_csv(csv_text)
        self.assertEqual(resp.status_code, 200)
        success, errors = self._parse_counts(resp.get_json()["msg"])
        self.assertEqual(success, 1)
        self.assertEqual(errors, 0)

        p = Patient.query.filter_by(student_id="2024001").first()
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "张三")
        self.assertEqual(p.grade, "2024级")
        self.assertEqual(p.class_name, "软件一班")
        self.assertIsNone(p.phone)
        self.assertEqual(p.counselor_name, "王老师")


if __name__ == "__main__":
    unittest.main()
