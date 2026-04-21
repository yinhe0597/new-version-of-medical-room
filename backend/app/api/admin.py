from flask import request, jsonify, send_file, make_response, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.app import db
from backend.app.api import bp
from backend.app.models import User, Drug, Payment, Visit, PrescriptionItem, Patient
from backend.app.utils.decorators import role_required
from datetime import datetime, date, timedelta
from sqlalchemy import func
from sqlalchemy.orm import aliased
import os
import shutil
import csv
import io
import subprocess
from sqlalchemy.exc import IntegrityError

from pypinyin import pinyin, Style

def _name_pinyin_parts(text):
    if not isinstance(text, str) or not text:
        return "", ""
    initials_list = pinyin(text, style=Style.FIRST_LETTER, strict=False)
    initials = "".join([x[0] for x in initials_list if x]).lower()
    full_list = pinyin(text, style=Style.NORMAL, strict=False)
    full = "".join([x[0] for x in full_list if x]).lower()
    return full, initials

@bp.route('/admin/backup/mysql', methods=['GET'])
@role_required('admin')
def backup_mysql_database():
    try:
        uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if not uri.startswith('mysql'):
            return jsonify({"msg": "Backup is only supported for MySQL databases in this version."}), 400

        # 解析 mysql 连接字符串
        # 格式: mysql+pymysql://user:password@host:port/dbname?charset=utf8mb4
        # 移除 'mysql+pymysql://'
        conn_str = uri.split('://', 1)[1]
        
        # 提取 user:password
        auth_part, rest = conn_str.split('@', 1)
        user, password = auth_part.split(':', 1)
        
        # 提取 host:port 和 dbname
        host_port_part, db_part = rest.split('/', 1)
        if ':' in host_port_part:
            host, port = host_port_part.split(':', 1)
        else:
            host = host_port_part
            port = '3306'
            
        dbname = db_part.split('?')[0]

        # 构造 mysqldump 命令
        dump_cmd = [
            'mysqldump',
            '-h', host,
            '-P', port,
            '-u', user,
            f'-p{password}',
            dbname
        ]

        # 执行导出
        try:
            process = subprocess.Popen(dump_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
        except FileNotFoundError:
            return jsonify({"msg": "Backup failed: 'mysqldump' command not found. Please ensure MySQL client tools are installed."}), 500

        if process.returncode != 0:
            error_msg = stderr.decode('utf-8', errors='ignore')
            return jsonify({"msg": f"Backup failed: {error_msg}"}), 500

        # 返回 sql 文件流
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{dbname}_backup_{timestamp}.sql"
        
        response = make_response(stdout)
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        response.headers["Content-type"] = "application/sql"
        
        return response

    except Exception as e:
        return jsonify({"msg": f"An error occurred during backup: {str(e)}"}), 500

@bp.route('/admin/patients/template', methods=['GET'])
@role_required('admin')
def get_patients_template():
    csv_content = "学号,姓名,性别,手机号码,年级,学院,专业,班级,年龄,辅导员姓名\n"
    csv_content += "2024001,张三,男,,2024级,计算机学院,软件工程,软件一班,19,王老师\n"
    csv_content += "2024002,李四,女,13912345678,2024级,外国语学院,英语,英语二班,20,赵老师\n"
    response = make_response(csv_content.encode('utf-8-sig'))
    response.headers["Content-Disposition"] = "attachment; filename=patients_template.csv"
    response.headers["Content-type"] = "text/csv"
    return response

@bp.route('/admin/patients/import', methods=['POST'])
@role_required('admin')
def import_patients():
    if 'file' not in request.files:
        return jsonify({"msg": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"msg": "No selected file"}), 400
    if not file.filename.endswith('.csv'):
        return jsonify({"msg": "Only CSV files are allowed"}), 400

    try:
        file_content = file.stream.read()
        try:
            decoded_content = file_content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                decoded_content = file_content.decode("gbk")
            except UnicodeDecodeError:
                decoded_content = file_content.decode("utf-8")

        stream = io.StringIO(decoded_content, newline=None)
        csv_input = csv.DictReader(stream)

        success_count = 0
        error_count = 0

        for row in csv_input:
            def pick(*keys):
                for k in keys:
                    if k in row:
                        return row.get(k)
                return None

            student_id = (pick('student_id', '学号') or '').strip()
            name = (pick('name', '姓名') or '').strip()
            gender = (pick('gender', '性别') or '').strip()
            phone_raw = (pick('phone', '手机号码', '手机号', '电话') or '').strip()
            grade = (pick('grade', '年级') or '').strip()
            college = (pick('college', '学院') or '').strip()
            major = (pick('major', '专业') or '').strip()
            class_name = (pick('class_name', '班级') or '').strip()
            age_raw = (pick('age', '年龄') or '').strip()
            counselor_name = (pick('counselor_name', '辅导员姓名', '辅导员') or '').strip()
            phone = phone_raw or None

            # Security Best Practice: Sanitize inputs to prevent CSV injection (if exported later)
            # Remove leading formula characters: = + - @
            def sanitize(val):
                if val and val[0] in ('=', '+', '-', '@'):
                    return "'" + val
                return val

            student_id = sanitize(student_id)
            name = sanitize(name)
            counselor_name = sanitize(counselor_name)

            missing = []
            if not student_id:
                missing.append("student_id")
            if not name:
                missing.append("name")
            if not class_name:
                missing.append("class_name")
            if not counselor_name:
                missing.append("counselor_name")

            if missing:
                error_count += 1
                continue

            full_py, initials_py = _name_pinyin_parts(name)

            # Insert or update based on student_id if provided
            existing = Patient.query.filter_by(student_id=student_id).first()
            if existing:
                existing.name = name
                existing.name_pinyin = full_py
                existing.name_initials = initials_py
                if gender:
                    existing.gender = gender
                if grade:
                    existing.grade = grade
                if college:
                    existing.college = college
                if major:
                    existing.major = major
                existing.class_name = class_name
                existing.counselor_name = counselor_name
                if age_raw:
                    try:
                        existing.age = int(age_raw)
                    except ValueError:
                        error_count += 1
                        continue
                if phone is not None:
                    existing.phone = phone
            else:
                age_val = None
                if age_raw:
                    try:
                        age_val = int(age_raw)
                    except ValueError:
                        error_count += 1
                        continue
                new_patient = Patient(
                    student_id=student_id,
                    name=name,
                    name_pinyin=full_py,
                    name_initials=initials_py,
                    gender=gender or None,
                    grade=grade or None,
                    college=college or None,
                    major=major or None,
                    class_name=class_name,
                    phone=phone,
                    age=age_val,
                    counselor_name=counselor_name
                )
                db.session.add(new_patient)

            success_count += 1

            if success_count % 100 == 0:
                db.session.commit()

        db.session.commit()
        return jsonify({"msg": f"Import complete. Success: {success_count}, Errors: {error_count}"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"Error parsing CSV: {str(e)}"}), 500

@bp.route('/admin/drugs', methods=['GET'])
@role_required(['admin', 'nurse'])
def get_drugs():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('size', 20, type=int)
    keyword = request.args.get('keyword', '')

    query = Drug.query.order_by(Drug.id.desc())
    if keyword:
        query = query.filter(Drug.name.contains(keyword))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    data = []
    for drug in pagination.items:
        data.append({
            "id": drug.id,
            "name": drug.name,
            "base_name": drug.base_name,
            "type": drug.type,
            "specification": drug.specification,
            "unit": drug.unit,
            "purchase_price": drug.purchase_price,
            "price": drug.price,
            "has_scattered": drug.has_scattered,
            "scattered_price": drug.scattered_price,
            "conversion_rate": drug.conversion_rate,
            "stock": drug.stock,
            "status": drug.status,
            "batch_no": drug.batch_no,
            "inbound_at": drug.inbound_at.strftime('%Y-%m-%d %H:%M') if drug.inbound_at else None,
            "variant_type": drug.variant_type,
            "stock_group_code": drug.stock_group_code,
            "unit_amount": drug.unit_amount
        })

    return jsonify({
        "data": data,
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total
        }
    }), 200

@bp.route('/admin/drugs', methods=['POST'])
@role_required(['admin', 'nurse'])
def create_drug():
    data = request.get_json() or {}

    drug_type = data.get('type', 1)

    if drug_type == 1:
        required_fields = ['name', 'specification', 'unit', 'price', 'stock']
    else:
        required_fields = ['name', 'specification', 'unit', 'price']
        data['stock'] = -1

    for field in required_fields:
        if field not in data:
            return jsonify({"msg": f"Missing required field: {field}"}), 400

    drug = Drug(
        name=data['name'],
        type=drug_type,
        specification=data['specification'],
        unit=data['unit'],
        purchase_price=float(data.get('purchase_price', 0.0)),
        price=float(data['price']),
        has_scattered=data.get('has_scattered', False),
        scattered_price=float(data.get('scattered_price', 0.0)) if data.get('scattered_price') else None,
        conversion_rate=int(data.get('conversion_rate', 1)) if data.get('conversion_rate') else None,
        stock=int(data['stock']),
        status=data.get('status', 1),
        batch_no=data.get('batch_no'),
        inbound_at=datetime.fromisoformat(data['inbound_at']) if data.get('inbound_at') else None
    )
    db.session.add(drug)
    db.session.commit()

    return jsonify({"data": {"id": drug.id}}), 201

@bp.route('/admin/drugs/<int:id>', methods=['PUT'])
@role_required(['admin', 'nurse'])
def update_drug(id):
    drug = Drug.query.get_or_404(id)
    data = request.get_json() or {}

    if drug.stock_group_code:
        if 'stock' in data:
            return jsonify({"msg": "Grouped stock item cannot be updated via stock field"}), 400
        if 'specification' in data or 'unit' in data:
            return jsonify({"msg": "Grouped stock item cannot change specification/unit"}), 400

    if 'name' in data: drug.name = data['name']
    if 'type' in data: drug.type = data['type']
    if 'specification' in data: drug.specification = data['specification']
    if 'unit' in data: drug.unit = data['unit']
    if 'purchase_price' in data: drug.purchase_price = float(data['purchase_price'])
    if 'price' in data: drug.price = float(data['price'])
    if 'has_scattered' in data: drug.has_scattered = data['has_scattered']
    if 'scattered_price' in data: drug.scattered_price = float(data['scattered_price']) if data['scattered_price'] else None
    if 'conversion_rate' in data: drug.conversion_rate = int(data['conversion_rate']) if data['conversion_rate'] else None
    if 'stock' in data: drug.stock = int(data['stock'])
    if 'status' in data: drug.status = int(data['status'])
    if 'batch_no' in data: drug.batch_no = data['batch_no'] or None
    if 'inbound_at' in data: drug.inbound_at = datetime.fromisoformat(data['inbound_at']) if data['inbound_at'] else None

    db.session.commit()
    return jsonify({"msg": "Drug updated successfully"}), 200

@bp.route('/admin/drugs/<int:id>', methods=['DELETE'])
@role_required(['admin', 'nurse'])
def delete_drug(id):
    drug = Drug.query.get_or_404(id)
    if drug.stock_group_code:
        return jsonify({"msg": "整散库存组药品不支持直接删除，请先停用或由管理员做库存组清理"}), 400
    try:
        db.session.delete(drug)
        db.session.commit()
        return jsonify({"msg": "删除成功"}), 200
    except IntegrityError:
        db.session.rollback()
        return jsonify({"msg": "已被处方引用的项目无法彻底删除，请使用停用功能"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"删除失败: {str(e)}"}), 500

@bp.route('/admin/drugs/import', methods=['POST'])
@role_required(['admin', 'nurse'])
def import_drugs():
    if 'file' not in request.files:
        return jsonify({"msg": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"msg": "No selected file"}), 400
    if not file.filename.endswith('.csv'):
        return jsonify({"msg": "Only CSV files are allowed"}), 400

    try:
        file_content = file.stream.read()
        try:
            decoded_content = file_content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                decoded_content = file_content.decode("gbk")
            except UnicodeDecodeError:
                decoded_content = file_content.decode("utf-8")

        stream = io.StringIO(decoded_content, newline=None)
        csv_input = csv.DictReader(stream)

        success_count = 0
        error_count = 0

        for row in csv_input:
            try:
                name = row.get('name')
                specification = row.get('specification')
                unit = row.get('unit')
                purchase_price = float(row.get('purchase_price') or 0.0)
                price = float(row.get('price') or 0.0)
                has_scattered = str(row.get('has_scattered', '')).strip() == '1'
                scattered_price = float(row.get('scattered_price')) if row.get('scattered_price') else None
                conversion_rate = int(row.get('conversion_rate')) if row.get('conversion_rate') else None
                batch_no = (row.get('batch_no') or '').strip() or None
                inbound_at = (row.get('inbound_at') or '').strip() or None
                
                stock_str = str(row.get('stock', '')).strip()
                stock = int(stock_str) if stock_str else 0

                if not name or not specification:
                    error_count += 1
                    continue

                existing = Drug.query.filter_by(name=name, specification=specification).first()
                if existing:
                    existing.stock += stock
                    existing.purchase_price = purchase_price
                    existing.price = price
                    existing.has_scattered = has_scattered
                    existing.scattered_price = scattered_price
                    existing.conversion_rate = conversion_rate
                    if batch_no is not None:
                        existing.batch_no = batch_no
                    if inbound_at:
                        existing.inbound_at = datetime.fromisoformat(inbound_at)
                    existing.status = 1
                else:
                    new_drug = Drug(
                        name=name,
                        specification=specification,
                        unit=unit,
                        purchase_price=purchase_price,
                        price=price,
                        has_scattered=has_scattered,
                        scattered_price=scattered_price,
                        conversion_rate=conversion_rate,
                        stock=stock,
                        status=1,
                        batch_no=batch_no,
                        inbound_at=datetime.fromisoformat(inbound_at) if inbound_at else None
                    )
                    db.session.add(new_drug)

                success_count += 1
            except ValueError:
                error_count += 1

        db.session.commit()
        return jsonify({
            "msg": f"Import completed. Success: {success_count}, Failed: {error_count}",
            "data": {"success": success_count, "failed": error_count}
        }), 200

    except Exception as e:
        return jsonify({"msg": f"Import failed: {str(e)}"}), 500

@bp.route('/admin/drugs/import_xls', methods=['POST'])
@role_required(['admin', 'nurse'])
def import_drugs_xls():
    if 'file' not in request.files:
        return jsonify({"msg": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"msg": "No selected file"}), 400

    try:
        import pandas as pd
        import numpy as np

        df = pd.read_excel(file, sheet_name=0)
        df.columns = [str(col).strip() for col in df.columns]

        success_count = 0
        error_count = 0

        for seq, group in df.groupby('序号'):
            try:
                base_name = str(group.iloc[0].get('药  名', '')).strip()
                if not base_name or base_name == 'nan':
                    continue

                spec = str(group.iloc[0].get('规格', '')).strip()
                unit = str(group.iloc[0].get('单位', '')).strip()
                
                # Whole info
                whole_row = group[group['散装价'].isna() | (group['散装价'] == '')]
                if whole_row.empty:
                    whole_row = group.iloc[[0]]
                else:
                    whole_row = whole_row.iloc[[0]]

                purchase_price = float(whole_row['购进价'].values[0]) if pd.notnull(whole_row['购进价'].values[0]) else 0.0
                price = float(whole_row['盒装价'].values[0]) if pd.notnull(whole_row['盒装价'].values[0]) else 0.0
                
                # Scattered info
                scattered_row = group[group['散装价'].notna() & (group['散装价'] != '')]
                has_scattered = not scattered_row.empty

                scattered_price = None
                conversion_rate = None

                if has_scattered:
                    scattered_price = float(scattered_row['盒装价'].values[0])
                    scattered_total = float(scattered_row['散装价'].values[0])
                    if scattered_price > 0:
                        conversion_rate = int(round(scattered_total / scattered_price))
                    else:
                        conversion_rate = 1

                stock = 0
                if '库存' in group.columns:
                    val = group.iloc[0].get('库存')
                    stock = int(val) if pd.notnull(val) else 0

                batch_no = None
                if '批号' in group.columns:
                    val = group.iloc[0].get('批号')
                    batch_no = str(val).strip() if pd.notnull(val) and str(val).strip() else None

                inbound_at = None
                if '入库时间' in group.columns:
                    val = group.iloc[0].get('入库时间')
                    inbound_at = val if pd.notnull(val) else None

                new_drug = Drug(
                    name=base_name,
                    specification=spec,
                    unit=unit,
                    price=price,
                    purchase_price=purchase_price,
                    has_scattered=has_scattered,
                    scattered_price=scattered_price,
                    conversion_rate=conversion_rate,
                    stock=stock,
                    status=1,
                    batch_no=batch_no,
                    inbound_at=inbound_at
                )
                db.session.add(new_drug)
                success_count += 1
            except Exception as e:
                error_count += 1

        db.session.commit()
        return jsonify({
            "msg": f"Import completed. Success: {success_count}, Failed: {error_count}",
            "data": {"success": success_count, "failed": error_count}
        }), 200
    except Exception as e:
        return jsonify({"msg": f"Import failed: {str(e)}"}), 500

@bp.route('/admin/drugs/template', methods=['GET'])
@role_required(['admin', 'nurse'])
def get_drug_template():
    si = io.BytesIO()
    si.write(b'\xef\xbb\xbf')

    str_io = io.StringIO()
    cw = csv.writer(str_io)
    cw.writerow(['name', 'specification', 'unit', 'purchase_price', 'price', 'has_scattered', 'scattered_price', 'conversion_rate', 'stock', 'batch_no', 'inbound_at'])
    cw.writerow(['示例药品', '10mg*10片', '盒', '8.5', '10.5', '1', '1.2', '10', '100', 'BATCH-001', '2026-03-01 10:30'])
    cw.writerow(['无库存无零卖示例', '100ml', '瓶', '12', '15', '0', '', '', '0', '', ''])

    si.write(str_io.getvalue().encode('utf-8'))

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=drug_import_template.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output

@bp.route('/admin/drugs/smart-inventory', methods=['POST'])
@role_required(['admin', 'nurse'])
def smart_inventory():
    total_merged = 0
    total_deleted = 0

    try:
        duplicates_query = db.session.query(
            Drug.name,
            Drug.specification,
            func.count(Drug.id).label('count')
        ).group_by(
            Drug.name,
            Drug.specification
        ).having(
            func.count(Drug.id) > 1
        ).all()

        for dup in duplicates_query:
            name = dup.name
            spec = dup.specification

            drugs = Drug.query.filter_by(name=name, specification=spec).order_by(Drug.id.asc()).all()
            if len(drugs) <= 1:
                continue

            primary_drug = drugs[0]
            duplicate_drugs = drugs[1:]

            for dup_drug in duplicate_drugs:
                if primary_drug.type == 1 and dup_drug.stock > 0:
                    primary_drug.stock += dup_drug.stock

                items_to_update = PrescriptionItem.query.filter_by(drug_id=dup_drug.id).all()
                for item in items_to_update:
                    item.drug_id = primary_drug.id

                db.session.delete(dup_drug)
                total_deleted += 1

            total_merged += 1

        db.session.commit()

        low_stock_drugs = Drug.query.filter(
            Drug.type == 1,
            Drug.status == 1,
            Drug.stock < 10
        ).order_by(Drug.stock.asc()).all()

        warnings = []
        for d in low_stock_drugs:
            warnings.append({
                "id": d.id,
                "name": d.name,
                "specification": d.specification,
                "stock": d.stock
            })

        return jsonify({
            "msg": "盘库完成",
            "data": {
                "merged_groups": total_merged,
                "deleted_duplicates": total_deleted,
                "warnings": warnings
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"智能盘库失败: {str(e)}"}), 500

@bp.route('/admin/statistics/revenue', methods=['GET'])
@role_required(['admin', 'nurse'])
def get_revenue_stats():
    def parse_dt(value, is_end=False):
        if not value:
            return None
        s = str(value).strip()
        if not s:
            return None
        fmts = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]
        for fmt in fmts:
            try:
                dt = datetime.strptime(s, fmt)
                if fmt == "%Y-%m-%d":
                    if is_end:
                        return dt + timedelta(days=1)
                    return dt
                if is_end:
                    return dt + timedelta(seconds=1)
                return dt
            except Exception:
                continue
        raise ValueError("Invalid date format")

    stats_type = request.args.get("type", "daily")
    target_date_str = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    start_time_str = request.args.get("start_time") or request.args.get("start_date")
    end_time_str = request.args.get("end_time") or request.args.get("end_date")

    doctor_id = request.args.get("doctor_id", type=int)
    nurse_id = request.args.get("nurse_id", type=int)

    try:
        if start_time_str or end_time_str:
            start = parse_dt(start_time_str, is_end=False) if start_time_str else None
            end = parse_dt(end_time_str, is_end=True) if end_time_str else None
            if start is None and end is None:
                raise ValueError("Invalid date format")
            if start is None:
                start = end - timedelta(days=1)
            if end is None:
                end = start + timedelta(days=1)
        else:
            if stats_type == "daily":
                target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
                start = datetime.combine(target_date, datetime.min.time())
                end = start + timedelta(days=1)
            elif stats_type == "monthly":
                target_year, target_month = map(int, target_date_str.split("-")[:2])
                start = datetime(target_year, target_month, 1)
                if target_month == 12:
                    end = datetime(target_year + 1, 1, 1)
                else:
                    end = datetime(target_year, target_month + 1, 1)
            else:
                target_year = int(target_date_str.split("-")[0])
                start = datetime(target_year, 1, 1)
                end = datetime(target_year + 1, 1, 1)

        query = Payment.query.join(Visit).filter(
            Payment.payment_date >= start,
            Payment.payment_date < end
        )
        if doctor_id:
            query = query.filter(Visit.doctor_id == doctor_id)
        if nurse_id:
            query = query.filter(Payment.nurse_id == nurse_id)

        payments = query.options(
            db.joinedload(Payment.visit).joinedload(Visit.patient),
            db.joinedload(Payment.visit).joinedload(Visit.doctor),
            db.joinedload(Payment.nurse),
        ).all()

        visit_ids = [p.visit_id for p in payments if p.visit_id]
        items_by_visit = {}
        if visit_ids:
            items = PrescriptionItem.query.options(
                db.joinedload(PrescriptionItem.drug)
            ).filter(
                PrescriptionItem.visit_id.in_(visit_ids)
            ).all()
            for it in items:
                items_by_visit.setdefault(it.visit_id, []).append(it)

        total_revenue = 0.0
        drug_revenue = 0.0
        service_revenue = 0.0
        consultation_revenue = 0.0
        total_cost = 0.0
        total_profit = 0.0

        details = []
        for p in payments:
            v = p.visit
            if v is None:
                continue

            consult = float(v.consultation_fee or 0.0)
            drug_amt = 0.0
            service_amt = 0.0
            cost = 0.0
            for it in items_by_visit.get(v.id, []):
                amount_val = it.new_amount if it.new_amount is not None else it.amount
                amount_val = float(amount_val or 0.0)
                d = getattr(it, "drug", None)
                if d is not None and int(getattr(d, "type", 1) or 1) == 1:
                    drug_amt += amount_val
                else:
                    service_amt += amount_val
                cost += float(it.purchase_cost or 0.0)

            amount = float(p.amount or 0.0)
            profit = amount - cost

            total_revenue += amount
            drug_revenue += drug_amt
            service_revenue += service_amt
            consultation_revenue += consult
            total_cost += cost
            total_profit += profit

            details.append({
                "date": p.payment_date.strftime("%Y-%m-%d %H:%M:%S") if p.payment_date else "",
                "visit_id": p.visit_id,
                "patient_name": v.patient.name if v.patient else "",
                "student_id": v.patient.student_id if v.patient else "",
                "doctor_name": v.doctor.real_name if getattr(v, "doctor", None) else "",
                "nurse_name": p.nurse.real_name if getattr(p, "nurse", None) else "",
                "diagnosis": v.diagnosis or "",
                "chief_complaint": v.chief_complaint or "",
                "drug_amount": drug_amt,
                "service_amount": service_amt,
                "consultation_fee": consult,
                "amount": amount,
                "cost": cost,
                "profit": profit,
            })

        return jsonify({
            "data": {
                "total_revenue": total_revenue,
                "drug_revenue": drug_revenue,
                "service_revenue": service_revenue,
                "consultation_revenue": consultation_revenue,
                "total_cost": total_cost,
                "total_profit": total_profit,
                "details": details,
                "range": {
                    "start": start.strftime("%Y-%m-%d %H:%M:%S"),
                    "end": (end - timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S"),
                }
            }
        }), 200

    except ValueError:
        return jsonify({"msg": "Invalid date format"}), 400


@bp.route('/admin/statistics/revenue/users', methods=['GET'])
@role_required(['admin', 'nurse'])
def get_revenue_stats_users():
    users = User.query.filter(User.role.in_(["doctor", "nurse"])).order_by(User.role.asc(), User.real_name.asc()).all()
    doctors = []
    nurses = []
    for u in users:
        item = {"id": u.id, "real_name": u.real_name}
        if u.role == "doctor":
            doctors.append(item)
        elif u.role == "nurse":
            nurses.append(item)
    return jsonify({"data": {"doctors": doctors, "nurses": nurses}}), 200


@bp.route("/admin/statistics/revenue/export", methods=["GET"])
@role_required(["admin", "nurse"])
def export_revenue_stats():
    from openpyxl import Workbook

    stats_type = request.args.get("type", "daily")
    target_date_str = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    start_time_str = request.args.get("start_time") or request.args.get("start_date")
    end_time_str = request.args.get("end_time") or request.args.get("end_date")

    doctor_id = request.args.get("doctor_id", type=int)
    nurse_id = request.args.get("nurse_id", type=int)

    try:
        def parse_dt(value, is_end=False):
            if not value:
                return None
            s = str(value).strip()
            if not s:
                return None
            fmts = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]
            for fmt in fmts:
                try:
                    dt = datetime.strptime(s, fmt)
                    if fmt == "%Y-%m-%d":
                        if is_end:
                            return dt + timedelta(days=1)
                        return dt
                    if is_end:
                        return dt + timedelta(seconds=1)
                    return dt
                except Exception:
                    continue
            raise ValueError("Invalid date format")

        if start_time_str or end_time_str:
            start = parse_dt(start_time_str, is_end=False) if start_time_str else None
            end = parse_dt(end_time_str, is_end=True) if end_time_str else None
            if start is None and end is None:
                raise ValueError("Invalid date format")
            if start is None:
                start = end - timedelta(days=1)
            if end is None:
                end = start + timedelta(days=1)
            date_label = f"{start.strftime('%Y%m%d_%H%M')}-{(end - timedelta(seconds=1)).strftime('%Y%m%d_%H%M')}"
        else:
            if stats_type == "daily":
                target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
                start = datetime.combine(target_date, datetime.min.time())
                end = start + timedelta(days=1)
                date_label = target_date_str
            elif stats_type == "monthly":
                target_year, target_month = map(int, target_date_str.split("-")[:2])
                start = datetime(target_year, target_month, 1)
                if target_month == 12:
                    end = datetime(target_year + 1, 1, 1)
                else:
                    end = datetime(target_year, target_month + 1, 1)
                date_label = f"{target_year:04d}-{target_month:02d}"
            elif stats_type == "yearly":
                target_year = int(target_date_str.split("-")[0])
                start = datetime(target_year, 1, 1)
                end = datetime(target_year + 1, 1, 1)
                date_label = f"{target_year:04d}"
            else:
                return jsonify({"msg": "Invalid type"}), 400
    except Exception:
        return jsonify({"msg": "Invalid date format"}), 400

    def safe_text(val):
        s = "" if val is None else str(val)
        if s.startswith(("=", "+", "-", "@")):
            return "'" + s
        return s

    query = Payment.query.join(Visit).filter(Payment.payment_date >= start, Payment.payment_date < end)
    if doctor_id:
        query = query.filter(Visit.doctor_id == doctor_id)
    if nurse_id:
        query = query.filter(Payment.nurse_id == nurse_id)
    payments = query.options(
        db.joinedload(Payment.visit).joinedload(Visit.patient),
        db.joinedload(Payment.visit).joinedload(Visit.doctor),
        db.joinedload(Payment.nurse),
    ).all()

    visit_ids = [p.visit_id for p in payments if p.visit_id]
    items_by_visit = {}
    if visit_ids:
        items = PrescriptionItem.query.options(
            db.joinedload(PrescriptionItem.drug)
        ).filter(
            PrescriptionItem.visit_id.in_(visit_ids)
        ).all()
        for it in items:
            items_by_visit.setdefault(it.visit_id, []).append(it)

    wb = Workbook()
    ws = wb.active
    ws.title = "revenue"

    ws.append(
        [
            "支付时间",
            "visit_id",
            "患者姓名",
            "学号",
            "医生",
            "护士",
            "支付方式",
            "诊察费",
            "药品金额",
            "诊疗项目金额",
            "总金额",
            "成本",
            "利润",
            "诊断",
            "主诉",
        ]
    )

    total_revenue = 0.0
    consultation_revenue = 0.0
    drug_revenue = 0.0
    service_revenue = 0.0
    total_cost = 0.0
    total_profit = 0.0

    for p in payments:
        v = p.visit
        if v is None:
            continue
        consult = float(v.consultation_fee or 0.0)
        amount = float(p.amount or 0.0)
        cost = 0.0
        drug_amt = 0.0
        service_amt = 0.0
        for it in items_by_visit.get(v.id, []):
            amount_val = it.new_amount if it.new_amount is not None else it.amount
            amount_val = float(amount_val or 0.0)
            d = getattr(it, "drug", None)
            if d is not None and int(getattr(d, "type", 1) or 1) == 1:
                drug_amt += amount_val
            else:
                service_amt += amount_val
            cost += float(it.purchase_cost or 0.0)
        profit = amount - cost

        total_revenue += amount
        consultation_revenue += consult
        drug_revenue += drug_amt
        service_revenue += service_amt
        total_cost += cost
        total_profit += profit

        ws.append(
            [
                safe_text(p.payment_date.strftime("%Y-%m-%d %H:%M:%S") if p.payment_date else ""),
                v.id,
                safe_text(v.patient.name if v.patient else ""),
                safe_text(v.patient.student_id if v.patient else ""),
                safe_text(v.doctor.real_name if v.doctor else ""),
                safe_text(p.nurse.real_name if getattr(p, "nurse", None) else ""),
                safe_text(p.payment_method or ""),
                round(consult, 2),
                round(drug_amt, 2),
                round(service_amt, 2),
                round(amount, 2),
                round(cost, 2),
                round(profit, 2),
                safe_text(v.diagnosis or ""),
                safe_text(v.chief_complaint or ""),
            ]
        )

    ws2 = wb.create_sheet("summary")
    ws2.append(["维度", safe_text(stats_type)])
    ws2.append(["日期", safe_text(date_label)])
    ws2.append(["开始时间", safe_text(start.strftime("%Y-%m-%d %H:%M:%S"))])
    ws2.append(["结束时间", safe_text((end - timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S"))])
    ws2.append(["doctor_id", safe_text(doctor_id if doctor_id else "")])
    ws2.append(["nurse_id", safe_text(nurse_id if nurse_id else "")])
    ws2.append(["总收入", round(total_revenue, 2)])
    ws2.append(["药品收入", round(drug_revenue, 2)])
    ws2.append(["诊疗项目收入", round(service_revenue, 2)])
    ws2.append(["诊察费收入", round(consultation_revenue, 2)])
    ws2.append(["总成本", round(total_cost, 2)])
    ws2.append(["总利润", round(total_profit, 2)])

    stream = io.BytesIO()
    wb.save(stream)
    payload = stream.getvalue()

    filename = f"revenue_{stats_type}_{date_label}.xlsx"
    resp = make_response(payload)
    resp.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp


@bp.route("/admin/statistics/drug-outbound", methods=["GET"])
@role_required(["admin", "nurse"])
def get_drug_outbound_records():
    def parse_dt(value, is_end=False):
        if not value:
            return None
        s = str(value).strip()
        if not s:
            return None
        fmts = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]
        for fmt in fmts:
            try:
                dt = datetime.strptime(s, fmt)
                if fmt == "%Y-%m-%d":
                    if is_end:
                        return dt + timedelta(days=1)
                    return dt
                if is_end:
                    return dt + timedelta(seconds=1)
                return dt
            except Exception:
                continue
        raise ValueError("Invalid date format")

    start_time_str = request.args.get("start_time") or request.args.get("start_date")
    end_time_str = request.args.get("end_time") or request.args.get("end_date")
    if not start_time_str and not end_time_str:
        today = datetime.now().strftime("%Y-%m-%d")
        start_time_str = f"{today} 00:00:00"
        end_time_str = f"{today} 23:59:59"

    doctor_id = request.args.get("doctor_id", type=int)
    nurse_id = request.args.get("nurse_id", type=int)
    keyword = (request.args.get("keyword") or "").strip()
    page = request.args.get("page", 1, type=int)
    size = request.args.get("size", 50, type=int)
    if page <= 0:
        page = 1
    if size <= 0:
        size = 50
    if size > 200:
        size = 200

    try:
        start = parse_dt(start_time_str, is_end=False) if start_time_str else None
        end = parse_dt(end_time_str, is_end=True) if end_time_str else None
        if start is None and end is None:
            raise ValueError("Invalid date format")
        if start is None:
            start = end - timedelta(days=1)
        if end is None:
            end = start + timedelta(days=1)
    except Exception:
        return jsonify({"msg": "Invalid date format"}), 400

    Doctor = aliased(User)
    Nurse = aliased(User)

    amount_expr = func.coalesce(PrescriptionItem.new_amount, PrescriptionItem.amount)
    q = (
        db.session.query(
            Payment.payment_date,
            Payment.payment_method,
            Visit.id.label("visit_id"),
            Patient.name.label("patient_name"),
            Patient.student_id.label("student_id"),
            Doctor.real_name.label("doctor_name"),
            Nurse.real_name.label("nurse_name"),
            Drug.id.label("drug_id"),
            Drug.name.label("drug_name"),
            Drug.specification.label("specification"),
            Drug.unit.label("unit"),
            PrescriptionItem.is_scattered.label("is_scattered"),
            PrescriptionItem.quantity.label("quantity"),
            PrescriptionItem.price_at_visit.label("price_at_visit"),
            amount_expr.label("amount"),
        )
        .join(Visit, Payment.visit_id == Visit.id)
        .join(Patient, Visit.patient_id == Patient.id)
        .join(Doctor, Visit.doctor_id == Doctor.id)
        .join(Nurse, Payment.nurse_id == Nurse.id)
        .join(PrescriptionItem, PrescriptionItem.visit_id == Visit.id)
        .join(Drug, PrescriptionItem.drug_id == Drug.id)
        .filter(Payment.payment_date >= start, Payment.payment_date < end)
        .filter(Drug.type == 1)
    )

    if doctor_id:
        q = q.filter(Visit.doctor_id == doctor_id)
    if nurse_id:
        q = q.filter(Payment.nurse_id == nurse_id)
    if keyword:
        q = q.filter(func.lower(Drug.name).contains(keyword.lower()) | func.lower(Drug.specification).contains(keyword.lower()))

    total_records = q.count()
    agg = q.with_entities(
        func.coalesce(func.sum(amount_expr), 0.0),
        func.coalesce(func.sum(PrescriptionItem.quantity), 0),
    ).first()
    total_amount = float(agg[0] or 0.0) if agg else 0.0
    total_quantity = int(agg[1] or 0) if agg else 0

    rows = (
        q.order_by(Payment.payment_date.desc(), Visit.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    details = []
    for r in rows:
        details.append({
            "date": r.payment_date.strftime("%Y-%m-%d %H:%M:%S") if r.payment_date else "",
            "visit_id": r.visit_id,
            "patient_name": r.patient_name,
            "student_id": r.student_id,
            "doctor_name": r.doctor_name,
            "nurse_name": r.nurse_name,
            "payment_method": r.payment_method,
            "drug_id": r.drug_id,
            "drug_name": r.drug_name,
            "specification": r.specification,
            "unit": r.unit,
            "is_scattered": bool(r.is_scattered),
            "quantity": int(r.quantity or 0),
            "price_at_visit": float(r.price_at_visit or 0.0),
            "amount": float(r.amount or 0.0),
        })

    pages = int((total_records + size - 1) / size) if size else 1

    return jsonify({
        "data": {
            "summary": {
                "total_records": total_records,
                "total_quantity": total_quantity,
                "total_amount": total_amount,
            },
            "details": details,
            "meta": {
                "page": page,
                "per_page": size,
                "total": total_records,
                "pages": pages,
            },
            "range": {
                "start": start.strftime("%Y-%m-%d %H:%M:%S"),
                "end": (end - timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S"),
            }
        }
    }), 200


@bp.route("/admin/statistics/drug-outbound/export", methods=["GET"])
@role_required(["admin", "nurse"])
def export_drug_outbound_records():
    from openpyxl import Workbook

    def parse_dt(value, is_end=False):
        if not value:
            return None
        s = str(value).strip()
        if not s:
            return None
        fmts = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]
        for fmt in fmts:
            try:
                dt = datetime.strptime(s, fmt)
                if fmt == "%Y-%m-%d":
                    if is_end:
                        return dt + timedelta(days=1)
                    return dt
                if is_end:
                    return dt + timedelta(seconds=1)
                return dt
            except Exception:
                continue
        raise ValueError("Invalid date format")

    def safe_text(val):
        s = "" if val is None else str(val)
        if s.startswith(("=", "+", "-", "@")):
            return "'" + s
        return s

    start_time_str = request.args.get("start_time") or request.args.get("start_date")
    end_time_str = request.args.get("end_time") or request.args.get("end_date")
    if not start_time_str and not end_time_str:
        today = datetime.now().strftime("%Y-%m-%d")
        start_time_str = f"{today} 00:00:00"
        end_time_str = f"{today} 23:59:59"

    doctor_id = request.args.get("doctor_id", type=int)
    nurse_id = request.args.get("nurse_id", type=int)
    keyword = (request.args.get("keyword") or "").strip()

    try:
        start = parse_dt(start_time_str, is_end=False) if start_time_str else None
        end = parse_dt(end_time_str, is_end=True) if end_time_str else None
        if start is None and end is None:
            raise ValueError("Invalid date format")
        if start is None:
            start = end - timedelta(days=1)
        if end is None:
            end = start + timedelta(days=1)
    except Exception:
        return jsonify({"msg": "Invalid date format"}), 400

    Doctor = aliased(User)
    Nurse = aliased(User)
    amount_expr = func.coalesce(PrescriptionItem.new_amount, PrescriptionItem.amount)
    q = (
        db.session.query(
            Payment.payment_date,
            Payment.payment_method,
            Visit.id.label("visit_id"),
            Patient.name.label("patient_name"),
            Patient.student_id.label("student_id"),
            Doctor.real_name.label("doctor_name"),
            Nurse.real_name.label("nurse_name"),
            Drug.name.label("drug_name"),
            Drug.specification.label("specification"),
            Drug.unit.label("unit"),
            PrescriptionItem.is_scattered.label("is_scattered"),
            PrescriptionItem.quantity.label("quantity"),
            PrescriptionItem.price_at_visit.label("price_at_visit"),
            amount_expr.label("amount"),
        )
        .join(Visit, Payment.visit_id == Visit.id)
        .join(Patient, Visit.patient_id == Patient.id)
        .join(Doctor, Visit.doctor_id == Doctor.id)
        .join(Nurse, Payment.nurse_id == Nurse.id)
        .join(PrescriptionItem, PrescriptionItem.visit_id == Visit.id)
        .join(Drug, PrescriptionItem.drug_id == Drug.id)
        .filter(Payment.payment_date >= start, Payment.payment_date < end)
        .filter(Drug.type == 1)
    )
    if doctor_id:
        q = q.filter(Visit.doctor_id == doctor_id)
    if nurse_id:
        q = q.filter(Payment.nurse_id == nurse_id)
    if keyword:
        q = q.filter(func.lower(Drug.name).contains(keyword.lower()) | func.lower(Drug.specification).contains(keyword.lower()))

    rows = q.order_by(Payment.payment_date.asc(), Visit.id.asc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "outbound"
    ws.append([
        "出库时间",
        "visit_id",
        "患者姓名",
        "学号",
        "接诊医生",
        "开药护士",
        "支付方式",
        "药品名称",
        "规格",
        "单位",
        "是否零散",
        "数量",
        "单价",
        "金额",
    ])

    total_amount = 0.0
    total_quantity = 0
    for r in rows:
        qty = int(r.quantity or 0)
        amt = float(r.amount or 0.0)
        total_quantity += qty
        total_amount += amt
        ws.append([
            safe_text(r.payment_date.strftime("%Y-%m-%d %H:%M:%S") if r.payment_date else ""),
            r.visit_id,
            safe_text(r.patient_name),
            safe_text(r.student_id),
            safe_text(r.doctor_name),
            safe_text(r.nurse_name),
            safe_text(r.payment_method),
            safe_text(r.drug_name),
            safe_text(r.specification),
            safe_text(r.unit),
            "是" if bool(r.is_scattered) else "否",
            qty,
            round(float(r.price_at_visit or 0.0), 4),
            round(amt, 2),
        ])

    ws2 = wb.create_sheet("summary")
    ws2.append(["开始时间", safe_text(start.strftime("%Y-%m-%d %H:%M:%S"))])
    ws2.append(["结束时间", safe_text((end - timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S"))])
    ws2.append(["doctor_id", safe_text(doctor_id if doctor_id else "")])
    ws2.append(["nurse_id", safe_text(nurse_id if nurse_id else "")])
    ws2.append(["keyword", safe_text(keyword)])
    ws2.append(["记录数", len(rows)])
    ws2.append(["合计数量", total_quantity])
    ws2.append(["合计金额", round(total_amount, 2)])

    stream = io.BytesIO()
    wb.save(stream)
    payload = stream.getvalue()

    filename = f"drug_outbound_{start.strftime('%Y%m%d_%H%M')}_{(end - timedelta(seconds=1)).strftime('%Y%m%d_%H%M')}.xlsx"
    resp = make_response(payload)
    resp.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp

@bp.route('/admin/users', methods=['GET'])
@role_required('admin')
def get_users():
    users = User.query.filter(User.role != 'admin').all()
    data = []
    for u in users:
        data.append({
            "id": u.id,
            "username": u.username,
            "real_name": u.real_name,
            "role": u.role
        })
    return jsonify({"data": data}), 200

@bp.route('/admin/users', methods=['POST'])
@role_required('admin')
def create_user():
    data = request.get_json() or {}
    required_fields = ['username', 'password', 'real_name', 'role']
    for field in required_fields:
        if not data.get(field):
            return jsonify({"msg": f"Missing required field: {field}"}), 400

    if User.query.filter_by(username=data['username']).first():
        return jsonify({"msg": "Username already exists"}), 400

    if data['role'] not in ['doctor', 'nurse']:
        return jsonify({"msg": "Invalid role"}), 400

    user = User(
        username=data['username'],
        real_name=data['real_name'],
        role=data['role']
    )
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()

    return jsonify({"data": {"id": user.id}}), 201

@bp.route('/admin/users/<int:id>', methods=['PUT'])
@role_required('admin')
def update_user(id):
    user = User.query.get_or_404(id)
    if user.role == 'admin':
        return jsonify({"msg": "Cannot modify admin user"}), 403

    data = request.get_json() or {}

    if 'username' in data and data['username'] != user.username:
        if User.query.filter_by(username=data['username']).first():
            return jsonify({"msg": "Username already exists"}), 400
        user.username = data['username']

    if 'real_name' in data:
        user.real_name = data['real_name']

    if 'role' in data and data['role'] in ['doctor', 'nurse']:
        user.role = data['role']

    if data.get('password'):
        user.set_password(data['password'])

    db.session.commit()
    return jsonify({"msg": "User updated successfully"}), 200

@bp.route('/admin/users/<int:id>', methods=['DELETE'])
@role_required('admin')
def delete_user(id):
    user = User.query.get_or_404(id)
    if user.role == 'admin':
        return jsonify({"msg": "Cannot delete admin user"}), 403

    db.session.delete(user)
    db.session.commit()
    return jsonify({"msg": "User deleted successfully"}), 200

@bp.route('/admin/backup', methods=['POST'])
@role_required('admin')
def backup_database():
    try:
        possible_paths = [
            os.path.join(os.getcwd(), 'app.db'),
            os.path.join(os.getcwd(), 'backend', 'app.db'),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'app.db')
        ]

        db_path = None
        for p in possible_paths:
            if os.path.exists(p):
                db_path = p
                break

        if not db_path:
            return jsonify({"msg": "Database file not found"}), 500

        backup_dir = os.path.join(os.path.dirname(db_path), 'backups')
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        backup_filename = f"backup_{timestamp}.db"
        backup_path = os.path.join(backup_dir, backup_filename)

        shutil.copy2(db_path, backup_path)

        return jsonify({
            "msg": "Backup successful",
            "filename": backup_filename
        }), 200
    except Exception as e:
        return jsonify({"msg": f"Backup failed: {str(e)}"}), 500
