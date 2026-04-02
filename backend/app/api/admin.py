from flask import request, jsonify, send_file, make_response
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.app import db
from backend.app.api import bp
from backend.app.models import User, Drug, Payment, Visit, PrescriptionItem
from backend.app.utils.decorators import role_required
from datetime import datetime, date, timedelta
from sqlalchemy import func
import os
import shutil
import csv
import io
from sqlalchemy.exc import IntegrityError

@bp.route('/admin/drugs', methods=['GET'])
@role_required('admin')
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
            "inbound_at": drug.inbound_at.strftime('%Y-%m-%d %H:%M') if drug.inbound_at else None
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
@role_required('admin')
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
@role_required('admin')
def update_drug(id):
    drug = Drug.query.get_or_404(id)
    data = request.get_json() or {}

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
@role_required('admin')
def delete_drug(id):
    drug = Drug.query.get_or_404(id)
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
@role_required('admin')
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
@role_required('admin')
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
@role_required('admin')
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
@role_required('admin')
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
@role_required('admin')
def get_revenue_stats():
    stats_type = request.args.get('type', 'daily')
    target_date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))

    try:
        if stats_type == 'daily':
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
            start = datetime.combine(target_date, datetime.min.time())
            end = start + timedelta(days=1)
        elif stats_type == 'monthly':
            target_year, target_month = map(int, target_date_str.split('-')[:2])
            start = datetime(target_year, target_month, 1)
            if target_month == 12:
                end = datetime(target_year + 1, 1, 1)
            else:
                end = datetime(target_year, target_month + 1, 1)
        else:
            target_year = int(target_date_str.split('-')[0])
            start = datetime(target_year, 1, 1)
            end = datetime(target_year + 1, 1, 1)

        query = Payment.query.filter(
            Payment.payment_date >= start,
            Payment.payment_date < end
        )

        payments = query.options(db.joinedload(Payment.visit)).all()
        total_revenue = sum(p.amount for p in payments)

        drug_revenue = 0.0
        consultation_revenue = 0.0
        total_profit = 0.0

        details = []
        for p in payments:
            visit = p.visit
            if visit:
                consultation_revenue += visit.consultation_fee
                drug_revenue += (visit.total_amount - visit.consultation_fee)
                
                # Calculate cost from items
                visit_cost = 0.0
                for item in visit.items:
                    visit_cost += (item.purchase_cost or 0.0)
                
                visit_profit = p.amount - visit_cost
                total_profit += visit_profit

                details.append({
                    "date": p.payment_date.strftime('%Y-%m-%d %H:%M'),
                    "amount": p.amount,
                    "profit": visit_profit,
                    "visit_id": p.visit_id
                })

        return jsonify({
            "data": {
                "total_revenue": total_revenue,
                "drug_revenue": drug_revenue,
                "consultation_revenue": consultation_revenue,
                "total_profit": total_profit,
                "details": details
            }
        }), 200

    except ValueError:
        return jsonify({"msg": "Invalid date format"}), 400

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
