import os
import pymysql
from sqlalchemy import create_engine, MetaData
from sqlalchemy.engine import URL
import sys
import re

# Add the project root so imports match all other entry points.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app import create_app, db
from backend.config import Config

# MySQL Connection config
MYSQL_USER = os.environ.get("MYSQL_USER") or "root"
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD")
MYSQL_HOST = os.environ.get("MYSQL_HOST") or "127.0.0.1"
MYSQL_PORT = int(os.environ.get("MYSQL_PORT") or 3306)
MYSQL_DB = os.environ.get("MYSQL_DB") or "medical_db"

if not MYSQL_PASSWORD:
    raise RuntimeError("MYSQL_PASSWORD environment variable is required")
if not re.fullmatch(r"[A-Za-z0-9_]+", MYSQL_DB):
    raise RuntimeError("MYSQL_DB may only contain letters, numbers, and underscores")

MYSQL_URI = URL.create(
    "mysql+pymysql",
    username=MYSQL_USER,
    password=MYSQL_PASSWORD,
    host=MYSQL_HOST,
    port=MYSQL_PORT,
    database=MYSQL_DB,
    query={"charset": "utf8mb4"},
).render_as_string(hide_password=False)

SQLITE_PATH = os.environ.get("SQLITE_DB_PATH") or os.path.join(ROOT_DIR, "data", "app.db")
SQLITE_URI = 'sqlite:///' + os.path.abspath(SQLITE_PATH)


class MigrationConfig(Config):
    SQLALCHEMY_DATABASE_URI = MYSQL_URI
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "connect_args": {"charset": "utf8mb4"},
    }
    SCHEDULER_ENABLED = False
    STARTUP_DATA_REPAIRS_ENABLED = False


def _modeled_table_names(model_metadata):
    return {table.name for table in model_metadata.sorted_tables}


def _modeled_destination_tables(model_metadata, destination_metadata):
    """Return destination tables that are owned by the current ORM metadata."""
    modeled_names = _modeled_table_names(model_metadata)
    destination_by_name = {
        table.name: table for table in destination_metadata.sorted_tables
    }
    return [
        destination_by_name[model_table.name]
        for model_table in model_metadata.sorted_tables
        if model_table.name in modeled_names and model_table.name in destination_by_name
    ]


def create_database():
    print("Connecting to MySQL to create database...")
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            port=MYSQL_PORT,
            charset="utf8mb4",
        )
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_DB} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        cursor.execute(f"ALTER DATABASE {MYSQL_DB} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        conn.commit()
        cursor.close()
        conn.close()
        print(f"Database '{MYSQL_DB}' ensured.")
    except Exception as e:
        print(f"Error creating database: {e}")
        sys.exit(1)

def repair_database_charset(mysql_engine, modeled_table_names):
    modeled_table_names = set(modeled_table_names)
    preparer = mysql_engine.dialect.identifier_preparer
    database_name = preparer.quote(MYSQL_DB)
    with mysql_engine.connect() as conn:
        conn.execute(db.text(
            f"ALTER DATABASE {database_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
        ))
        conn.commit()

        rows = conn.execute(
            db.text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = :db
                  AND table_type = 'BASE TABLE'
                """
            ),
            {"db": MYSQL_DB},
        ).fetchall()
        for (table_name,) in rows:
            if table_name not in modeled_table_names:
                continue
            quoted_table = preparer.quote(table_name)
            conn.execute(
                db.text(
                    f"ALTER TABLE {database_name}.{quoted_table} "
                    "CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
                )
            )
        conn.commit()

def migrate_data():
    if not os.path.isfile(os.path.abspath(SQLITE_PATH)):
        raise RuntimeError(f"SQLite source database not found: {SQLITE_PATH}")
    # 1. Create a Flask app configured with the new MySQL URI
    app = create_app(MigrationConfig)
    
    with app.app_context():
        print("Creating tables in MySQL...")
        db.create_all()
        print("Tables created.")
        print("Ensuring MySQL charset/collation is utf8mb4...")
        repair_database_charset(db.engine, _modeled_table_names(db.metadata))

        print("Setting up engines for data migration...")
        # Engine for SQLite (source)
        sqlite_engine = create_engine(SQLITE_URI)
        
        # Engine for MySQL (destination)
        mysql_engine = db.engine

        # Reflect tables from SQLite
        sqlite_metadata = MetaData()
        sqlite_metadata.reflect(bind=sqlite_engine)

        # Reflect tables from MySQL
        mysql_metadata = MetaData()
        mysql_metadata.reflect(bind=mysql_engine)
        modeled_mysql_tables = _modeled_destination_tables(db.metadata, mysql_metadata)
        modeled_mysql_table_names = {table.name for table in modeled_mysql_tables}

        with sqlite_engine.connect() as sqlite_conn, mysql_engine.connect() as mysql_conn:
            sqlite_conn.exec_driver_sql("BEGIN")
            transaction = mysql_conn.begin()
            print("Disabling foreign key checks...")
            try:
                mysql_conn.execute(db.text("SET FOREIGN_KEY_CHECKS=0;"))

                # Only clear tables owned by this application's current ORM.
                # Reflected extension/operations tables may share the database
                # and must never be touched by this migration.
                for mysql_table in reversed(modeled_mysql_tables):
                    mysql_conn.execute(mysql_table.delete())

                # Copy every modeled table in one transaction so a failed run
                # cannot leave the destination half migrated.
                for table_name in sqlite_metadata.tables.keys():
                    if table_name == 'alembic_version':
                        continue  # Skip migration history table
                    if table_name not in modeled_mysql_table_names:
                        print(f"  - Destination has no current ORM model for '{table_name}', skipping.")
                        continue

                    print(f"Migrating table '{table_name}'...")
                    sqlite_table = sqlite_metadata.tables[table_name]
                    mysql_table = mysql_metadata.tables[table_name]

                    rows = sqlite_conn.execute(sqlite_table.select()).mappings().all()

                    destination_columns = set(mysql_table.c.keys())
                    records = [
                        {key: value for key, value in dict(row).items() if key in destination_columns}
                        for row in rows
                    ]

                    if records:
                        print(f"  - Found {len(records)} records. Inserting into MySQL...")
                        mysql_conn.execute(mysql_table.insert(), records)
                    print(f"  - Migrated {len(records)} records for '{table_name}'.")

                for mysql_table in modeled_mysql_tables:
                    for constraint in mysql_table.foreign_key_constraints:
                        if len(constraint.elements) != 1:
                            raise RuntimeError(
                                f"Composite foreign key validation is not supported: {constraint.name}"
                            )
                        element = next(iter(constraint.elements))
                        child_column = element.parent
                        parent_column = element.column
                        orphan_count = mysql_conn.execute(
                            db.select(db.func.count())
                            .select_from(mysql_table.outerjoin(
                                parent_column.table,
                                child_column == parent_column,
                            ))
                            .where(
                                child_column.is_not(None),
                                parent_column.is_(None),
                            )
                        ).scalar_one()
                        if orphan_count:
                            raise RuntimeError(
                                f"Foreign key validation failed for {mysql_table.name}.{child_column.name}: "
                                f"{orphan_count} orphaned rows"
                            )

                print("Re-enabling foreign key checks...")
                mysql_conn.execute(db.text("SET FOREIGN_KEY_CHECKS=1;"))
                transaction.commit()
            except Exception:
                if transaction.is_active:
                    transaction.rollback()
                # FOREIGN_KEY_CHECKS is session-scoped. Restore it explicitly
                # before returning this pooled connection.
                try:
                    mysql_conn.execute(db.text("SET FOREIGN_KEY_CHECKS=1;"))
                    mysql_conn.commit()
                except Exception:
                    mysql_conn.invalidate()
                raise
            
        print("\nMigration completed successfully!")

if __name__ == '__main__':
    create_database()
    migrate_data()
