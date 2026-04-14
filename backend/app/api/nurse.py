from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.app import db
from backend.app.api import bp
from backend.app.models import (
    Drug,
    DrugStockGroup,
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
from backend.app.services.drug_stock import (
    ValidationError,
    compute_deduct_units,
    compute_initial_stocks,
    new_group_code,
    parse_min_sale_unit,
    recompute_variant_stocks,
    validate_pack_spec,
    validate_prices,
)
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


@bp.route("/nurse/drug-names/search", methods=["GET"])
@role_required(["nurse", "admin"])
def search_drug_names():
    keyword = (request.args.get("keyword") or "").strip()
    query = db.session.query(Drug.base_name, Drug.name).filter(Drug.type == 1)
    if keyword:
        query = query.filter(or_(Drug.base_name.contains(keyword), Drug.name.contains(keyword)))
    rows = query.limit(50).all()
    names = []
    seen = set()
    for base_name, name in rows:
        val = (base_name or name or "").strip()
        if not val:
            continue
        if val in seen:
            continue
        seen.add(val)
        names.append(val)
        if len(names) >= 20:
            break
    return jsonify({"data": names}), 200


@bp.route("/nurse/inbound", methods=["POST"])
@role_required(["nurse", "admin"])
def inbound_stock():
    data = request.get_json() or {}
    item_type = int(data.get("type") or 1)

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"msg": "Missing name"}), 400

    batch_no = (data.get("batch_no") or "").strip()
    if not batch_no:
        return jsonify({"msg": "Missing batch_no"}), 400

    user_id = get_jwt_identity()

    if item_type != 1:
        specification = (data.get("specification") or "").strip()
        unit = (data.get("unit") or "").strip() or "次"
        try:
            price_val = float(data.get("price"))
        except Exception:
            return jsonify({"msg": "Invalid price"}), 400
        if price_val <= 0:
            return jsonify({"msg": "price must be > 0"}), 400

        existing = Drug.query.filter(
            Drug.type == 2,
            Drug.name == name,
            Drug.specification == specification,
            Drug.batch_no == batch_no,
            Drug.status == 1,
            or_(Drug.variant_type == "service", Drug.variant_type.is_(None)),
        ).first()
        if existing:
            return jsonify({"msg": "Duplicate item for same batch", "data": {"drug_id": existing.id}}), 409

        drug = Drug(
            name=name,
            base_name=name,
            type=2,
            specification=specification,
            unit=unit,
            price=price_val,
            stock=-1,
            status=1,
            batch_no=batch_no,
            inbound_at=datetime.utcnow(),
            variant_type="service",
        )
        db.session.add(drug)
        db.session.commit()
        return jsonify({"data": {"drug_id": drug.id}}), 201

    pack_spec = (data.get("pack_specification") or "").strip()
    try:
        pack_meta = validate_pack_spec(pack_spec)
    except ValidationError as e:
        return jsonify({"msg": e.message, "field": e.field}), 400

    pack_amount = pack_meta["pack_amount"]
    unit_name = pack_meta["unit_name"]
    pack_unit = pack_meta["pack_unit"]

    retail_enabled = bool(data.get("retail_enabled"))
    min_sale_unit = data.get("min_sale_unit")
    min_sale_price = data.get("min_sale_price")
    retail_amount = None
    retail_unit_text = None

    if retail_enabled:
        try:
            retail_meta = parse_min_sale_unit(min_sale_unit)
        except ValidationError as e:
            return jsonify({"msg": e.message, "field": e.field}), 400
        if retail_meta["unit_name"] != unit_name:
            return jsonify({"msg": "min_sale_unit unit mismatch with pack_specification", "field": "min_sale_unit"}), 400
        retail_amount = retail_meta["min_sale_amount"]
        retail_unit_text = f"{retail_amount}{unit_name}"

    try:
        prices = validate_prices(data.get("pack_price"), min_sale_price if retail_enabled else None, pack_amount, retail_amount or 1)
    except ValidationError as e:
        extra = {"msg": e.message, "field": e.field}
        if e.field == "min_sale_price" and retail_enabled:
            extra["threshold"] = float(data.get("pack_price") or 0) * (float(retail_amount) / float(pack_amount))
        return jsonify(extra), 400

    try:
        qty_info = compute_initial_stocks(data.get("inbound_quantity"), pack_amount, retail_amount if retail_enabled else None)
    except ValidationError as e:
        return jsonify({"msg": e.message, "field": e.field}), 400

    existing_pack = Drug.query.filter(
        Drug.type == 1,
        Drug.name == name,
        Drug.specification == pack_spec,
        Drug.batch_no == batch_no,
        Drug.status == 1,
        or_(Drug.variant_type == "pack", Drug.variant_type.is_(None)),
    ).first()
    if existing_pack:
        return jsonify({"msg": "Duplicate drug batch (pack)", "data": {"drug_id": existing_pack.id}}), 409

    group_code = new_group_code()
    base_name = name

    pack_drug = Drug(
        name=name,
        base_name=base_name,
        type=1,
        specification=pack_spec,
        unit=pack_unit,
        price=prices["pack_price"],
        stock=qty_info["packs"],
        status=1,
        batch_no=batch_no,
        inbound_at=datetime.utcnow(),
        variant_type="pack",
        stock_group_code=group_code,
        unit_amount=pack_amount,
    )
    db.session.add(pack_drug)
    db.session.flush()

    retail_drug = None
    if retail_enabled:
        existing_retail = Drug.query.filter_by(
            type=1,
            name=f"{name}(散)",
            specification=retail_unit_text,
            batch_no=batch_no,
            status=1,
            variant_type="retail",
        ).first()
        if existing_retail:
            return jsonify({"msg": "Duplicate drug batch (retail)", "data": {"drug_id": existing_retail.id}}), 409

        retail_drug = Drug(
            name=f"{name}(散)",
            base_name=base_name,
            type=1,
            specification=retail_unit_text,
            unit=unit_name,
            price=prices["min_sale_price"],
            stock=int(qty_info["retail_units"] or 0),
            status=1,
            batch_no=batch_no,
            inbound_at=datetime.utcnow(),
            variant_type="retail",
            stock_group_code=group_code,
            unit_amount=retail_amount,
        )
        db.session.add(retail_drug)
        db.session.flush()

    group = DrugStockGroup(
        group_code=group_code,
        batch_no=batch_no,
        base_name=base_name,
        unit_name=unit_name,
        total_units=qty_info["total_units"],
        pack_amount=pack_amount,
        retail_amount=retail_amount,
        pack_drug_id=pack_drug.id,
        retail_drug_id=retail_drug.id if retail_drug else None,
        created_by=int(user_id) if user_id is not None else None,
    )
    db.session.add(group)
    db.session.flush()

    stocks = recompute_variant_stocks(group.total_units, group.pack_amount, group.retail_amount)
    pack_old = pack_drug.stock
    pack_drug.stock = stocks["pack_stock"]
    if retail_drug is not None:
        retail_old = retail_drug.stock
        retail_drug.stock = stocks["retail_stock"]
    else:
        retail_old = None

    now = datetime.utcnow()
    db.session.add(
        InventoryRecord(
            drug_id=pack_drug.id,
            nurse_id=int(user_id),
            old_stock=pack_old,
            new_stock=pack_drug.stock,
            remark=f"入库 批次:{batch_no}",
            timestamp=now,
        )
    )
    if retail_drug is not None:
        db.session.add(
            InventoryRecord(
                drug_id=retail_drug.id,
                nurse_id=int(user_id),
                old_stock=retail_old,
                new_stock=retail_drug.stock,
                remark=f"入库(散) 批次:{batch_no}",
                timestamp=now,
            )
        )

    db.session.commit()
    resp = {"group_code": group_code, "pack_drug_id": pack_drug.id}
    if retail_drug is not None:
        resp["retail_drug_id"] = retail_drug.id
    return jsonify({"data": resp}), 201

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
    if drug.stock_group_code:
        return jsonify({"msg": "Grouped stock item cannot be adjusted via inventory endpoint"}), 400

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

@bp.route('/nurse/inventory/group', methods=['POST'])
@role_required('nurse')
def update_group_inventory():
    data = request.get_json() or {}
    group_code = data.get('group_code')
    actual_packs = data.get('actual_packs')
    actual_retail_units = data.get('actual_retail_units')
    remark = data.get('remark')

    if group_code is None or actual_packs is None or actual_retail_units is None or not remark:
        return jsonify({"msg": "Missing required fields"}), 400

    try:
        actual_packs = int(actual_packs)
        actual_retail_units = int(actual_retail_units)
    except ValueError:
        return jsonify({"msg": "Invalid quantity values"}), 400

    if actual_packs < 0 or actual_retail_units < 0:
        return jsonify({"msg": "Quantity cannot be negative"}), 400

    group = DrugStockGroup.query.filter_by(group_code=group_code).first()
    if not group:
        return jsonify({"msg": "Stock group not found"}), 404

    user_id = get_jwt_identity()

    try:
        retail_amount = group.retail_amount if group.retail_amount is not None else 1
        new_total_units = actual_packs * group.pack_amount + actual_retail_units * retail_amount

        if new_total_units == group.total_units:
            return jsonify({"msg": "Inventory is already accurate, no changes made"}), 200

        old_total_units = group.total_units
        group.total_units = new_total_units
        stocks = recompute_variant_stocks(group.total_units, group.pack_amount, group.retail_amount)
        
        now = datetime.utcnow()

        if group.pack_drug:
            pack_old = group.pack_drug.stock
            group.pack_drug.stock = stocks["pack_stock"]
            db.session.add(
                InventoryRecord(
                    drug_id=group.pack_drug.id,
                    nurse_id=int(user_id),
                    old_stock=pack_old,
                    new_stock=group.pack_drug.stock,
                    remark=f"联合盘点({remark})",
                    timestamp=now,
                )
            )

        if group.retail_drug and stocks.get("retail_stock") is not None:
            retail_old = group.retail_drug.stock
            group.retail_drug.stock = stocks["retail_stock"]
            db.session.add(
                InventoryRecord(
                    drug_id=group.retail_drug.id,
                    nurse_id=int(user_id),
                    old_stock=retail_old,
                    new_stock=group.retail_drug.stock,
                    remark=f"联合盘点(散)({remark})",
                    timestamp=now,
                )
            )

        db.session.commit()
        return jsonify({"msg": "Group inventory updated successfully"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"Failed to update group inventory: {str(e)}"}), 500

@bp.route('/nurse/inventory/records', methods=['GET'])
@role_required(['nurse', 'admin'])
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
    import math
    visit = Visit.query.get_or_404(visit_id)

    if not is_visit_status_transition_allowed(visit.status, VISIT_STATUS_NURSE_VERIFIED):
        return jsonify({"msg": f"Visit status transition not allowed: {visit.status} -> {VISIT_STATUS_NURSE_VERIFIED}"}), 400

    items = list(visit.items or [])
    if len(items) == 0:
        return jsonify({"msg": "Visit has no items"}), 400

    group_cache = {}
    group_deduct = {}
    for item in items:
        if item.drug is None:
            return jsonify({"msg": "Prescription item has no drug"}), 400
        qty = int(item.quantity or 0)
        if qty <= 0:
            return jsonify({"msg": "Invalid quantity"}), 400

        is_stock_item = item.drug.type == 1 or item.drug.type is None
        if not is_stock_item:
            if item.is_scattered:
                return jsonify({"msg": "Non-drug item cannot be scattered"}), 400
            stock_val = item.drug.stock
            if stock_val is None or int(stock_val) < 0:
                continue
            if int(stock_val) < qty:
                return jsonify({"msg": f"Insufficient stock for {item.drug.name}"}), 400
            continue

        if item.drug.stock_group_code:
            code = item.drug.stock_group_code
            group = group_cache.get(code)
            if group is None:
                group = DrugStockGroup.query.filter_by(group_code=code).first()
                if group is None:
                    return jsonify({"msg": "Stock group not found"}), 400
                group_cache[code] = group
            unit_amount = int(item.drug.unit_amount or 0)
            if unit_amount <= 0:
                return jsonify({"msg": "Invalid unit_amount"}), 400
            needed_units = compute_deduct_units(qty, unit_amount)
            pending = group_deduct.get(code, 0) + needed_units
            if group.total_units < pending:
                return jsonify({"msg": f"Insufficient stock for {item.drug.base_name or item.drug.name}"}), 400
            group_deduct[code] = pending
            continue

        conv_rate = item.drug.conversion_rate or 1
        stock_needed = math.ceil(qty / conv_rate) if item.is_scattered else qty
        if int(item.drug.stock or 0) < int(stock_needed):
            return jsonify({"msg": f"Insufficient stock for {item.drug.name}"}), 400

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

    group_cache = {}
    group_deduct = {}

    for item in visit.items:
        if item.drug.type == 1 or item.drug.type is None:
            if item.drug.stock_group_code:
                code = item.drug.stock_group_code
                group = group_cache.get(code)
                if group is None:
                    group = DrugStockGroup.query.filter_by(group_code=code).first()
                    if group is None:
                        return jsonify({"msg": "Stock group not found"}), 400
                    group_cache[code] = group
                unit_amount = int(item.drug.unit_amount or 0)
                if unit_amount <= 0:
                    return jsonify({"msg": "Invalid unit_amount"}), 400
                needed_units = compute_deduct_units(item.quantity, unit_amount)
                if needed_units <= 0:
                    return jsonify({"msg": "Invalid quantity"}), 400
                pending = group_deduct.get(code, 0) + needed_units
                if group.total_units < pending:
                    return jsonify({"msg": f"Insufficient stock for {item.drug.base_name or item.drug.name}"}), 400
                group_deduct[code] = pending
                continue
            conv_rate = item.drug.conversion_rate or 1
            stock_needed = math.ceil(item.quantity / conv_rate) if item.is_scattered else item.quantity
            if item.drug.stock < stock_needed:
                return jsonify({"msg": f"Insufficient stock for {item.drug.name}"}), 400

    try:
        for code, units in group_deduct.items():
            group = group_cache[code]
            group.total_units -= int(units)
            stocks = recompute_variant_stocks(group.total_units, group.pack_amount, group.retail_amount)
            if group.pack_drug is not None:
                group.pack_drug.stock = stocks["pack_stock"]
            if group.retail_drug is not None and stocks.get("retail_stock") is not None:
                group.retail_drug.stock = stocks["retail_stock"]

        for item in visit.items:
            if item.drug.type == 1 or item.drug.type is None:
                if item.drug.stock_group_code:
                    continue
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
@role_required(['nurse', 'admin'])
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
            "base_name": drug.base_name,
            "type": drug.type,
            "specification": drug.specification,
            "unit": drug.unit,
            "price": drug.price,
            "stock": drug.stock,
            "batch_no": drug.batch_no,
            "variant_type": drug.variant_type,
            "stock_group_code": drug.stock_group_code,
            "unit_amount": drug.unit_amount,
            "has_scattered": drug.has_scattered,
            "scattered_price": drug.scattered_price,
            "conversion_rate": drug.conversion_rate,
            "inbound_at": drug.inbound_at.strftime('%Y-%m-%d %H:%M') if drug.inbound_at else None
        })

    return jsonify({"data": data}), 200
