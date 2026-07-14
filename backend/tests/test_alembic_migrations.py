import os
from pathlib import Path
import tempfile
import unittest

from flask import current_app
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text
from sqlalchemy.schema import UniqueConstraint

from backend.app import (
    _assert_database_at_alembic_head,
    _sync_model_schema,
    create_migration_app,
    db,
)


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
            self.assertEqual(
                db.session.execute(text("PRAGMA foreign_keys")).scalar_one(),
                1,
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

                actual_columns_by_name = {
                    column["name"]: column
                    for column in inspector.get_columns(table_name)
                }
                for model_column in model_table.columns:
                    actual_column = actual_columns_by_name[model_column.name]
                    self.assertIs(
                        actual_column["type"]._type_affinity,
                        model_column.type._type_affinity,
                        f"{table_name}.{model_column.name}",
                    )
                    expected_length = getattr(model_column.type, "length", None)
                    if expected_length is not None:
                        self.assertEqual(
                            getattr(actual_column["type"], "length", None),
                            expected_length,
                            f"{table_name}.{model_column.name}",
                        )
                    self.assertEqual(
                        actual_column["nullable"],
                        model_column.nullable,
                        f"{table_name}.{model_column.name}",
                    )

                model_foreign_keys = {
                    (
                        tuple(column.name for column in constraint.columns),
                        constraint.referred_table.name,
                        tuple(element.column.name for element in constraint.elements),
                    )
                    for constraint in model_table.foreign_key_constraints
                }
                actual_foreign_keys = {
                    (
                        tuple(foreign_key.get("constrained_columns") or ()),
                        foreign_key.get("referred_table"),
                        tuple(foreign_key.get("referred_columns") or ()),
                    )
                    for foreign_key in inspector.get_foreign_keys(table_name)
                }
                self.assertEqual(
                    actual_foreign_keys,
                    model_foreign_keys,
                    table_name,
                )

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

    def test_production_head_guard_rejects_unversioned_database(self):
        def assertions():
            with self.assertRaisesRegex(RuntimeError, "current=<unversioned>"):
                _assert_database_at_alembic_head(current_app._get_current_object())

        self._run_with_database(assertions)

    def test_production_head_guard_accepts_current_head(self):
        def assertions():
            upgrade(directory=MIGRATIONS_DIR)
            _assert_database_at_alembic_head(current_app._get_current_object())

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
            db.session.execute(
                text(
                    "INSERT INTO visit (id, patient_id, doctor_id, status) "
                    "VALUES (1, 1, 1, 'pending')"
                )
            )
            db.session.execute(
                text(
                    "INSERT INTO payment (id, visit_id, nurse_id, amount) "
                    "VALUES (1, 1, 1, 12.5)"
                )
            )
            db.session.execute(
                text(
                    "INSERT INTO prescription_item "
                    "(id, visit_id, drug_id, quantity, price_at_visit, amount) "
                    "VALUES (1, 1, 1, 1, 12.5, 12.5)"
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

    def test_upgrade_repairs_legacy_inventory_table_and_preserves_orphans(self):
        def assertions():
            upgrade(directory=MIGRATIONS_DIR, revision=HISTORICAL_SPLIT_REVISION)
            db.session.execute(
                text(
                    "INSERT INTO user (id, username, password_hash, real_name, role) "
                    "VALUES (1, 'legacy-nurse', 'legacy-hash', 'Legacy Nurse', 'nurse')"
                )
            )
            db.session.execute(
                text(
                    "INSERT INTO drug "
                    "(id, name, specification, unit, price, stock, status, type) "
                    "VALUES (1, 'Deleted Drug', '10mg', 'box', 12.5, 0, 1, 1)"
                )
            )
            db.session.execute(
                text(
                    "CREATE TABLE inventory_record ("
                    "id INTEGER NOT NULL PRIMARY KEY, "
                    "drug_id INTEGER, nurse_id INTEGER, old_stock INTEGER, "
                    "new_stock INTEGER, remark VARCHAR(200), timestamp DATETIME, "
                    "FOREIGN KEY(drug_id) REFERENCES drug(id), "
                    "FOREIGN KEY(nurse_id) REFERENCES user(id))"
                )
            )
            db.session.execute(
                text(
                    "INSERT INTO inventory_record "
                    "(id, drug_id, nurse_id, old_stock, new_stock, remark) "
                    "VALUES (1, 1, 1, 2, 0, 'legacy outbound')"
                )
            )
            db.session.commit()

            db.session.remove()
            with db.engine.connect() as connection:
                connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
                connection.commit()
                connection.execute(text("DELETE FROM drug WHERE id = 1"))
                connection.commit()
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()

            upgrade(directory=MIGRATIONS_DIR)

            columns = {
                column["name"]
                for column in inspect(db.engine).get_columns("inventory_record")
            }
            self.assertTrue({"visit_id", "operation_type"}.issubset(columns))
            self.assertEqual(
                db.session.execute(
                    text(
                        "SELECT old_stock, new_stock, remark "
                        "FROM inventory_record WHERE id = 1"
                    )
                ).one(),
                (2, 0, "legacy outbound"),
            )
            violations = db.session.execute(text("PRAGMA foreign_key_check")).all()
            self.assertEqual(
                [
                    (row[0], row[1], row[2])
                    for row in violations
                ],
                [("inventory_record", 1, "drug")],
            )
            self.assertEqual(
                db.session.execute(text("PRAGMA foreign_keys")).scalar_one(),
                1,
            )

        self._run_with_database(assertions)

    def test_late_upgrade_failure_rolls_back_and_restores_foreign_keys(self):
        def assertions():
            upgrade(directory=MIGRATIONS_DIR, revision=HISTORICAL_SPLIT_REVISION)
            db.session.execute(
                text(
                    "CREATE TABLE drug_stock_group ("
                    "id INTEGER NOT NULL PRIMARY KEY)"
                )
            )
            db.session.commit()

            with self.assertRaises(SystemExit) as raised:
                upgrade(directory=MIGRATIONS_DIR)
            self.assertEqual(raised.exception.code, 1)

            db.session.remove()
            with db.engine.connect() as connection:
                self.assertEqual(
                    connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    ).scalar_one(),
                    HISTORICAL_SPLIT_REVISION,
                )
                patient_columns = {
                    column["name"]
                    for column in inspect(connection).get_columns("patient")
                }
                drug_columns = {
                    column["name"]
                    for column in inspect(connection).get_columns("drug")
                }
                visit_columns = {
                    column["name"]
                    for column in inspect(connection).get_columns("visit")
                }
                self.assertNotIn("is_temporary", patient_columns)
                self.assertNotIn("counselor_name", patient_columns)
                self.assertNotIn("batch_no", drug_columns)
                self.assertNotIn("verified_by", visit_columns)
                self.assertEqual(
                    {
                        column["name"]
                        for column in inspect(connection).get_columns(
                            "drug_stock_group"
                        )
                    },
                    {"id"},
                )
                self.assertEqual(
                    connection.exec_driver_sql("PRAGMA foreign_keys").scalar(),
                    1,
                )

        self._run_with_database(assertions)

    def test_empty_partial_unversioned_schema_can_resume(self):
        def assertions():
            db.session.execute(
                text(
                    "CREATE TABLE drug ("
                    "id INTEGER NOT NULL PRIMARY KEY, name VARCHAR(128), "
                    "specification VARCHAR(50), unit VARCHAR(10), price FLOAT, "
                    "stock INTEGER, status INTEGER)"
                )
            )
            db.session.commit()

            upgrade(directory=MIGRATIONS_DIR)

            self.assertEqual(
                db.session.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one(),
                CURRENT_HEAD,
            )
            self.assertEqual(
                set(inspect(db.engine).get_table_names()) - {"alembic_version"},
                set(db.metadata.tables),
            )

        self._run_with_database(assertions)

    def test_nonempty_partial_unversioned_schema_is_rejected(self):
        def assertions():
            db.session.execute(
                text(
                    "CREATE TABLE drug ("
                    "id INTEGER NOT NULL PRIMARY KEY, name VARCHAR(128), "
                    "specification VARCHAR(50), unit VARCHAR(10), price FLOAT, "
                    "stock INTEGER, status INTEGER)"
                )
            )
            db.session.execute(
                text(
                    "INSERT INTO drug "
                    "(id, name, specification, unit, price, stock, status) "
                    "VALUES (1, 'Existing Drug', '10mg', 'box', 1.0, 1, 1)"
                )
            )
            db.session.commit()

            with self.assertRaises(SystemExit) as raised:
                upgrade(directory=MIGRATIONS_DIR)
            self.assertEqual(raised.exception.code, 1)
            self.assertEqual(
                db.session.execute(text("SELECT name FROM drug WHERE id = 1")).scalar_one(),
                "Existing Drug",
            )

        self._run_with_database(assertions)

    def test_downgrade_is_refused_without_mutating_data(self):
        def assertions():
            upgrade(directory=MIGRATIONS_DIR)
            db.session.execute(
                text(
                    "INSERT INTO user "
                    "(id, username, password_hash, real_name, role) "
                    "VALUES (1, 'keep-me', 'hash', 'Keep Me', 'admin')"
                )
            )
            db.session.commit()

            with self.assertRaises(SystemExit) as raised:
                downgrade(directory=MIGRATIONS_DIR, revision="-1")
            self.assertEqual(raised.exception.code, 1)
            self.assertEqual(
                db.session.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one(),
                CURRENT_HEAD,
            )
            self.assertEqual(
                db.session.execute(
                    text("SELECT username FROM user WHERE id = 1")
                ).scalar_one(),
                "keep-me",
            )

        self._run_with_database(assertions)

    def test_offline_sql_generation_is_explicitly_rejected(self):
        def assertions():
            with self.assertRaises(SystemExit) as raised:
                upgrade(directory=MIGRATIONS_DIR, sql=True)
            self.assertEqual(raised.exception.code, 1)
            self.assertEqual(inspect(db.engine).get_table_names(), [])

        self._run_with_database(assertions)


if __name__ == "__main__":
    unittest.main()
