from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.app import db
from backend.app.api import bp
from backend.app.models import User, Visit, PrescriptionItem, Payment, Drug, InventoryRecord
from backend.app.utils.decorators import role_required
from datetime import datetime
from sqlalchemy import or_

@bp.route('/nurse/pending-visits', methods=['GET'])
@role_required('nurse')
def get_pending_visits():
    # Preload patient information to avoid N+1 queries
    visits = Visit.query.filter_by(status='pending').options(
        db.joinedload(Visit.patient)
    ).order_by(Visit.timestamp.asc()).all()

    data = []
    for visit in visits:
        data.append({
            "visit_id": visit.id,
            "patient_name": visit.patient.name,
            "created_at": visit.timestamp.strftime('%Y-%m-%d %H:%M'),
            "total_amount": visit.total_amount
        })

    return jsonify({"data": data}), 200

@bp.route('/nurse/inventory', methods=['POST'])
@role_required('nurse')
def update_inventory():
    data = request.get_json() or {}
    drug_id = data.get('drug_id')
    new_stock = data.get('new_stock')
    remark = data.get('remark')

    if drug_id is None or new_stock is None or not remark:
        return jsonify({"msg": "Missing required fields"}), 400

    drug = Drug.query.get_or_404(drug_id)
    user_id = get_jwt_identity()

    try:
        record = InventoryRecord(
            drug_id=drug.id,
            nurse_id=int(user_id),
            old_stock=drug.stock,
            new_stock=int(new_stock),
            remark=remark
        )
        db.session.add(record)
        
        drug.stock = int(new_stock)
        
        db.session.commit()
        return jsonify({"msg": "Inventory updated successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"Failed to update inventory: {str(e)}"}), 500

@bp.route('/nurse/inventory/records', methods=['GET'])
@role_required('nurse')
def get_inventory_records():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('size', 20, type=int)

    query = InventoryRecord.query.order_by(InventoryRecord.timestamp.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    data = []
    for record in pagination.items:
        data.append({
            "id": record.id,
            "drug_name": record.drug.name if record.drug else "Unknown",
            "specification": record.drug.specification if record.drug else "-",
            "nurse_name": record.nurse.real_name if record.nurse else "Unknown",
            "old_stock": record.old_stock,
            "new_stock": record.new_stock,
            "remark": record.remark,
            "timestamp": record.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        })

    return jsonify({
        "data": data,
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total
        }
    }), 200

@bp.route('/nurse/visits/<int:visit_id>', methods=['GET'])
@role_required('nurse')
def get_visit_detail(visit_id):
    # Preload patient, items and drug information to avoid N+1 queries
    visit = Visit.query.options(
        db.joinedload(Visit.patient),
        db.joinedload(Visit.doctor),
        db.joinedload(Visit.items).joinedload(PrescriptionItem.drug)
    ).get_or_404(visit_id)

    items = []
    for item in visit.items:
        items.append({
            "drug_name": item.drug.name,
            "type": item.drug.type,
            "specification": item.drug.specification,
            "usage": item.usage,
            "dosage": item.dosage,
            "frequency": item.frequency,
            "timing": item.timing,
            "quantity": item.quantity,
            "unit_price": item.price_at_visit,
            "amount": item.amount,
            "is_scattered": item.is_scattered,
            "stock": item.drug.stock
        })

    return jsonify({
        "data": {
            "visit_id": visit.id,
            "patient": {
                "name": visit.patient.name
            },
            "doctor_name": visit.doctor.real_name if visit.doctor else "Unknown",
            "created_at": visit.timestamp.strftime('%Y-%m-%d %H:%M'),
            "diagnosis": visit.diagnosis,
            "consultation_fee": visit.consultation_fee,
            "doctor_advice": visit.doctor_advice,
            "items": items,
            "total_amount": visit.total_amount,
            "status": visit.status
        }
    }), 200

@bp.route('/nurse/visits/<int:visit_id>/execute', methods=['POST'])
@role_required('nurse')
def execute_visit(visit_id):
    import math
    visit = Visit.query.get_or_404(visit_id)

    if visit.status != 'pending':
        return jsonify({"msg": "Visit is not in pending status"}), 400

    data = request.get_json() or {}
    payment_method = data.get('payment_method', 'cash')

    for item in visit.items:
        if item.drug.type == 1:
            conv_rate = item.drug.conversion_rate or 1
            stock_needed = math.ceil(item.quantity / conv_rate) if item.is_scattered else item.quantity
            if item.drug.stock < stock_needed:
                return jsonify({"msg": f"Insufficient stock for {item.drug.name}"}), 400

    try:
        for item in visit.items:
            if item.drug.type == 1:
                conv_rate = item.drug.conversion_rate or 1
                stock_deduct = math.ceil(item.quantity / conv_rate) if item.is_scattered else item.quantity
                item.drug.stock -= stock_deduct

        user_id = get_jwt_identity()
        payment = Payment(
            visit_id=visit.id,
            nurse_id=int(user_id),
            amount=visit.total_amount,
            payment_method=payment_method
        )
        db.session.add(payment)

        visit.status = 'completed'

        db.session.commit()

        return jsonify({
            "data": {
                "payment_id": payment.id,
                "amount": payment.amount,
                "paid_at": payment.payment_date.strftime('%Y-%m-%d %H:%M')
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"Transaction failed: {str(e)}"}), 500

@bp.route('/nurse/payments/<int:payment_id>/print', methods=['PUT'])
@role_required('nurse')
def mark_printed(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    payment.receipt_printed = True
    db.session.commit()
    return jsonify({"msg": "Receipt marked as printed"}), 200

@bp.route('/nurse/drugs', methods=['GET'])
@role_required('nurse')
def list_drugs():
    keyword = request.args.get('keyword', '')
    name = request.args.get('name', '')
    specification = request.args.get('specification', '')
    batch_no = request.args.get('batch_no', '')
    inbound_start = request.args.get('inbound_start', '')
    inbound_end = request.args.get('inbound_end', '')
    pack = request.args.get('pack', 'all')
    query = Drug.query.filter(Drug.status == 1).filter(or_(Drug.type == 1, Drug.type.is_(None)))
    if pack == 'scattered':
        query = query.filter(Drug.has_scattered.is_(True))
    elif pack == 'packed':
        query = query.filter(or_(Drug.has_scattered.is_(False), Drug.has_scattered.is_(None)))
    if keyword:
        query = query.filter(
            (Drug.name.contains(keyword)) |
            (Drug.specification.contains(keyword))
        )
    if name:
        query = query.filter(Drug.name.contains(name))
    if specification:
        query = query.filter(Drug.specification.contains(specification))
    if batch_no:
        query = query.filter(Drug.batch_no.contains(batch_no))
    if inbound_start:
        try:
            query = query.filter(Drug.inbound_at >= datetime.fromisoformat(inbound_start))
        except Exception:
            pass
    if inbound_end:
        try:
            query = query.filter(Drug.inbound_at <= datetime.fromisoformat(inbound_end))
        except Exception:
            pass

    drugs = query.limit(50).all()
    data = []
    for drug in drugs:
        data.append({
            "id": drug.id,
            "name": drug.name,
            "type": drug.type,
            "specification": drug.specification,
            "unit": drug.unit,
            "price": drug.price,
            "stock": drug.stock,
            "has_scattered": drug.has_scattered,
            "scattered_price": drug.scattered_price,
            "conversion_rate": drug.conversion_rate,
            "batch_no": drug.batch_no,
            "inbound_at": drug.inbound_at.strftime('%Y-%m-%d %H:%M') if drug.inbound_at else None
        })

    return jsonify({"data": data}), 200
