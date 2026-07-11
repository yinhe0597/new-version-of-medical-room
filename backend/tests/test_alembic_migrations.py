import os
from pathlib import Path
import tempfile
import unittest

from flask_migrate import upgrade
from sqlalchemy import inspect, text
from sqlalchemy.schema import UniqueConstraint

from backend.app import _sync_model_schema, create_migration_app, db


MIGRATIONS_DIR = str(Path(__file__).resolve().parents[1] / "migrations")
CURRENT_HEAD = "b6e1d8f3a2c4"
HISTORICAL_SPLIT_REVISION = "bbf28ffdb4c0"
PRE_BASELINE_HEAD = "e7f8a9b0c1d2"


def migration_config(db_path):
    return type(
        "MigrationTestConfig",
        (),
        {
            "TESTING": True,
            "SECRET_KEY": "migration-test-secret",
            "JWT_SECRET_KEY": "migration-test-jwt-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + db_path,
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "CORS_ORIGINS": [],
            "SCHEDULER_ENABLED": False,
            "STARTUP_DATA_REPAIRS_ENABLED": False,
        },
    )


class AlembicMigrationTestCase(unittest.TestCase):
    def _run_with_database(self, callback):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "migration.db")
            app = create_migration_app(migration_config(db_path))
            try:
                with app.app_context():
                    callback()
                    db.session.remove()
                    db.engine.dispose()
            finally:
                with app.app_context():
                    db.session.remove()
                    db.engine.dispose()

    def test_empty_sqlite_upgrades_from_base_to_current_head(self):
        def assertions():
            self.assertEqual(inspect(db.engine).get_table_names(), [])

            upgrade(directory=MIGRATIONS_DIR)

            inspector = inspect(db.engine)
            tables = set(inspector.get_table_names())
            model_tables = set(db.metadata.tables)
            self.assertEqual(tables - {"alembic_version"}, model_tables)
            self.assertEqual(
                db.session.execute(text("SELECT version_num FROM alembic_version")).scalar_one(),
                CURRENT_HEAD,
            )

            allowed_legacy_columns = {"drug": {"monthly_sort_order"}}
            for table_name, model_table in db.metadata.tables.items():
                model_columns = set(model_table.columns.keys())
                actual_columns = {
                    column["name"] for column in inspector.get_columns(table_name)
                }
                self.assertEqual(actual_columns - model_columns, allowed_legacy_columns.get(table_name, set()))
                self.assertEqual(model_columns - actual_columns, set())

                model_index_semantics = {
                    (tuple(column.name for column in index.columns), bool(index.unique))
                    for index in model_table.indexes
                }
                model_index_semantics.update(
                    {
                        (tuple(column.name for column in constraint.columns), True)
                        for constraint in model_table.constraints
                        if isinstance(constraint, UniqueConstraint)
                    }
                )
                actual_index_semantics = {
                    (tuple(index.get("column_names") or ()), bool(index.get("unique")))
                    for index in inspector.get_indexes(table_name)
                }
                actual_index_semantics.update(
                    {
                        (tuple(constraint.get("column_names") or ()), True)
                        for constraint in inspector.get_unique_constraints(table_name)
                    }
                )
                self.assertEqual(actual_index_semantics, model_index_semantics, table_name)

            expected_columns = {
                "drug": {
                    "batch_no",
                    "inbound_at",
                    "purchase_price",
                    "storage_location",
                    "expiry_date",
                },
                "patient": {
                    "name_pinyin",
                    "name_initials",
                    "patient_type",
                    "department",
                    "shop_name",
                },
                "payment": {
                    "is_employee_discount",
                    "original_amount",
                    "receipt_snapshot",
                    "actual_consultation_fee",
                    "actual_drug_amount",
                },
                "prescription_item": {
                    "purchase_cost",
                    "is_intravenous",
                    "infusion_group",
                    "infusion_dosage_value",
                    "infusion_dosage_unit",
                    "infusion_method",
                },
                "user": {"token_version", "is_active"},
                "visit": {"special_note", "revoked_by", "revoked_at", "revoke_reason"},
                "inventory_record": {"visit_id", "operation_type"},
            }
            for table_name, required in expected_columns.items():
                actual = {
                    column["name"] for column in inspector.get_columns(table_name)
                }
                self.assertTrue(required.issubset(actual), table_name)

            password_hash = next(
                column
                for column in inspector.get_columns("user")
                if column["name"] == "password_hash"
            )
            self.assertEqual(password_hash["type"].length, 256)

            snapshot_uniques = {
                frozenset(constraint.get("column_names") or ())
                for constraint in inspector.get_unique_constraints("daily_stock_snapshot")
            }
            self.assertIn(frozenset({"drug_id", "date"}), snapshot_uniques)

            revoked_foreign_keys = [
                foreign_key
                for foreign_key in inspector.get_foreign_keys("visit")
                if foreign_key.get("constrained_columns") == ["revoked_by"]
            ]
            self.assertEqual(len(revoked_foreign_keys), 1)
            self.assertEqual(revoked_foreign_keys[0]["referred_table"], "user")

        self._run_with_database(assertions)

    def test_upgrade_preserves_historical_rows_and_accepts_runtime_synced_schema(self):
        def assertions():
            upgrade(directory=MIGRATIONS_DIR, revision=HISTORICAL_SPLIT_REVISION)
            db.session.execute(
                text(
                    "INSERT INTO user (id, username, password_hash, real_name, role) "
                    "VALUES (1, 'legacy-admin', 'legacy-hash', 'Legacy Admin', 'admin')"
                )
            )
            db.session.execute(
                text(
                    "INSERT INTO patient "
                    "(id, student_id, name, gender, class_name, phone, created_at) "
                    "VALUES (1, 'legacy-001', 'Legacy Patient', 'X', 'Class 1', NULL, NULL)"
                )
            )
            db.session.execute(
                text(
                    "INSERT INTO drug "
                    "(id, name, specification, unit, price, stock, status, type) "
                    "VALUES (1, 'Legacy Drug', '10mg', 'box', 12.5, 7, 1, 1)"
                )
            )
            db.session.commit()

            upgrade(directory=MIGRATIONS_DIR, revision=PRE_BASELINE_HEAD)
            self.assertEqual(
                db.session.execute(text("SELECT name FROM drug WHERE id = 1")).scalar_one(),
                "Legacy Drug",
            )
            self.assertEqual(
                db.session.execute(text("SELECT stock FROM drug WHERE id = 1")).scalar_one(),
                7,
            )

            db.session.remove()
            _sync_model_schema(app)

        # _sync_model_schema needs the Flask app, so keep this path explicit.
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "legacy.db")
            app = create_migration_app(migration_config(db_path))
            try:
                with app.app_context():
                    assertions()
                    upgrade(directory=MIGRATIONS_DIR)

                    self.assertEqual(
                        db.session.execute(
                            text("SELECT username FROM user WHERE id = 1")
                        ).scalar_one(),
                        "legacy-admin",
                    )
                    self.assertEqual(
                        db.session.execute(
                            text("SELECT name FROM patient WHERE id = 1")
                        ).scalar_one(),
                        "Legacy Patient",
                    )
                    self.assertEqual(
                        db.session.execute(
                            text("SELECT version_num FROM alembic_version")
                        ).scalar_one(),
                        CURRENT_HEAD,
                    )
                    self.assertIn(
                        "operation_type",
                        {
                            column["name"]
                            for column in inspect(db.engine).get_columns("inventory_record")
                        },
                    )
                    db.session.remove()
                    db.engine.dispose()
            finally:
                with app.app_context():
                    db.session.remove()
                    db.engine.dispose()


if __name__ == "__main__":
    unittest.main()
