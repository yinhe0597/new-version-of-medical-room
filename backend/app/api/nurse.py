from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.app import db
from backend.app.api import bp
from backend.app.models import (
    Drug,
    InventoryRecord,
    Payment,
    PrescriptionItem,
    User,
    Visit,
    VISIT_STATUS_COMPLETED,
    VISIT_STATUS_NURSE_VERIFIED,
    VISIT_STATUS_PENDING,
    VISIT_STATUS_REJECTED,
    is_visit_status_transition_allowed,
)
from backend.app.utils.decorators import role_required
from datetime import datetime
from sqlalchemy import or_

def _recompute_visit_total(visit):
    items_sum = 0.0
    for item in visit.items:
        val = item.new_amount if item.new_amount is not None else item.amount
        items_sum += float(val or 0.0)
    return float(visit.consultation_fee or 0.0) + items_sum

@bp.route('/nurse/pending-visits', methods=['GET'])
@role_required('nurse')
def get_pending_visits():
    visits = (
        Visit.query.filter(Visit.status.in_([VISIT_STATUS_PENDING, VISIT_STATUS_NURSE_VERIFIED]))
        .options(db.joinedload(Visit.patient))
        .order_by(Visit.timestamp.asc())
        .all()
    )

    data = []
    for visit in visits:
        data.append({
            "visit_id": visit.id,
            "patient_name": visit.patient.name,
            "student_id": visit.patient.student_id,
            "created_at": visit.timestamp.strftime('%Y-%m-%d %H:%M'),
            "total_amount": visit.total_amount,
            "status": visit.status,
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
    visit = Visit.query.options(
        db.joinedload(Visit.patient),
        db.joinedload(Visit.doctor),
        db.joinedload(Visit.items).joinedload(PrescriptionItem.drug),
        db.joinedload(Visit.items).joinedload(PrescriptionItem.modifier),
    ).get_or_404(visit_id)

    items = []
    for item in visit.items:
        unit_price = item.new_price if item.new_price is not None else item.price_at_visit
        amount = item.new_amount if item.new_amount is not None else item.amount
        items.append({
            "item_id": item.id,
            "drug_name": item.drug.name,
            "type": item.drug.type,
            "specification": item.drug.specification,
            "conversion_rate": item.drug.conversion_rate,
            "usage": item.usage,
            "dosage": item.dosage,
            "frequency": item.frequency,
            "timing": item.timing,
            "quantity": item.quantity,
            "unit_price": unit_price,
            "amount": amount,
            "is_scattered": item.is_scattered,
            "stock": item.drug.stock,
            "original_price": item.original_price,
            "original_amount": item.original_amount,
            "new_price": item.new_price,
            "new_amount": item.new_amount,
            "modified_by": item.modified_by,
            "modified_by_name": item.modifier.real_name if item.modifier else None,
            "modified_at": item.modified_at.strftime('%Y-%m-%d %H:%M:%S') if item.modified_at else None,
            "modify_reason": item.modify_reason,
        })

    return jsonify({
        "data": {
            "visit_id": visit.id,
            "patient": {
                "name": visit.patient.name,
                "student_id": visit.patient.student_id,
            },
            "doctor_name": visit.doctor.real_name if visit.doctor else "Unknown",
            "created_at": visit.timestamp.strftime('%Y-%m-%d %H:%M'),
            "diagnosis": visit.diagnosis,
            "consultation_fee": visit.consultation_fee,
            "doctor_advice": visit.doctor_advice,
            "items": items,
            "total_amount": visit.total_amount,
            "status": visit.status,
            "reject_reason": visit.reject_reason,
            "verified_by": visit.verified_by,
            "verified_at": visit.verified_at.strftime('%Y-%m-%d %H:%M:%S') if visit.verified_at else None,
            "rejected_by": visit.rejected_by,
            "rejected_at": visit.rejected_at.strftime('%Y-%m-%d %H:%M:%S') if visit.rejected_at else None,
        }
    }), 200

@bp.route('/nurse/visits/<int:visit_id>/verify', methods=['POST'])
@role_required('nurse')
def verify_visit(visit_id):
    visit = Visit.query.get_or_404(visit_id)

    if not is_visit_status_transition_allowed(visit.status, VISIT_STATUS_NURSE_VERIFIED):
        return jsonify({"msg": f"Visit status transition not allowed: {visit.status} -> {VISIT_STATUS_NURSE_VERIFIED}"}), 400

    if visit.status != VISIT_STATUS_NURSE_VERIFIED:
        user_id = get_jwt_identity()
        visit.status = VISIT_STATUS_NURSE_VERIFIED
        visit.verified_by = int(user_id)
        visit.verified_at = datetime.utcnow()
        db.session.commit()

    return jsonify({"msg": "Visit verified"}), 200

@bp.route('/nurse/visits/<int:visit_id>/reject', methods=['POST'])
@role_required('nurse')
def reject_visit(visit_id):
    visit = Visit.query.get_or_404(visit_id)
    data = request.get_json() or {}
    reason = (data.get("reason") or "").strip()

    if not reason:
        return jsonify({"msg": "Missing reject reason"}), 400

    if not is_visit_status_transition_allowed(visit.status, VISIT_STATUS_REJECTED):
        return jsonify({"msg": f"Visit status transition not allowed: {visit.status} -> {VISIT_STATUS_REJECTED}"}), 400

    if visit.status != VISIT_STATUS_REJECTED:
        user_id = get_jwt_identity()
        visit.status = VISIT_STATUS_REJECTED
        visit.rejected_by = int(user_id)
        visit.rejected_at = datetime.utcnow()
        visit.reject_reason = reason
        db.session.commit()

    return jsonify({"msg": "Visit rejected"}), 200

@bp.route('/nurse/visits/<int:visit_id>/items/<int:item_id>/modify', methods=['PUT'])
@role_required('nurse')
def modify_prescription_item(visit_id, item_id):
    visit = Visit.query.options(db.joinedload(Visit.payment)).get_or_404(visit_id)

    if visit.status != VISIT_STATUS_NURSE_VERIFIED:
        return jsonify({"msg": f"Visit must be {VISIT_STATUS_NURSE_VERIFIED} to modify items"}), 400

    if visit.payment is not None or Payment.query.filter_by(visit_id=visit.id).first() is not None:
        return jsonify({"msg": "Visit already has payment, cannot modify items"}), 400

    item = PrescriptionItem.query.filter_by(id=item_id, visit_id=visit.id).first()
    if item is None:
        return jsonify({"msg": "Prescription item not found"}), 404

    data = request.get_json() or {}

    reason = (data.get("modify_reason") or "").strip()
    if not reason:
        return jsonify({"msg": "Missing modify_reason"}), 400

    if "quantity" in data and data.get("quantity") is not None:
        try:
            req_qty = int(data.get("quantity"))
        except Exception:
            return jsonify({"msg": "Invalid quantity"}), 400
        if req_qty != int(item.quantity or 0):
            return jsonify({"msg": "Quantity is immutable"}), 400

    new_price = data.get("new_price")
    new_amount = data.get("new_amount")

    if new_price is None and new_amount is None:
        return jsonify({"msg": "Missing new_price or new_amount"}), 400

    try:
        new_price_val = float(new_price) if new_price is not None else None
        new_amount_val = float(new_amount) if new_amount is not None else None
    except Exception:
        return jsonify({"msg": "Invalid new_price/new_amount"}), 400

    qty = int(item.quantity or 0)
    if qty <= 0:
        return jsonify({"msg": "Invalid prescription item quantity"}), 400

    if new_price_val is None:
        new_price_val = new_amount_val / qty
    if new_amount_val is None:
        new_amount_val = new_price_val * qty

    if new_price is not None and new_amount is not None:
        expected = new_price_val * qty
        if abs(expected - new_amount_val) > 0.01:
            return jsonify({"msg": "new_amount does not match new_price * quantity"}), 400

    if item.original_price is None:
        item.original_price = item.price_at_visit
    if item.original_amount is None:
        item.original_amount = item.amount

    user_id = get_jwt_identity()
    now = datetime.utcnow()

    item.new_price = new_price_val
    item.new_amount = new_amount_val
    item.modified_by = int(user_id)
    item.modified_at = now
    item.modify_reason = reason

    item.price_at_visit = new_price_val
    item.amount = new_amount_val

    visit.total_amount = _recompute_visit_total(visit)
    db.session.commit()

    return jsonify({
        "data": {
            "visit_id": visit.id,
            "item_id": item.id,
            "new_price": item.new_price,
            "new_amount": item.new_amount,
            "total_amount": visit.total_amount,
        }
    }), 200

@bp.route('/nurse/visits/<int:visit_id>/execute', methods=['POST'])
@role_required('nurse')
def execute_visit(visit_id):
    import math
    visit = Visit.query.get_or_404(visit_id)

    if visit.status != VISIT_STATUS_NURSE_VERIFIED:
        return jsonify({"msg": f"Visit must be {VISIT_STATUS_NURSE_VERIFIED} before execution"}), 400

    if visit.payment is not None or Payment.query.filter_by(visit_id=visit.id).first() is not None:
        return jsonify({"msg": "Visit already has payment"}), 400

    data = request.get_json() or {}
    payment_method = data.get('payment_method', 'cash')

    visit.total_amount = _recompute_visit_total(visit)

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
        if visit.verified_by is None:
            visit.verified_by = int(user_id)
        if visit.verified_at is None:
            visit.verified_at = datetime.utcnow()
        payment = Payment(
            visit_id=visit.id,
            nurse_id=int(user_id),
            amount=visit.total_amount,
            payment_method=payment_method
        )
        db.session.add(payment)

        visit.status = VISIT_STATUS_COMPLETED

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
