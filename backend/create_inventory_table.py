import sqlite3

db_path = "e:/yws/backend/app.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

try:
    c.execute("""
        CREATE TABLE inventory_record (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
            drug_id INTEGER, 
            nurse_id INTEGER, 
            old_stock INTEGER, 
            new_stock INTEGER, 
            remark VARCHAR(200), 
            timestamp DATETIME, 
            FOREIGN KEY(drug_id) REFERENCES drug (id), 
            FOREIGN KEY(nurse_id) REFERENCES user (id)
        )
    """)
    print("Table created.")
except Exception as e:
    print(f"Error: {e}")

conn.commit()
conn.close()
