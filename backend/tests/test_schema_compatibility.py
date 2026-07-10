import os
import sqlite3
import tempfile
import unittest

from sqlalchemy import inspect
from sqlalchemy.dialects import mysql, sqlite

from backend.app import _mysql_legacy_type_upgrades, create_app, db
from backend.app.models import Patient, User


class SchemaCompatibilityTestCase(unittest.TestCase):
    def test_known_legacy_mysql_column_types_generate_controlled_alters(self):
        mysql_dialect = mysql.dialect()

        user_upgrades = _mysql_legacy_type_upgrades(
            mysql_dialect,
            db.metadata.tables["user"],
            [{
                "name": "password_hash",
                "type": mysql.VARCHAR(128),
                "nullable": False,
            }],
        )
        self.assertEqual(len(user_upgrades), 1)
        self.assertIn("MODIFY COLUMN password_hash VARCHAR(256) NOT NULL", user_upgrades[0]["sql"])
        self.assertIsNone(user_upgrades[0]["max_length_sql"])

        patient_upgrades = _mysql_legacy_type_upgrades(
            mysql_dialect,
            db.metadata.tables["patient"],
            [
                {"name": "name_pinyin", "type": mysql.TEXT(), "nullable": True},
                {"name": "name_initials", "type": mysql.TEXT(), "nullable": True},
            ],
        )
        self.assertEqual(len(patient_upgrades), 2)
        self.assertEqual(
            {upgrade["column_name"] for upgrade in patient_upgrades},
            {"name_pinyin", "name_initials"},
        )
        for upgrade in patient_upgrades:
            self.assertIn("VARCHAR(255) NULL", upgrade["sql"])
            self.assertIn("MAX(CHAR_LENGTH", upgrade["max_length_sql"])
            self.assertEqual(upgrade["max_length"], 255)

    def test_sqlite_never_generates_type_alters(self):
        upgrades = _mysql_legacy_type_upgrades(
            sqlite.dialect(),
            db.metadata.tables["user"],
            [{
                "name": "password_hash",
                "type": sqlite.VARCHAR(128),
                "nullable": True,
            }],
        )
        self.assertEqual(upgrades, [])

    def test_legacy_schema_is_synchronized_without_tcm_ghost_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "legacy.db")
            connection = sqlite3.connect(db_path)
            connection.execute(
                "CREATE TABLE patient ("
                "id INTEGER PRIMARY KEY, name VARCHAR(64), gender VARCHAR(10), "
                "is_temporary BOOLEAN DEFAULT 0)"
            )
            connection.execute(
                "INSERT INTO patient (id, name, gender, is_temporary) VALUES (1, '临时患者', '男', 1)"
            )
            connection.execute(
                "CREATE TABLE user ("
                "id INTEGER PRIMARY KEY, username VARCHAR(64), password_hash VARCHAR(256), "
                "real_name VARCHAR(64), role VARCHAR(20))"
            )
            connection.execute(
                "INSERT INTO user (id, username, real_name, role) "
                "VALUES (1, 'legacy-doctor', '历史医生', 'doctor')"
            )
            connection.execute(
                "CREATE TABLE inventory_record ("
                "id INTEGER PRIMARY KEY, drug_id INTEGER, nurse_id INTEGER, "
                "old_stock INTEGER, new_stock INTEGER, remark VARCHAR(200), timestamp DATETIME)"
            )
            connection.commit()
            connection.close()

            class TestConfig:
                TESTING = True
                SECRET_KEY = "test-secret-key-that-is-long-enough"
                JWT_SECRET_KEY = "test-jwt-key-that-is-long-enough"
                SQLALCHEMY_DATABASE_URI = "sqlite:///" + db_path
                SQLALCHEMY_TRACK_MODIFICATIONS = False
                CORS_ORIGINS = []

            app = create_app(TestConfig)
            with app.app_context():
                patient_columns = {
                    column["name"] for column in inspect(db.engine).get_columns("patient")
                }
                visit_columns = {
                    column["name"] for column in inspect(db.engine).get_columns("visit")
                }
                self.assertIn("patient_type", patient_columns)
                self.assertIn("department", patient_columns)
                self.assertNotIn("tcm_enabled", visit_columns)
                self.assertEqual(db.session.get(Patient, 1).patient_type, "temporary")
                user_columns = {
                    column["name"] for column in inspect(db.engine).get_columns("user")
                }
                self.assertIn("is_active", user_columns)
                self.assertTrue(db.session.get(User, 1).is_active)
                inventory_columns = {
                    column["name"] for column in inspect(db.engine).get_columns("inventory_record")
                }
                self.assertIn("operation_type", inventory_columns)
                db.session.remove()
                db.engine.dispose()


if __name__ == "__main__":
    unittest.main()
