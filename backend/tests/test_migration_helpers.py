import unittest

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text

from backend.migrations.migration_helpers import (
    ensure_foreign_key,
    ensure_index,
    ensure_unique,
)


class MigrationHelperTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.connection = self.engine.connect()

    def tearDown(self):
        self.connection.close()
        self.engine.dispose()

    def _operations(self):
        return Operations.context(MigrationContext.configure(self.connection))

    def test_equivalent_index_does_not_hide_name_collision(self):
        self.connection.execute(
            text("CREATE TABLE sample (id INTEGER PRIMARY KEY, a INTEGER, b INTEGER)")
        )
        self.connection.execute(text("CREATE INDEX equivalent_idx ON sample (a)"))
        self.connection.execute(text("CREATE INDEX expected_idx ON sample (b)"))

        with self._operations():
            with self.assertRaisesRegex(RuntimeError, "has shape"):
                ensure_index("expected_idx", "sample", ["a"])

    def test_partial_unique_index_does_not_satisfy_full_unique(self):
        self.connection.execute(
            text(
                "CREATE TABLE sample ("
                "id INTEGER PRIMARY KEY, value INTEGER, active INTEGER)"
            )
        )
        self.connection.execute(
            text(
                "CREATE UNIQUE INDEX partial_unique ON sample (value) "
                "WHERE active = 1"
            )
        )
        self.connection.execute(
            text(
                "INSERT INTO sample (id, value, active) "
                "VALUES (1, 7, 0), (2, 7, 0)"
            )
        )

        with self._operations():
            with self.assertRaisesRegex(RuntimeError, "duplicate key group"):
                ensure_unique("uq_sample_value", "sample", ["value"])

    def test_foreign_key_actions_must_match_default_semantics(self):
        self.connection.execute(text("PRAGMA foreign_keys=ON"))
        self.connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
        self.connection.execute(
            text(
                "CREATE TABLE child ("
                "id INTEGER PRIMARY KEY, parent_id INTEGER, "
                "FOREIGN KEY(parent_id) REFERENCES parent(id) ON DELETE CASCADE)"
            )
        )

        with self._operations():
            with self.assertRaisesRegex(RuntimeError, "incompatible options"):
                ensure_foreign_key(
                    "fk_child_parent_id_parent",
                    "child",
                    ["parent_id"],
                    "parent",
                    ["id"],
                )


if __name__ == "__main__":
    unittest.main()
