import pandas as pd
import sqlite3
from pypinyin import lazy_pinyin, Style

file_path = r'E:\yws\国家临床版2.0疾病诊断编码（ICD-10）.xlsx'
db_path = r'e:\yws\backend\app.db'

def get_pinyin_variants(text):
    if not isinstance(text, str):
        return ""
    from pypinyin import pinyin
    # Initials
    pinyin_list_first = pinyin(text, style=Style.FIRST_LETTER, strict=False)
    initials = "".join([item[0] for item in pinyin_list_first if item]).lower()
    
    # Full pinyin
    pinyin_list_full = pinyin(text, style=Style.NORMAL, strict=False)
    full = "".join([item[0] for item in pinyin_list_full if item]).lower()
    
    return f"{initials}|{full}"

try:
    print("Reading ICD-10 Excel file...")
    df = pd.read_excel(file_path)
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Clear existing diagnosis
    c.execute('DELETE FROM diagnosis_dict')
    c.execute("DELETE FROM sqlite_sequence WHERE name='diagnosis_dict'")

    success_count = 0
    records_to_insert = []

    print("Processing rows...")
    for idx, row in df.iterrows():
        code = str(row.get('疾病诊断编码', '')).strip()
        name = str(row.get('疾病诊断名称', '')).strip()
        
        if not name or name == 'nan':
            continue
            
        pinyin = get_pinyin_variants(name)

        records_to_insert.append((code, name, pinyin))
        success_count += 1

    print(f"Inserting {len(records_to_insert)} records into database...")
    c.executemany('''
        INSERT INTO diagnosis_dict (code, name, pinyin)
        VALUES (?, ?, ?)
    ''', records_to_insert)

    conn.commit()
    conn.close()
    print(f'Successfully imported {success_count} diagnoses.')
except Exception as e:
    print(f'Error: {e}')
