import pandas as pd
import sqlite3
import numpy as np
from datetime import datetime, timezone

file_path = r'C:\Users\Administrator\Desktop\studentINF.xlsx'
db_path = r'e:\yws\backend\app.db'

try:
    print("Reading Excel file...")
    df = pd.read_excel(file_path)
    df.columns = [str(col).strip() for col in df.columns]

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Clear existing patients
    c.execute('DELETE FROM patient')
    c.execute("DELETE FROM sqlite_sequence WHERE name='patient'")

    success_count = 0
    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    
    records_to_insert = []

    print("Processing rows...")
    for idx, row in df.iterrows():
        student_id = str(row.get('学号', '')).strip()
        if not student_id or student_id == 'nan':
            continue

        name = str(row.get('姓名', '')).strip()
        gender = str(row.get('性别', '')).strip()
        if gender not in ['男', '女']:
            gender = '未知'

        phone = str(row.get('手机号码', '')).strip()
        if pd.isna(row.get('手机号码')) or phone == 'nan':
            phone = ''
            
        grade = str(row.get('年级', '')).strip()
        if grade.endswith('.0'):
            grade = grade[:-2]
            
        college = str(row.get('学院', '')).strip()
        major = str(row.get('专业', '')).strip()
        class_name = str(row.get('班级', '')).strip()

        records_to_insert.append((
            student_id, name, gender, grade, college, major, class_name, phone, now_str
        ))
        success_count += 1

    print(f"Inserting {len(records_to_insert)} records into database...")
    c.executemany('''
        INSERT INTO patient (student_id, name, gender, grade, college, major, class_name, phone, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', records_to_insert)

    conn.commit()
    conn.close()
    print(f'Successfully imported {success_count} students.')
except Exception as e:
    print(f'Error: {e}')
