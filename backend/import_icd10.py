import os
import sys
import pandas as pd
from pypinyin import pinyin, Style

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app import create_app, db
from backend.app.models import DiagnosisDict

def get_pinyin_variants(text):
    if not isinstance(text, str):
        return ""
    # Initials
    pinyin_list_first = pinyin(text, style=Style.FIRST_LETTER, strict=False)
    initials = "".join([item[0] for item in pinyin_list_first if item]).lower()
    
    # Full pinyin
    pinyin_list_full = pinyin(text, style=Style.NORMAL, strict=False)
    full = "".join([item[0] for item in pinyin_list_full if item]).lower()
    
    return f"{initials}|{full}"

def import_data(file_path):
    print(f"Reading Excel file: {file_path}...")
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return

    print("Data loaded. Processing...")
    
    app = create_app()
    with app.app_context():
        # Clear existing data if necessary, or just insert new ones
        count = DiagnosisDict.query.count()
        if count > 0:
            print(f"Database already contains {count} records. Clearing table...")
            db.session.query(DiagnosisDict).delete()
            db.session.commit()
            
        diagnoses = []
        for index, row in df.iterrows():
            code = str(row.get('疾病诊断编码', ''))
            name = str(row.get('疾病诊断名称', ''))
            
            if not code or not name or code == 'nan' or name == 'nan':
                continue

            py = get_pinyin_variants(name)
            
            diag = DiagnosisDict(
                code=code.strip(),
                name=name.strip(),
                pinyin=py
            )
            diagnoses.append(diag)
            
            if len(diagnoses) >= 1000:
                db.session.bulk_save_objects(diagnoses)
                db.session.commit()
                diagnoses = []
                print(f"Inserted {index + 1} records...")
                
        if diagnoses:
            db.session.bulk_save_objects(diagnoses)
            db.session.commit()
            
        print("Import completed successfully!")

if __name__ == '__main__':
    excel_path = '/workspace/.trae/specs/add-prescription-verification-workflow/国家临床版2.0疾病诊断编码（ICD-10）.xlsx'
    if not os.path.exists(excel_path):
        print(f"File not found: {excel_path}")
    else:
        import_data(excel_path)
