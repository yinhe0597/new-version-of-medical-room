import os
import unittest
from unittest.mock import patch

from sqlalchemy import Column, Integer, MetaData, Table


with patch.dict(
    os.environ,
    {"MYSQL_PASSWORD": "migration-test-password", "MYSQL_DB": "medical_db"},
):
    from backend.migrate_to_mysql import (
        MigrationConfig,
        _modeled_destination_tables,
        _modeled_table_names,
    )


class MysqlMigrationSafetyTestCase(unittest.TestCase):
    def test_migration_app_disables_background_and_startup_data_writes(self):
        self.assertFalse(MigrationConfig.SCHEDULER_ENABLED)
        self.assertFalse(MigrationConfig.STARTUP_DATA_REPAIRS_ENABLED)

    def test_only_modeled_destination_tables_are_selected_for_clearing(self):
        model_metadata = MetaData()
        Table("user", model_metadata, Column("id", Integer, primary_key=True))
        Table("patient", model_metadata, Column("id", Integer, primary_key=True))

        destination_metadata = MetaData()
        Table("user", destination_metadata, Column("id", Integer, primary_key=True))
        Table("patient", destination_metadata, Column("id", Integer, primary_key=True))
        Table("operations_audit", destination_metadata, Column("id", Integer, primary_key=True))
        Table("alembic_version", destination_metadata, Column("id", Integer, primary_key=True))

        selected = _modeled_destination_tables(model_metadata, destination_metadata)

        self.assertEqual(_modeled_table_names(model_metadata), {"user", "patient"})
        self.assertEqual({table.name for table in selected}, {"user", "patient"})
        self.assertNotIn("operations_audit", {table.name for table in selected})
        self.assertNotIn("alembic_version", {table.name for table in selected})

    def test_missing_modeled_table_is_not_selected(self):
        model_metadata = MetaData()
        Table("user", model_metadata, Column("id", Integer, primary_key=True))
        Table("patient", model_metadata, Column("id", Integer, primary_key=True))

        destination_metadata = MetaData()
        Table("user", destination_metadata, Column("id", Integer, primary_key=True))
        Table("operations_audit", destination_metadata, Column("id", Integer, primary_key=True))

        selected = _modeled_destination_tables(model_metadata, destination_metadata)

        self.assertEqual([table.name for table in selected], ["user"])


if __name__ == "__main__":
    unittest.main()
