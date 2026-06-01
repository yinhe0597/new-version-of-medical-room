from flask import request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.app import db
from backend.app.api import bp
from backend.app.models import (
    Drug,
    DrugStockGroup,
    InventoryRecord,
    DiagnosisDict,
    DailyStockSnapshot,
    Payment,
    PrescriptionItem,
    User,
    Visit,
    OperationLog,
    VISIT_STATUS_COMPLETED,
    VISIT_STATUS_NURSE_VERIFIED,
    VISIT_STATUS_PENDING,
    VISIT_STATUS_REJECTED,
    VISIT_STATUS_REVOKED,
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
from datetime import datetime, timezone, timedelta
from sqlalchemy import or_, func
import re
import math
import json
import io

_DIAG_LINE_CODE_RE = re.compile(r"^(?P<name>.*?)[（(](?P<code>[^）)]+)[）)]\s*$")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_GARBLED_Q_RE = re.compile(r"\?{2,}")

def _format_local_dt(dt, fmt="%Y-%m-%d %H:%M"):
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime(fmt)

def _looks_garbled_name(name: str) -> bool:
    if not isinstance(name, str):
        return False
    s = name.strip()
    if not s:
        return False
    if _CJK_RE.search(s):
        return False
    return _GARBLED_Q_RE.search(s) is not None

def _normalize_diagnosis_text_for_output(diagnosis_text):
    if not isinstance(diagnosis_text, str) or not diagnosis_text:
        return diagnosis_text

    codes_to_fix = set()
    raw_lines = re.split(r"[\r\n]+", diagnosis_text)
    for line in raw_lines:
        parts = re.split(r"[;；]+", line or "")
        for token in parts:
            t = (token or "").strip()
            if not t:
                continue
            m = _DIAG_LINE_CODE_RE.match(t)
            if not m:
                continue
            name = (m.group("name") or "").strip()
            code = (m.group("code") or "").strip()
            if code and _looks_garbled_name(name):
                codes_to_fix.add(code)

    if not codes_to_fix:
        return diagnosis_text

    rows = DiagnosisDict.query.filter(DiagnosisDict.code.in_(sorted(codes_to_fix))).all()
    names_by_code = {}
    for row in rows:
        code = (row.code or "").strip()
        name = (row.name or "").strip()
        if not code or not name:
            continue
        names_by_code.setdefault(code, []).append(name)

    def pick_name(code: str):
        candidates = names_by_code.get(code) or []
        good = [x for x in candidates if not _looks_garbled_name(x)]
        good = [x for x in good if _CJK_RE.search(x) or re.search(r"[A-Za-z]", x)]
        good.sort(key=lambda x: (len(x), x))
        return good[0] if good else None

    fixed_lines = []
    for line in raw_lines:
        segs = re.split(r"([;；]+)", line or "")
        out = []
        for seg in segs:
            if seg is None:
                continue
            if re.fullmatch(r"[;；]+", seg):
                out.append(seg)
                continue
            token = (seg or "").strip()
            if not token:
                out.append(seg)
                continue
            m = _DIAG_LINE_CODE_RE.match(token)
            if not m:
                out.append(seg)
                continue
            name = (m.group("name") or "").strip()
            code = (m.group("code") or "").strip()
            if not code or not _looks_garbled_name(name):
                out.append(seg)
                continue
            best = pick_name(code)
            if not best:
                out.append(seg)
                continue
            use_fullwidth = "（" in token or "）" in token
            if use_fullwidth:
                out.append(f"{best}（{code}）")
            else:
                out.append(f"{best} ({code})")
        fixed_lines.append("".join(out))

    return "\n".join(fixed_lines)

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
            "created_at": _format_local_dt(visit.timestamp, "%Y-%m-%d %H:%M"),
            "total_amount": visit.total_amount,
            "status": visit.status,
        })

    return jsonify({"data": data}), 200


@bp.route("/nurse/drug-names/search", methods=["GET"])
@role_required(["nurse", "admin"])
def search_drug_names():
    keyword = (request.args.get("keyword") or "").strip()
    query = db.session.query(Drug.base_name, Drug.name).filter(Drug.type.in_([1, 3]))
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

    if item_type == 2:
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

    if item_type == 3:
        specification = (data.get("specification") or "").strip()
        unit = (data.get("unit") or "").strip() or "个"
        try:
            price_val = float(data.get("price"))
        except Exception:
            return jsonify({"msg": "Invalid price"}), 400
        if price_val <= 0:
            return jsonify({"msg": "price must be > 0"}), 400
        try:
            inbound_qty = int(data.get("inbound_quantity") or 0)
        except Exception:
            return jsonify({"msg": "Invalid inbound_quantity"}), 400
        if inbound_qty <= 0:
            return jsonify({"msg": "inbound_quantity must be > 0"}), 400

        existing = Drug.query.filter(
            Drug.type == 3,
            Drug.name == name,
            Drug.specification == specification,
            Drug.batch_no == batch_no,
            Drug.status == 1,
            Drug.variant_type == "consumable",
        ).first()
        if existing:
            return jsonify({"msg": "Duplicate consumable for same batch", "data": {"drug_id": existing.id}}), 409

        now = datetime.utcnow()
        drug = Drug(
            name=name,
            base_name=name,
            type=3,
            specification=specification,
            unit=unit,
            price=price_val,
            stock=inbound_qty,
            status=1,
            batch_no=batch_no,
            inbound_at=now,
            variant_type="consumable",
            purchase_price=float(data.get("purchase_price") or 0.0),
        )
        db.session.add(drug)
        db.session.commit()

        ir = InventoryRecord(
            drug_id=drug.id,
            nurse_id=int(user_id),
            old_stock=0,
            new_stock=inbound_qty,
            remark="入库耗材",
            timestamp=now,
        )
        db.session.add(ir)
        db.session.commit()

        log = OperationLog(
            user_id=int(user_id),
            action_type='nurse_inbound',
            target_type='drug',
            target_id=drug.id,
            summary=f"入库耗材: {drug.name} x{inbound_qty}{unit}"
        )
        db.session.add(log)
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

    log = OperationLog(
        user_id=int(user_id),
        action_type='nurse_inbound',
        target_type='drug',
        target_id=pack_drug.id,
        summary=f"入库药品: {base_name} ({pack_spec}) 批次:{batch_no}",
        details=json.dumps({
            "base_name": base_name,
            "pack_spec": pack_spec,
            "batch_no": batch_no,
            "pack_drug_id": pack_drug.id,
            "retail_drug_id": retail_drug.id if retail_drug else None,
        }, ensure_ascii=False)
    )
    db.session.add(log)
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

        log = OperationLog(
            user_id=int(user_id),
            action_type='nurse_inventory_adjust',
            target_type='drug',
            target_id=drug_id,
            summary=f"库存调整: {drug.name} {record.old_stock}→{int(new_stock)}",
            details=json.dumps({
                "drug_name": drug.name,
                "old_stock": record.old_stock,
                "new_stock": int(new_stock),
                "remark": remark
            }, ensure_ascii=False)
        )
        db.session.add(log)
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
            "timestamp": (record.timestamp + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
        })

    return jsonify({
        "data": data,
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total
        }
    }), 200


def _compute_monthly_report(start_date_str, end_date_str):
    """核心算法：计算月度盘点报表数据"""
    from datetime import date as date_type

    try:
        start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date_str, '%Y-%m-%d')
    except (ValueError, TypeError):
        return None, "Invalid date format, use YYYY-MM-DD"

    start_date = start_dt.date()
    end_date = end_dt.date()

    # 本地时间转UTC
    start_datetime_utc = start_dt - timedelta(hours=8)
    end_datetime_utc = end_dt.replace(hour=23, minute=59, second=59) - timedelta(hours=8)

    # 查询活跃药品
    drugs = Drug.query.filter(
        Drug.status == 1,
        or_(Drug.type.in_([1, 3]), Drug.type.is_(None))
    ).order_by(Drug.storage_location.asc().nullslast()).all()

    if not drugs:
        return [], None

    drug_ids = [d.id for d in drugs]
    drug_map = {d.id: d for d in drugs}

    # 批量查询：期间入库（remark LIKE '入库%'）
    inbound_query = (
        db.session.query(
            InventoryRecord.drug_id,
            func.sum(InventoryRecord.new_stock - InventoryRecord.old_stock)
        )
        .filter(
            InventoryRecord.drug_id.in_(drug_ids),
            InventoryRecord.remark.like('入库%'),
            InventoryRecord.timestamp >= start_datetime_utc,
            InventoryRecord.timestamp <= end_datetime_utc
        )
        .group_by(InventoryRecord.drug_id)
        .all()
    )
    inbound_map = {row[0]: int(row[1] or 0) for row in inbound_query}

    # 批量查询：期间盘点调整（remark NOT LIKE '入库%'）
    adjustment_query = (
        db.session.query(
            InventoryRecord.drug_id,
            func.sum(InventoryRecord.new_stock - InventoryRecord.old_stock)
        )
        .filter(
            InventoryRecord.drug_id.in_(drug_ids),
            ~InventoryRecord.remark.like('入库%'),
            InventoryRecord.timestamp >= start_datetime_utc,
            InventoryRecord.timestamp <= end_datetime_utc
        )
        .group_by(InventoryRecord.drug_id)
        .all()
    )
    adjustment_map = {row[0]: int(row[1] or 0) for row in adjustment_query}

    # 批量查询：期间出库处方项
    outbound_items = (
        db.session.query(
            PrescriptionItem.drug_id,
            PrescriptionItem.quantity,
            PrescriptionItem.is_scattered
        )
        .join(Visit, PrescriptionItem.visit_id == Visit.id)
        .join(Payment, Payment.visit_id == Visit.id)
        .filter(
            PrescriptionItem.drug_id.in_(drug_ids),
            Visit.status == VISIT_STATUS_COMPLETED,
            Payment.payment_date >= start_datetime_utc,
            Payment.payment_date <= end_datetime_utc
        )
        .all()
    )

    # 计算出库扣减量
    outbound_map = {}
    for drug_id, quantity, is_scattered in outbound_items:
        drug = drug_map.get(drug_id)
        if not drug:
            continue
        deduction = _calc_deduction(drug, quantity, is_scattered)
        outbound_map[drug_id] = outbound_map.get(drug_id, 0) + deduction

    # 批量获取快照
    start_snapshots = {s.drug_id: s.stock for s in
        DailyStockSnapshot.query.filter_by(date=start_date).all()}
    end_snapshots = {s.drug_id: s.stock for s in
        DailyStockSnapshot.query.filter_by(date=end_date).all()}

    # 回退计算所需：期末反推
    ir_after_end = (
        db.session.query(
            InventoryRecord.drug_id,
            func.sum(InventoryRecord.new_stock - InventoryRecord.old_stock)
        )
        .filter(
            InventoryRecord.drug_id.in_(drug_ids),
            InventoryRecord.timestamp > end_datetime_utc
        )
        .group_by(InventoryRecord.drug_id)
        .all()
    )
    ir_after_end_map = {row[0]: int(row[1] or 0) for row in ir_after_end}

    dispensing_after_end = (
        db.session.query(
            PrescriptionItem.drug_id,
            PrescriptionItem.quantity,
            PrescriptionItem.is_scattered
        )
        .join(Visit, PrescriptionItem.visit_id == Visit.id)
        .join(Payment, Payment.visit_id == Visit.id)
        .filter(
            PrescriptionItem.drug_id.in_(drug_ids),
            Visit.status == VISIT_STATUS_COMPLETED,
            Payment.payment_date > end_datetime_utc
        )
        .all()
    )
    disp_after_end_map = {}
    for drug_id, quantity, is_scattered in dispensing_after_end:
        drug = drug_map.get(drug_id)
        if not drug:
            continue
        deduction = _calc_deduction(drug, quantity, is_scattered)
        disp_after_end_map[drug_id] = disp_after_end_map.get(drug_id, 0) + deduction

    # 回退计算所需：期初反推
    ir_after_start = (
        db.session.query(
            InventoryRecord.drug_id,
            func.sum(InventoryRecord.new_stock - InventoryRecord.old_stock)
        )
        .filter(
            InventoryRecord.drug_id.in_(drug_ids),
            InventoryRecord.timestamp >= start_datetime_utc
        )
        .group_by(InventoryRecord.drug_id)
        .all()
    )
    ir_after_start_map = {row[0]: int(row[1] or 0) for row in ir_after_start}

    dispensing_after_start = (
        db.session.query(
            PrescriptionItem.drug_id,
            PrescriptionItem.quantity,
            PrescriptionItem.is_scattered
        )
        .join(Visit, PrescriptionItem.visit_id == Visit.id)
        .join(Payment, Payment.visit_id == Visit.id)
        .filter(
            PrescriptionItem.drug_id.in_(drug_ids),
            Visit.status == VISIT_STATUS_COMPLETED,
            Payment.payment_date >= start_datetime_utc
        )
        .all()
    )
    disp_after_start_map = {}
    for drug_id, quantity, is_scattered in dispensing_after_start:
        drug = drug_map.get(drug_id)
        if not drug:
            continue
        deduction = _calc_deduction(drug, quantity, is_scattered)
        disp_after_start_map[drug_id] = disp_after_start_map.get(drug_id, 0) + deduction

    # 组装结果
    result = []
    for drug in drugs:
        current_stock = int(drug.stock or 0)

        # 期初库存：优先快照，回退反推
        opening_stock = start_snapshots.get(drug.id)
        if opening_stock is None:
            opening_stock = current_stock - ir_after_start_map.get(drug.id, 0) + disp_after_start_map.get(drug.id, 0)

        # 期末库存：今天用当前库存，否则优先快照，回退反推
        if end_date == date_type.today():
            closing_stock = current_stock
        else:
            closing_stock = end_snapshots.get(drug.id)
            if closing_stock is None:
                closing_stock = current_stock - ir_after_end_map.get(drug.id, 0) + disp_after_end_map.get(drug.id, 0)
        inbound = inbound_map.get(drug.id, 0)
        outbound = outbound_map.get(drug.id, 0)
        adjustment = adjustment_map.get(drug.id, 0)

        # 过滤无变动且库存为0的药品
        if inbound == 0 and outbound == 0 and adjustment == 0 and opening_stock == 0 and closing_stock == 0:
            continue

        purchase_price = float(drug.purchase_price or 0)
        result.append({
            "drug_id": drug.id,
            "drug_name": drug.name,
            "type": drug.type,
            "variant_type": drug.variant_type,
            "specification": drug.specification,
            "purchase_price": purchase_price,
            "unit": drug.unit,
            "opening_stock": opening_stock,
            "inbound": inbound,
            "outbound": outbound,
            "adjustment": adjustment,
            "closing_stock": closing_stock,
            "inbound_amount": round(purchase_price * inbound, 2),
            "current_stock_amount": round(purchase_price * closing_stock, 2),
        })

    return result, None


def _calc_deduction(drug, quantity, is_scattered):
    """计算出库扣减量（与execute_visit一致）"""
    qty = int(quantity or 0)
    if drug.stock_group_code:
        unit_amount = int(drug.unit_amount or 1)
        return math.ceil(qty / unit_amount)
    if is_scattered and not drug.stock_group_code:
        conv_rate = drug.conversion_rate or 1
        return math.ceil(qty / conv_rate)
    return qty


@bp.route('/nurse/inventory/monthly-report', methods=['GET'])
@role_required(['nurse', 'admin'])
def get_monthly_report():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date or not end_date:
        return jsonify({"msg": "Missing start_date or end_date"}), 400

    data, error = _compute_monthly_report(start_date, end_date)
    if error:
        return jsonify({"msg": error}), 400

    return jsonify({
        "data": data,
        "meta": {"total": len(data)}
    }), 200


@bp.route('/nurse/inventory/monthly-report/export', methods=['GET'])
@role_required(['nurse', 'admin'])
def export_monthly_report():
    from openpyxl import Workbook

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date or not end_date:
        return jsonify({"msg": "Missing start_date or end_date"}), 400

    data, error = _compute_monthly_report(start_date, end_date)
    if error:
        return jsonify({"msg": error}), 400

    wb = Workbook()
    ws = wb.active
    ws.title = "月度盘点报表"

    headers = ["序号", "名称", "类型", "规格", "购进价", "单位", "上月盘点数（期初）", "入库数", "出库数", "盘点调整", "现存数（期末）", "本月进药金额", "现库存金额"]
    ws.append(headers)

    for idx, item in enumerate(data, 1):
        ws.append([
            idx,
            item["drug_name"],
            "耗材" if item.get("type") == 3 else "药品",
            item["specification"],
            item["purchase_price"],
            item["unit"],
            item["opening_stock"],
            item["inbound"],
            item["outbound"],
            item["adjustment"],
            item["closing_stock"],
            item["inbound_amount"],
            item["current_stock_amount"],
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"月度盘点报表_{start_date}_{end_date}.xlsx"
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )

@bp.route('/nurse/visits/<int:visit_id>', methods=['GET'])
@role_required('nurse')
def get_visit_detail(visit_id):
    visit = Visit.query.options(
        db.joinedload(Visit.patient),
        db.joinedload(Visit.doctor),
    ).get_or_404(visit_id)

    items_query = visit.items
    if hasattr(items_query, "options"):
        items_query = items_query.options(
            db.joinedload(PrescriptionItem.drug),
            db.joinedload(PrescriptionItem.modifier),
        )
    items_list = items_query.all() if hasattr(items_query, "all") else list(items_query or [])

    items = []
    for item in items_list:
        unit_price = item.new_price if item.new_price is not None else item.price_at_visit
        amount = item.new_amount if item.new_amount is not None else item.amount
        drug = item.drug
        items.append({
            "item_id": item.id,
            "drug_name": drug.name if drug else "（已删除药品）",
            "type": drug.type if drug else None,
            "specification": drug.specification if drug else "",
            "conversion_rate": drug.conversion_rate if drug else 1,
            "usage": item.usage,
            "dosage": item.dosage,
            "frequency": item.frequency,
            "timing": item.timing,
            "quantity": item.quantity,
            "unit_price": unit_price,
            "amount": amount,
            "is_scattered": item.is_scattered,
            "is_intravenous": item.is_intravenous,
            "infusion_group": item.infusion_group,
            "infusion_dosage_value": item.infusion_dosage_value,
            "infusion_dosage_unit": item.infusion_dosage_unit,
            "infusion_method": item.infusion_method,
            "stock": drug.stock if drug else 0,
            "original_price": item.original_price,
            "original_amount": item.original_amount,
            "new_price": item.new_price,
            "new_amount": item.new_amount,
            "modified_by": item.modified_by,
            "modified_by_name": item.modifier.real_name if item.modifier else None,
            "modified_at": item.modified_at.strftime('%Y-%m-%d %H:%M:%S') if item.modified_at else None,
            "modify_reason": item.modify_reason,
        })

    # 读取小票快照（支付执行时保存的 JSON 快照）
    payment = Payment.query.filter_by(visit_id=visit.id).first()
    receipt_snapshot = None
    if payment and payment.receipt_snapshot:
        try:
            receipt_snapshot = json.loads(payment.receipt_snapshot)
        except (json.JSONDecodeError, TypeError):
            receipt_snapshot = None

    return jsonify({
        "data": {
            "visit_id": visit.id,
            "patient": {
                "name": visit.patient.name if visit.patient else "未知",
                "student_id": visit.patient.student_id if visit.patient else "",
            },
            "doctor_name": visit.doctor.real_name if visit.doctor else "Unknown",
            "created_at": _format_local_dt(visit.timestamp, "%Y-%m-%d %H:%M"),
            "diagnosis": _normalize_diagnosis_text_for_output(visit.diagnosis),
            "consultation_fee": visit.consultation_fee,
            "doctor_advice": visit.doctor_advice,
            "special_note": visit.special_note,
            "items": items,
            "total_amount": visit.total_amount,
            "status": visit.status,
            "reject_reason": visit.reject_reason,
            "verified_by": visit.verified_by,
            "verified_at": _format_local_dt(visit.verified_at, "%Y-%m-%d %H:%M:%S") if visit.verified_at else None,
            "rejected_by": visit.rejected_by,
            "rejected_at": _format_local_dt(visit.rejected_at, "%Y-%m-%d %H:%M:%S") if visit.rejected_at else None,
            "receipt_snapshot": receipt_snapshot,
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

        is_stock_item = item.drug.type in (1, 3) or item.drug.type is None
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

        log = OperationLog(
            user_id=int(user_id),
            action_type='nurse_verify',
            target_type='visit',
            target_id=visit.id,
            summary=f"审核通过: {visit.patient.name if visit.patient else '未知'} ({visit.diagnosis or '无诊断'})"
        )
        db.session.add(log)
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

        log = OperationLog(
            user_id=int(user_id),
            action_type='nurse_reject',
            target_type='visit',
            target_id=visit.id,
            summary=f"驳回处方: {visit.patient.name if visit.patient else '未知'}",
            details=json.dumps({"reason": reason}, ensure_ascii=False)
        )
        db.session.add(log)
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

    log = OperationLog(
        user_id=int(user_id),
        action_type='nurse_modify_price',
        target_type='prescription_item',
        target_id=item.id,
        summary=f"改价: {item.drug.name if item.drug else '未知'} ¥{item.original_price}→¥{new_price_val}",
        details=json.dumps({
            "visit_id": visit.id,
            "drug_name": item.drug.name if item.drug else '',
            "old_price": item.original_price,
            "new_price": new_price_val,
            "old_amount": item.original_amount,
            "new_amount": new_amount_val,
            "reason": reason
        }, ensure_ascii=False)
    )
    db.session.add(log)
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


@bp.route('/nurse/visits/<int:visit_id>/service-items', methods=['POST'])
@role_required('nurse')
def add_service_item(visit_id):
    visit = Visit.query.options(db.joinedload(Visit.payment)).get_or_404(visit_id)

    if visit.status != VISIT_STATUS_NURSE_VERIFIED:
        return jsonify({"msg": f"Visit must be {VISIT_STATUS_NURSE_VERIFIED} to add service items"}), 400

    if visit.payment is not None or Payment.query.filter_by(visit_id=visit.id).first() is not None:
        return jsonify({"msg": "Visit already has payment, cannot add service items"}), 400

    data = request.get_json() or {}
    drug_id = data.get('drug_id')
    quantity = data.get('quantity')

    if drug_id is None:
        return jsonify({"msg": "Missing drug_id"}), 400

    try:
        quantity = int(quantity) if quantity is not None else 1
    except Exception:
        return jsonify({"msg": "Invalid quantity"}), 400

    if quantity <= 0:
        return jsonify({"msg": "Quantity must be > 0"}), 400

    drug = Drug.query.get_or_404(drug_id)
    if drug.type not in (2, 3):
        return jsonify({"msg": "Only service/consumable items (type=2/3) can be added by nurse"}), 400

    user_id = get_jwt_identity()
    now = datetime.utcnow()

    amount = float(drug.price or 0) * quantity
    item = PrescriptionItem(
        visit_id=visit.id,
        drug_id=drug.id,
        quantity=quantity,
        price_at_visit=float(drug.price or 0),
        amount=amount,
        modified_by=int(user_id),
        modified_at=now,
        modify_reason="护士新增诊疗项目" if drug.type == 2 else "护士新增耗材"
    )
    db.session.add(item)

    visit.total_amount = _recompute_visit_total(visit)
    db.session.commit()

    log = OperationLog(
        user_id=int(user_id),
        action_type='nurse_add_service',
        target_type='prescription_item',
        target_id=item.id,
        summary=f"护士追加{'项目' if drug.type == 2 else '耗材'}: {drug.name} x{quantity} ¥{amount}",
        details=json.dumps({
            "visit_id": visit.id,
            "drug_name": drug.name,
            "drug_type": drug.type,
            "quantity": quantity,
            "price": float(drug.price or 0),
            "amount": amount,
        }, ensure_ascii=False)
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({
        "data": {
            "visit_id": visit.id,
            "item_id": item.id,
            "drug_name": drug.name,
            "type": drug.type,
            "specification": drug.specification,
            "quantity": item.quantity,
            "unit_price": item.price_at_visit,
            "amount": item.amount,
            "total_amount": visit.total_amount,
        }
    }), 201


@bp.route('/nurse/visits/<int:visit_id>/service-items/<int:item_id>', methods=['PUT'])
@role_required('nurse')
def update_service_item(visit_id, item_id):
    visit = Visit.query.options(db.joinedload(Visit.payment)).get_or_404(visit_id)

    if visit.status != VISIT_STATUS_NURSE_VERIFIED:
        return jsonify({"msg": f"Visit must be {VISIT_STATUS_NURSE_VERIFIED} to update service items"}), 400

    if visit.payment is not None or Payment.query.filter_by(visit_id=visit.id).first() is not None:
        return jsonify({"msg": "Visit already has payment, cannot update service items"}), 400

    item = PrescriptionItem.query.filter_by(id=item_id, visit_id=visit.id).first()
    if item is None:
        return jsonify({"msg": "Prescription item not found"}), 404

    if item.drug.type not in (2, 3):
        return jsonify({"msg": "Only service/consumable items (type=2/3) can be modified by nurse"}), 400

    data = request.get_json() or {}
    quantity = data.get('quantity')

    if quantity is None:
        return jsonify({"msg": "Missing quantity"}), 400

    try:
        quantity = int(quantity)
    except Exception:
        return jsonify({"msg": "Invalid quantity"}), 400

    if quantity <= 0:
        return jsonify({"msg": "Quantity must be > 0"}), 400

    user_id = get_jwt_identity()
    now = datetime.utcnow()

    item.quantity = quantity
    item.amount = float(item.price_at_visit or 0) * quantity
    item.modified_by = int(user_id)
    item.modified_at = now
    item.modify_reason = "护士修改诊疗项目数量"

    visit.total_amount = _recompute_visit_total(visit)
    db.session.commit()

    return jsonify({
        "data": {
            "visit_id": visit.id,
            "item_id": item.id,
            "quantity": item.quantity,
            "amount": item.amount,
            "total_amount": visit.total_amount,
        }
    }), 200


@bp.route('/nurse/visits/<int:visit_id>/service-items/<int:item_id>', methods=['DELETE'])
@role_required('nurse')
def delete_service_item(visit_id, item_id):
    visit = Visit.query.options(db.joinedload(Visit.payment)).get_or_404(visit_id)

    if visit.status != VISIT_STATUS_NURSE_VERIFIED:
        return jsonify({"msg": f"Visit must be {VISIT_STATUS_NURSE_VERIFIED} to delete service items"}), 400

    if visit.payment is not None or Payment.query.filter_by(visit_id=visit.id).first() is not None:
        return jsonify({"msg": "Visit already has payment, cannot delete service items"}), 400

    item = PrescriptionItem.query.filter_by(id=item_id, visit_id=visit.id).first()
    if item is None:
        return jsonify({"msg": "Prescription item not found"}), 404

    if item.drug.type not in (2, 3):
        return jsonify({"msg": "Only service/consumable items (type=2/3) can be deleted by nurse"}), 400

    db.session.delete(item)
    visit.total_amount = _recompute_visit_total(visit)
    db.session.commit()

    return jsonify({
        "data": {
            "visit_id": visit.id,
            "total_amount": visit.total_amount,
        }
    }), 200


@bp.route('/nurse/services/search', methods=['GET'])
@role_required('nurse')
def search_services():
    keyword = (request.args.get('keyword') or "").strip()
    query = Drug.query.filter(Drug.type.in_([2, 3]), Drug.status == 1)
    if keyword:
        query = query.filter(or_(Drug.name.contains(keyword), Drug.specification.contains(keyword)))
    services = query.limit(50).all()

    data = []
    for service in services:
        data.append({
            "id": service.id,
            "name": service.name,
            "specification": service.specification,
            "price": service.price,
            "unit": service.unit,
        })

    return jsonify({"data": data}), 200

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
    employee_discount = data.get('employee_discount', False)
    actual_amount = data.get('actual_amount')

    visit.total_amount = _recompute_visit_total(visit)

    group_cache = {}
    group_deduct = {}

    for item in visit.items:
        if item.drug.type in (1, 3) or item.drug.type is None:
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
            if item.drug.type in (1, 3) or item.drug.type is None:
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

        # 计算实收金额
        final_amount = visit.total_amount
        original_amount = None
        if employee_discount and actual_amount is not None:
            original_amount = visit.total_amount
            final_amount = float(actual_amount)

        payment = Payment(
            visit_id=visit.id,
            nurse_id=int(user_id),
            amount=final_amount,
            payment_method=payment_method,
            is_employee_discount=employee_discount,
            original_amount=original_amount
        )
        db.session.add(payment)

        # 生成小票数据快照
        snapshot = {
            "patient_name": visit.patient.name if visit.patient else "未知",
            "patient_student_id": visit.patient.student_id if visit.patient else "",
            "diagnosis": visit.diagnosis or "",
            "doctor_advice": visit.doctor_advice or "",
            "special_note": visit.special_note or "",
            "items": []
        }
        for item in visit.items:
            drug = item.drug
            snapshot["items"].append({
                "drug_name": drug.name if drug else "（已删除药品）",
                "type": drug.type if drug else None,
                "specification": drug.specification if drug else "",
                "quantity": item.quantity,
                "usage": item.usage,
                "dosage": item.dosage,
                "frequency": item.frequency,
                "timing": item.timing,
                "is_intravenous": item.is_intravenous,
                "infusion_group": item.infusion_group,
                "infusion_dosage_value": item.infusion_dosage_value,
                "infusion_dosage_unit": item.infusion_dosage_unit,
                "infusion_method": item.infusion_method,
            })
        payment.receipt_snapshot = json.dumps(snapshot, ensure_ascii=False)

        visit.status = VISIT_STATUS_COMPLETED

        log = OperationLog(
            user_id=int(user_id),
            action_type='nurse_execute',
            target_type='visit',
            target_id=visit.id,
            summary=f"执行收费: {visit.patient.name if visit.patient else '未知'} ¥{final_amount}",
            details=json.dumps({
                "payment_method": payment_method,
                "amount": final_amount,
                "employee_discount": employee_discount,
                "original_amount": original_amount
            }, ensure_ascii=False)
        )
        db.session.add(log)

        db.session.commit()

        return jsonify({
            "data": {
                "payment_id": payment.id,
                "amount": payment.amount,
                "original_amount": payment.original_amount,
                "paid_at": (payment.payment_date + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M')
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"Transaction failed: {str(e)}"}), 500

@bp.route('/nurse/payments/<int:payment_id>/print', methods=['PUT'])
@role_required('nurse')
def mark_printed(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    try:
        payment.receipt_printed = True
        db.session.commit()
        return jsonify({"msg": "Receipt marked as printed"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"标记打印失败: {str(e)}"}), 500

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
    query = Drug.query.filter(Drug.status == 1).filter(or_(Drug.type.in_([1, 3]), Drug.type.is_(None)))
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

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('size', 20, type=int)
    query = query.order_by(Drug.storage_location.asc().nullslast())
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
            "price": drug.price,
            "stock": drug.stock,
            "batch_no": drug.batch_no,
            "variant_type": drug.variant_type,
            "stock_group_code": drug.stock_group_code,
            "unit_amount": drug.unit_amount,
            "has_scattered": drug.has_scattered,
            "scattered_price": drug.scattered_price,
            "conversion_rate": drug.conversion_rate,
            "inbound_at": drug.inbound_at.strftime('%Y-%m-%d %H:%M') if drug.inbound_at else None,
            "storage_location": drug.storage_location
        })

    return jsonify({
        "data": data,
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total
        }
    }), 200


@bp.route('/nurse/my-history', methods=['GET'])
@role_required('nurse')
def get_my_history():
    """获取历史处方记录（所有护士可见），支持按护士、医生、日期范围、患者姓名、状态筛选及分页"""
    # 可选的筛选参数
    nurse_id = request.args.get('nurse_id', type=int, default=None)
    doctor_id = request.args.get('doctor_id', type=int, default=None)
    date_from = request.args.get('date_from', default=None)
    date_to = request.args.get('date_to', default=None)
    search_name = request.args.get('search_name', default=None)
    status = request.args.get('status', default=None)

    # 分页参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('size', 20, type=int)

    query = Visit.query.options(
        db.joinedload(Visit.patient),
        db.joinedload(Visit.doctor),
        db.joinedload(Visit.payment),
    )

    # 护士筛选：通过 verified_by / rejected_by / revoked_by / payment.nurse_id 关联
    if nurse_id is not None:
        payment_visit_ids = db.session.query(Payment.visit_id).filter(Payment.nurse_id == nurse_id).subquery()
        query = query.filter(
            or_(
                Visit.verified_by == nurse_id,
                Visit.rejected_by == nurse_id,
                Visit.revoked_by == nurse_id,
                Visit.id.in_(payment_visit_ids)
            )
        )

    # 医生筛选
    if doctor_id is not None:
        query = query.filter(Visit.doctor_id == doctor_id)

    # 日期范围筛选
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Visit.timestamp >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            # 包含 date_to 当天全天
            dt_to = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(Visit.timestamp < dt_to)
        except ValueError:
            pass

    # 患者姓名搜索（服务器端）
    if search_name:
        query = query.join(Visit.patient).filter(Patient.name.contains(search_name))

    # 状态筛选（服务器端）
    if status:
        query = query.filter(Visit.status == status)

    # 分页查询
    pagination = query.order_by(Visit.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    visits = pagination.items

    data = []
    for visit in visits:
        payment = visit.payment
        data.append({
            "visit_id": visit.id,
            "patient_name": visit.patient.name if visit.patient else "未知",
            "student_id": visit.patient.student_id if visit.patient else "",
            "created_at": _format_local_dt(visit.timestamp, "%Y-%m-%d %H:%M"),
            "diagnosis": _normalize_diagnosis_text_for_output(visit.diagnosis) if visit.diagnosis else "",
            "doctor_name": visit.doctor.real_name if visit.doctor else "未知",
            "doctor_id": visit.doctor_id,
            "total_amount": visit.total_amount,
            "status": visit.status,
            "payment_method": payment.payment_method if payment else None,
            "payment_id": payment.id if payment else None,
            "payment_amount": float(payment.amount) if payment and payment.amount else None,
            "payment_original_amount": float(payment.original_amount) if payment and payment.original_amount else None,
            "paid_at": (payment.payment_date + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M') if payment else None,
            "verified_at": _format_local_dt(visit.verified_at, "%Y-%m-%d %H:%M:%S") if visit.verified_at else None,
            "rejected_at": _format_local_dt(visit.rejected_at, "%Y-%m-%d %H:%M:%S") if visit.rejected_at else None,
            "reject_reason": visit.reject_reason,
            "revoked_at": _format_local_dt(visit.revoked_at, "%Y-%m-%d %H:%M:%S") if visit.revoked_at else None,
            "revoke_reason": visit.revoke_reason,
        })

    return jsonify({
        "data": data,
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total
        }
    }), 200


@bp.route('/nurse/staff-list', methods=['GET'])
@role_required('nurse')
def get_nurse_staff_list():
    """返回护士和医生列表，用于前端筛选下拉"""
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


@bp.route('/nurse/visits/<int:visit_id>/revoke', methods=['POST'])
@role_required('nurse')
def revoke_visit(visit_id):
    """
    撤销已完成的交易：
    1. 还原库存（因为实际未发药）
    2. 删除 Payment 记录
    3. 标记 Visit 状态为 revoked（已撤销），保留审核痕迹
    4. 记录审计信息
    """
    visit = Visit.query.options(
        db.joinedload(Visit.payment),
    ).get_or_404(visit_id)

    # 校验状态
    if visit.status != VISIT_STATUS_COMPLETED:
        return jsonify({"msg": "只有已完成的处方才能撤销交易"}), 400

    # 校验当前护士是否为经手人
    user_id = int(get_jwt_identity())
    payment = visit.payment or Payment.query.filter_by(visit_id=visit.id).first()

    is_handler = (visit.verified_by == user_id) or (payment and payment.nurse_id == user_id)
    if not is_handler:
        return jsonify({"msg": "只有经手护士才能撤销该交易"}), 403

    # 校验撤销原因
    data = request.get_json() or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"msg": "请提供撤销原因"}), 400

    try:
        # 1. 还原库存
        items = list(visit.items or [])
        group_cache = {}
        group_restore = {}

        for item in items:
            if item.drug is None:
                continue
            is_stock_item = item.drug.type in (1, 3) or item.drug.type is None
            if not is_stock_item:
                continue  # 诊疗项目不涉及库存

            qty = int(item.quantity or 0)
            if qty <= 0:
                continue

            if item.drug.stock_group_code:
                # 库存组还原
                code = item.drug.stock_group_code
                group = group_cache.get(code)
                if group is None:
                    group = DrugStockGroup.query.filter_by(group_code=code).first()
                    if group:
                        group_cache[code] = group

                if group:
                    unit_amount = int(item.drug.unit_amount or 0)
                    if unit_amount > 0:
                        restore_units = compute_deduct_units(qty, unit_amount)
                        group_restore[code] = group_restore.get(code, 0) + restore_units
                continue

            # 普通药品库存还原
            conv_rate = item.drug.conversion_rate or 1
            stock_restore = math.ceil(qty / conv_rate) if item.is_scattered else qty
            item.drug.stock += int(stock_restore)

        # 还原库存组
        for code, units in group_restore.items():
            group = group_cache[code]
            group.total_units += int(units)
            stocks = recompute_variant_stocks(group.total_units, group.pack_amount, group.retail_amount)
            if group.pack_drug is not None:
                group.pack_drug.stock = stocks["pack_stock"]
            if group.retail_drug is not None and stocks.get("retail_stock") is not None:
                group.retail_drug.stock = stocks["retail_stock"]

        # 2. 删除 Payment 记录
        if payment:
            db.session.delete(payment)

        # 3. 标记 Visit 状态为已撤销（保留审核痕迹）
        visit.status = VISIT_STATUS_REVOKED

        # 4. 记录审计信息
        visit.revoked_by = user_id
        visit.revoked_at = datetime.utcnow()
        visit.revoke_reason = reason

        log = OperationLog(
            user_id=int(user_id),
            action_type='nurse_revoke',
            target_type='visit',
            target_id=visit.id,
            summary=f"撤销交易: {visit.patient.name if visit.patient else '未知'}",
            details=json.dumps({"reason": reason}, ensure_ascii=False)
        )
        db.session.add(log)

        db.session.commit()

        return jsonify({"msg": "交易已成功撤销"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"撤销失败: {str(e)}"}), 500
