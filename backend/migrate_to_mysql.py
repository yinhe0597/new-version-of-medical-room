import os
import pymysql
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker
import sys

# Add the backend directory to sys.path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app, db
from config import Config

# MySQL Connection config
MYSQL_USER = os.environ.get("MYSQL_USER") or "root"
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD") or "123456"
MYSQL_HOST = os.environ.get("MYSQL_HOST") or "127.0.0.1"
MYSQL_PORT = int(os.environ.get("MYSQL_PORT") or 3306)
MYSQL_DB = os.environ.get("MYSQL_DB") or "medical_db"

MYSQL_URI_NO_DB = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/?charset=utf8mb4"
MYSQL_URI = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"

SQLITE_URI = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'app.db')

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

def repair_database_charset(mysql_engine):
    with mysql_engine.connect() as conn:
        conn.execute(db.text(f"ALTER DATABASE `{MYSQL_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"))
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
            conn.execute(
                db.text(
                    f"ALTER TABLE `{MYSQL_DB}`.`{table_name}` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
                )
            )
        conn.commit()

def migrate_data():
    # 1. Create a Flask app configured with the new MySQL URI
    class MigrationConfig(Config):
        SQLALCHEMY_DATABASE_URI = MYSQL_URI
        SQLALCHEMY_TRACK_MODIFICATIONS = False

    app = create_app(MigrationConfig)
    
    with app.app_context():
        print("Creating tables in MySQL...")
        db.create_all()
        print("Tables created.")
        print("Ensuring MySQL charset/collation is utf8mb4...")
        repair_database_charset(db.engine)

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

        with mysql_engine.connect() as mysql_conn:
            print("Disabling foreign key checks...")
            mysql_conn.execute(db.text("SET FOREIGN_KEY_CHECKS=0;"))
            
            # Iterate through tables in dependency order
            for table_name in sqlite_metadata.tables.keys():
                if table_name == 'alembic_version':
                    continue # Skip migration history table
                    
                print(f"Migrating table '{table_name}'...")
                
                sqlite_table = sqlite_metadata.tables[table_name]
                mysql_table = mysql_metadata.tables[table_name]
                
                # Fetch data from SQLite
                with sqlite_engine.connect() as sqlite_conn:
                    # Select all rows
                    result = sqlite_conn.execute(sqlite_table.select())
                    rows = result.mappings().all()
                    
                    if not rows:
                        print(f"  - Table '{table_name}' is empty. Skipping.")
                        continue
                    
                    print(f"  - Found {len(rows)} records. Inserting into MySQL...")
                    
                    # Convert mappings to dictionaries for insertion
                    records = [dict(row) for row in rows]
                    
                    # Insert into MySQL
                    # Clear existing data just in case
                    mysql_conn.execute(mysql_table.delete())
                    mysql_conn.execute(mysql_table.insert(), records)
                    mysql_conn.commit()
                    print(f"  - Migrated {len(rows)} records for '{table_name}'.")

            print("Re-enabling foreign key checks...")
            mysql_conn.execute(db.text("SET FOREIGN_KEY_CHECKS=1;"))
            mysql_conn.commit()
            
        print("\nMigration completed successfully!")

if __name__ == '__main__':
    create_database()
    migrate_data()
