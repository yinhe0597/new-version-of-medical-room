import sqlite3

db_path = "e:/yws/backend/app.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

def add_column(table, column, definition):
    try:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        print(f"Added {column} to {table}")
    except sqlite3.OperationalError as e:
        print(f"Error adding {column} to {table}: {e}")

add_column("drug", "purchase_price", "FLOAT DEFAULT 0.0")
add_column("drug", "has_scattered", "BOOLEAN DEFAULT 0")
add_column("drug", "scattered_price", "FLOAT")
add_column("drug", "conversion_rate", "INTEGER")
add_column("drug", "batch_no", "TEXT")
add_column("drug", "inbound_at", "DATETIME")

add_column("prescription_item", "is_scattered", "BOOLEAN DEFAULT 0")
add_column("prescription_item", "purchase_cost", "FLOAT DEFAULT 0.0")

add_column("patient", "name_pinyin", "TEXT")
add_column("patient", "name_initials", "TEXT")

conn.commit()
conn.close()
