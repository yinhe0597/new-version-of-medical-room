import os
import sys
import argparse
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

def import_data(file_path, sheet=None):
    print(f"Reading Excel file: {file_path}...")
    try:
        if sheet is None:
            df = pd.read_excel(file_path)
        else:
            df = pd.read_excel(file_path, sheet_name=sheet)
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return

    print("Data loaded. Processing...")
    
    app = create_app()
    with app.app_context():
        existing_by_code = {
            (d.code or ""): d
            for d in DiagnosisDict.query.filter(DiagnosisDict.code.isnot(None)).all()
            if (d.code or "").strip()
        }

        inserted = 0
        updated = 0
        processed = 0

        for index, row in df.iterrows():
            raw_code = row.get('疾病诊断编码', '')
            raw_name = row.get('疾病诊断名称', '')
            code = str(raw_code).strip() if raw_code is not None else ""
            name = str(raw_name).strip() if raw_name is not None else ""

            if not code or not name or code == 'nan' or name == 'nan':
                continue

            processed += 1
            py = get_pinyin_variants(name)

            existing = existing_by_code.get(code)
            if existing is None:
                db.session.add(DiagnosisDict(code=code, name=name, pinyin=py))
                existing_by_code[code] = True
                inserted += 1
            else:
                changed = False
                if (existing.name or "").strip() != name:
                    existing.name = name
                    changed = True
                if (existing.pinyin or "").strip() != py:
                    existing.pinyin = py
                    changed = True
                if changed:
                    updated += 1

            if processed % 2000 == 0:
                db.session.commit()
                print(f"Processed {processed} rows, inserted {inserted}, updated {updated}...")

        db.session.commit()
        print(f"Import completed successfully! processed={processed}, inserted={inserted}, updated={updated}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("excel_path", nargs="?", default=None)
    parser.add_argument("--sheet", default=None)
    args = parser.parse_args()

    excel_path = args.excel_path
    if not excel_path:
        excel_path = os.path.join(ROOT_DIR, "国家临床版2.0疾病诊断编码（ICD-10）.xlsx")

    if not os.path.exists(excel_path):
        print(f"File not found: {excel_path}")
        sys.exit(1)

    import_data(excel_path, sheet=args.sheet)
