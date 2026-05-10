from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.app import db
from backend.app.api import bp
from backend.app.models import User, Patient, Visit, Drug, DrugStockGroup, PrescriptionItem, DiagnosisDict, TextTemplate, OperationLog, VISIT_STATUS_PENDING
import json
from backend.app.utils.decorators import role_required
from datetime import datetime, timezone
import math
import time
import re
from sqlalchemy import or_, case
from pypinyin import pinyin, Style


def _name_pinyin_parts(text):
    if not isinstance(text, str) or not text:
        return "", ""
    initials_list = pinyin(text, style=Style.FIRST_LETTER, strict=False)
    initials = "".join([x[0] for x in initials_list if x]).lower()
    full_list = pinyin(text, style=Style.NORMAL, strict=False)
    full = "".join([x[0] for x in full_list if x]).lower()
    return full, initials

def _diagnosis_pinyin(text):
    full, initials = _name_pinyin_parts(text)
    if not full and not initials:
        return ""
    return f"{initials}|{full}"

_DIAG_LINE_CODE_RE = re.compile(r"^(?P<name>.*?)[（(](?P<code>[^）)]+)[）)]\s*$")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_GARBLED_Q_RE = re.compile(r"\?{2,}")

_ID_CARD_RE = re.compile(r"^\d{17}[\dXx]$")

def _format_local_dt(dt, fmt="%Y-%m-%d %H:%M"):
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime(fmt)

def _is_valid_cn_id_card(id_card: str) -> bool:
    if not isinstance(id_card, str):
        return False
    s = id_card.strip()
    if not s:
        return False
    if not _ID_CARD_RE.match(s):
        return False

    birth = s[6:14]
    try:
        datetime.strptime(birth, "%Y%m%d")
    except Exception:
        return False

    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    mapping = ["1", "0", "X", "9", "8", "7", "6", "5", "4", "3", "2"]
    total = 0
    for i in range(17):
        total += int(s[i]) * weights[i]
    check = mapping[total % 11]
    return s[-1].upper() == check

def _extract_diagnosis_entries(diagnosis_text):
    if not isinstance(diagnosis_text, str):
        return []
    raw_lines = re.split(r"[\r\n]+", diagnosis_text)
    entries = []
    for line in raw_lines:
        for part in re.split(r"[;；]+", line):
            token = (part or "").strip()
            if not token:
                continue
            m = _DIAG_LINE_CODE_RE.match(token)
            if m:
                name = (m.group("name") or "").strip()
                code = (m.group("code") or "").strip()
                if name:
                    entries.append((name, code))
                continue
            entries.append((token, ""))
    return entries

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

def _upsert_diagnosis_dict_from_text(diagnosis_text):
    entries = _extract_diagnosis_entries(diagnosis_text)
    if not entries:
        return

    codes = sorted({code for _, code in entries if code})
    names = sorted({name for name, _ in entries if name})

    existing_by_code = {}
    if codes:
        for d in DiagnosisDict.query.filter(DiagnosisDict.code.in_(codes)).all():
            if d.code:
                existing_by_code[d.code] = d

    existing_by_name = {}
    if names:
        for d in DiagnosisDict.query.filter(DiagnosisDict.name.in_(names)).all():
            if d.name:
                existing_by_name[d.name] = d

    for name, code in entries:
        name = (name or "").strip()
        code = (code or "").strip()
        if not name:
            continue

        target = None
        if code:
            target = existing_by_code.get(code)
        if target is None:
            target = existing_by_name.get(name)

        py = _diagnosis_pinyin(name)

        if target is None:
            target = DiagnosisDict(code=code or "", name=name, pinyin=py)
            db.session.add(target)
            if code:
                existing_by_code[code] = target
            existing_by_name[name] = target
            continue

        if code and (target.code or "") == "":
            target.code = code
            existing_by_code[code] = target
        if (target.name or "").strip() != name:
            target.name = name
            existing_by_name[name] = target
        if py and (target.pinyin or "").strip() != py:
            target.pinyin = py

@bp.route('/doctor/patient/search', methods=['GET'])
@role_required('doctor')
def search_patient():
    import logging
    logger = logging.getLogger(__name__)
    
    start = time.perf_counter()
    keyword = request.args.get('keyword', '').strip()
    if not keyword:
        return jsonify({"msg": "Missing keyword parameter"}), 400

    kw_lower = keyword.lower()
    logger.info(f"Searching for keyword: {keyword}, kw_lower: {kw_lower}")

    user_id = get_jwt_identity()
    now_ts = time.time()
    if not hasattr(search_patient, "_rate"):
        search_patient._rate = {}
    bucket = search_patient._rate.setdefault(str(user_id), [])
    bucket[:] = [t for t in bucket if now_ts - t < 10]
    if len(bucket) >= 30:
        return jsonify({"msg": "Too many requests"}), 429
    bucket.append(now_ts)

    like_kw = f"%{keyword}%"
    like_lower = f"%{kw_lower}%"

    patients = Patient.query.filter(
        or_(
            Patient.name.ilike(like_kw),
            Patient.student_id.ilike(like_kw),
            Patient.phone.ilike(like_kw),
            Patient.name_pinyin.ilike(like_lower),
            Patient.name_initials.ilike(like_lower),
        )
    ).limit(50).all()

    logger.info(f"Found {len(patients)} patients matching keyword")

    data = []
    for p in patients:
        data.append({
            "id": p.id,
            "student_id": p.student_id,
            "name": p.name,
            "gender": p.gender,
            "grade": p.grade,
            "college": p.college,
            "major": p.major,
            "class_name": p.class_name,
            "phone": p.phone,
            "counselor_name": p.counselor_name,
            "is_temporary": bool(p.is_temporary) if p.is_temporary is not None else False,
            "age": p.age,
        })

    logger.info(f"Returning {len(data)} patients")
    
    resp = jsonify({"data": data})
    resp.headers["X-Response-Time-ms"] = f"{(time.perf_counter() - start) * 1000:.2f}"
    return resp, 200

@bp.route('/doctor/patient', methods=['POST'])
@role_required('doctor')
def create_patient():
    data = request.get_json() or {}
    required_fields = ['name', 'gender']

    for field in required_fields:
        if field not in data:
            return jsonify({"msg": f"Missing required field: {field}"}), 400

    is_temporary = bool(data.get("is_temporary", False))

    student_id = (data.get("student_id") or "").strip() or None
    if is_temporary:
        student_id = None

    if student_id:
        existing = Patient.query.filter_by(student_id=student_id).first()
        if existing:
            return jsonify({"data": {"id": existing.id}}), 200

    name = (data.get("name") or "").strip()
    gender = (data.get("gender") or "").strip()
    phone = (data.get("phone") or "").strip() or None
    age_val = data.get("age")
    id_card = (data.get("id_card") or "").strip() or None

    if is_temporary:
        if not phone:
            return jsonify({"msg": "Missing required field: phone", "field": "phone"}), 400
        try:
            age = int(age_val)
        except Exception:
            return jsonify({"msg": "Invalid age", "field": "age"}), 400
        if age <= 0 or age > 150:
            return jsonify({"msg": "Invalid age", "field": "age"}), 400
        if id_card and not _is_valid_cn_id_card(id_card):
            return jsonify({"msg": "Invalid id_card", "field": "id_card"}), 400
    else:
        age = None
        if age_val not in (None, ""):
            try:
                age = int(age_val)
            except Exception:
                return jsonify({"msg": "Invalid age", "field": "age"}), 400
            if age <= 0 or age > 150:
                return jsonify({"msg": "Invalid age", "field": "age"}), 400
        if id_card and not _is_valid_cn_id_card(id_card):
            return jsonify({"msg": "Invalid id_card", "field": "id_card"}), 400

    full_py, initials_py = _name_pinyin_parts(name)
    patient = Patient(
        student_id=student_id,
        name=name,
        name_pinyin=full_py,
        name_initials=initials_py,
        gender=gender,
        grade=(data.get("grade") or "").strip() or None,
        college=(data.get("college") or "").strip() or None,
        major=(data.get("major") or "").strip() or None,
        class_name=(data.get("class_name") or "").strip() or None,
        phone=phone,
        counselor_name=(data.get("counselor_name") or "").strip() or None,
        is_temporary=is_temporary,
        age=age,
        id_card=id_card
    )
    db.session.add(patient)
    db.session.commit()

    return jsonify({"data": {"id": patient.id}}), 201

@bp.route('/doctor/patient/<int:id>', methods=['PUT'])
@role_required('doctor')
def update_patient(id):
    patient = Patient.query.get_or_404(id)
    data = request.get_json() or {}
    
    if 'phone' in data:
        patient.phone = data['phone']

    if 'age' in data:
        try:
            age = int(data.get("age"))
        except Exception:
            return jsonify({"msg": "Invalid age", "field": "age"}), 400
        if age <= 0 or age > 150:
            return jsonify({"msg": "Invalid age", "field": "age"}), 400
        patient.age = age

    if 'id_card' in data:
        id_card = (data.get("id_card") or "").strip() or None
        if id_card and not _is_valid_cn_id_card(id_card):
            return jsonify({"msg": "Invalid id_card", "field": "id_card"}), 400
        patient.id_card = id_card
        
    db.session.commit()
    return jsonify({"msg": "Patient updated successfully"}), 200

@bp.route('/doctor/patient/<int:patient_id>/visits', methods=['GET'])
@role_required('doctor')
def get_patient_history(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    visits = patient.visits.order_by(Visit.timestamp.desc()).all()

    data = []
    for visit in visits:
        data.append({
            "visit_id": visit.id,
            "date": visit.timestamp.strftime('%Y-%m-%d %H:%M'),
            "diagnosis": visit.diagnosis,
            "total_amount": visit.total_amount
        })

    return jsonify({"data": data}), 200

@bp.route('/doctor/drugs/search', methods=['GET'])
@role_required('doctor')
def search_drugs():
    keyword = request.args.get('keyword', '')
    query = Drug.query.filter_by(status=1)
    if keyword:
        query = query.filter(
            (Drug.name.contains(keyword)) |
            (Drug.specification.contains(keyword))
        )

    drugs = query.limit(20).all()
    data = []
    for drug in drugs:
        if (drug.type == 1 or drug.type is None) and (drug.stock or 0) <= 0:
            if drug.variant_type in ["retail", "pack"] or drug.has_scattered:
                continue
        data.append({
            "id": drug.id,
            "name": drug.name,
            "base_name": drug.base_name,
            "type": drug.type,
            "specification": drug.specification,
            "unit": drug.unit,
            "price": drug.price,
            "variant_type": drug.variant_type,
            "stock_group_code": drug.stock_group_code,
            "unit_amount": drug.unit_amount,
            "has_scattered": drug.has_scattered,
            "scattered_price": drug.scattered_price,
            "conversion_rate": drug.conversion_rate,
            "stock": drug.stock
        })

    return jsonify({"data": data}), 200

@bp.route('/doctor/diagnoses/search', methods=['GET'])
@role_required('doctor')
def search_diagnoses():
    keyword = request.args.get('keyword', '').lower()
    query = DiagnosisDict.query
    if keyword:
        # Check if it contains Chinese characters
        if any('\u4e00' <= char <= '\u9fff' for char in keyword):
            # Keyword has Chinese, match name
            query = query.filter(DiagnosisDict.name.contains(keyword))
        else:
            # Keyword is english/pinyin/code
            query = query.filter(
                (DiagnosisDict.code.contains(keyword)) |
                (DiagnosisDict.pinyin.contains(f"{keyword}|")) |
                (DiagnosisDict.pinyin.contains(f"|{keyword}")) |
                (DiagnosisDict.pinyin.like(f"{keyword}%")) |
                (DiagnosisDict.pinyin.like(f"%|{keyword}%")) |
                (DiagnosisDict.pinyin.contains(keyword)) |
                (DiagnosisDict.name.contains(keyword))
            )

    # First fetch some, since memory sort is needed
    diagnoses = query.limit(200).all()
    
    # Sort handling for better matching
    if not any('\u4e00' <= char <= '\u9fff' for char in keyword):
        # 1. Exact match code or starts with code
        # 2. Pinyin contains |keyword (exact match of full pinyin)
        # 3. Pinyin starts with keyword (exact match of initials)
        # 4. Pinyin contains keyword exactly like gm (in gmpy)
        # 5. Other contains
        def sort_key(x):
            code = (x.code or "").lower()
            if code == keyword: return 0
            if code.startswith(keyword): return 1
            
            pinyin_parts = (x.pinyin or "").split('|')
            initials = pinyin_parts[0] if len(pinyin_parts) > 0 else ""
            full_pinyin = pinyin_parts[1] if len(pinyin_parts) > 1 else ""
            
            # Exact match for full pinyin
            if full_pinyin == keyword: return 2
            # Exact match for initials
            if initials == keyword: return 3
            
            if full_pinyin.startswith(keyword): return 4
            if initials.startswith(keyword): return 5 + len(initials) / 100.0
            
            if keyword in initials: return 6
            if keyword in full_pinyin: return 7
            
            if keyword in x.name.lower(): return 8
            
            return 9
            
        diagnoses = query.limit(500).all()
        diagnoses.sort(key=sort_key)
        
    # Before truncating, maybe specifically find common diseases like "感冒" if matched
    if not any('\u4e00' <= char <= '\u9fff' for char in keyword):
        # We also sort by the length of the name so shorter ones (like "感冒") appear before "急性鼻咽炎［感冒］" if both match equally
        def final_sort_key(x):
            # Check if name is exactly "感冒" and keyword is "gm"
            is_exact_common = 0
            if keyword == 'gm' and x.name == '感冒': is_exact_common = -1
            if keyword == 'ganmao' and x.name == '感冒': is_exact_common = -1
            return (is_exact_common, sort_key(x), len(x.name))
        diagnoses.sort(key=final_sort_key)
        
    diagnoses = diagnoses[:50]
    data = []
    for diag in diagnoses:
        data.append({
            "id": diag.id,
            "code": diag.code,
            "name": diag.name,
            "pinyin": diag.pinyin
        })

    return jsonify({"data": data}), 200

@bp.route('/doctor/visits', methods=['POST'])
@role_required('doctor')
def create_visit():
    data = request.get_json() or {}
    patient_id = data.get('patient_id')
    items = data.get('items', [])

    if not patient_id:
        return jsonify({"msg": "Missing patient_id"}), 400

    diagnosis = (data.get("diagnosis") or "").strip()
    if not diagnosis:
        return jsonify({"msg": "Missing diagnosis", "field": "diagnosis"}), 400

    if not isinstance(items, list) or len(items) == 0:
        return jsonify({"msg": "Missing items", "field": "items"}), 400

    # Verify stock availability
    total_amount = round(float(data.get('consultation_fee', 0)), 2)
    drug_items = []

    for idx, item in enumerate(items):
        drug_id = item.get("drug_id") if isinstance(item, dict) else None
        if drug_id is None:
            return jsonify({"msg": "Missing drug_id", "field": "drug_id", "item_index": idx}), 400

        drug = Drug.query.get(drug_id)
        if not drug:
            return jsonify({"msg": f"Drug/Item {drug_id} not found", "item_index": idx}), 404

        try:
            quantity = int(item.get("quantity"))
        except Exception:
            return jsonify({"msg": "Invalid quantity", "field": "quantity", "item_index": idx}), 400
        if quantity <= 0:
            return jsonify({"msg": "Invalid quantity", "field": "quantity", "item_index": idx}), 400

        try:
            days = int(item.get("days", 1))
        except Exception:
            return jsonify({"msg": "Invalid days", "field": "days", "item_index": idx}), 400
        if days <= 0:
            return jsonify({"msg": "Invalid days", "field": "days", "item_index": idx}), 400

        if drug.type == 1 or drug.type is None:
            for f in ["usage", "dosage", "frequency", "timing"]:
                val = (item.get(f) or "").strip()
                if not val:
                    return jsonify({"msg": f"Missing {f}", "field": f, "item_index": idx}), 400

        if (drug.type == 1 or drug.type is None) and drug.stock_group_code:
            group = DrugStockGroup.query.filter_by(group_code=drug.stock_group_code).first()
            if group is None:
                return jsonify({"msg": "Stock group not found"}), 400
            unit_amount = int(drug.unit_amount or 0)
            if unit_amount <= 0:
                return jsonify({"msg": "Invalid unit_amount", "item_index": idx}), 400
            needed_units = quantity * unit_amount
            if group.total_units < needed_units:
                pack_avail = group.total_units // int(group.pack_amount or 1)
                retail_avail = group.total_units // int(group.retail_amount or 1) if group.retail_amount else None
                extra = f", pack_available={pack_avail}"
                if retail_avail is not None:
                    extra += f", retail_available={retail_avail}"
                return jsonify({"msg": f"Insufficient stock for {drug.base_name or drug.name}{extra}"}), 400

            unit_price = round(drug.price or 0.0, 2)
            if drug.variant_type == "retail" and group.pack_drug and group.pack_drug.purchase_price and group.pack_amount:
                purchase_cost = round(float(group.pack_drug.purchase_price or 0.0) / float(group.pack_amount) * float(unit_amount) * quantity, 2)
            else:
                purchase_cost = round(float(drug.purchase_price or 0.0) * quantity, 2)

            item_amount = round(quantity * unit_price, 2)
            total_amount += item_amount
            drug_items.append({
                "drug": drug,
                "quantity": quantity,
                "usage": item.get("usage"),
                "dosage": item.get("dosage"),
                "frequency": item.get("frequency"),
                "timing": item.get("timing"),
                "days": days,
                "price_at_visit": unit_price,
                "amount": item_amount,
                "is_scattered": False,
                "purchase_cost": purchase_cost,
            })
            continue

        is_scattered = bool(item.get('is_scattered', False)) if (drug.type == 1 or drug.type is None) else False
        
        # 不支持散装的药品，自动降级为普通售卖
        if is_scattered and not drug.has_scattered:
            is_scattered = False

        # Calculate prices and costs
        if is_scattered:
            unit_price = round(drug.scattered_price or 0.0, 2)
            conv_rate = drug.conversion_rate or 1
            purchase_cost = round((drug.purchase_price or 0.0) / conv_rate * quantity, 2)
            stock_needed = quantity / conv_rate
        else:
            unit_price = round(drug.price or 0.0, 2)
            purchase_cost = round((drug.purchase_price or 0.0) * quantity, 2)
            stock_needed = quantity

        if (drug.type in (1, 3) or drug.type is None) and drug.stock < math.ceil(stock_needed):
            return jsonify({"msg": f"Insufficient stock for {drug.name}"}), 400

        item_amount = round(quantity * unit_price, 2)
        total_amount += item_amount

        drug_items.append({
            "drug": drug,
            "quantity": quantity,
            "usage": item.get('usage'),
            "dosage": item.get('dosage'),
            "frequency": item.get('frequency'),
            "timing": item.get('timing'),
            "days": days,
            "price_at_visit": unit_price,
            "amount": item_amount,
            "is_scattered": is_scattered,
            "purchase_cost": purchase_cost
        })

    # Create Visit
    user_id = get_jwt_identity()
    visit = Visit(
        patient_id=patient_id,
        doctor_id=int(user_id),
        chief_complaint=data.get('chief_complaint'),
        present_illness=data.get('present_illness'),
        past_history=data.get('past_history'),
        physical_exam=data.get('physical_exam'),
        diagnosis=diagnosis,
        doctor_advice=data.get('doctor_advice'),
        special_note=data.get('special_note'),
        consultation_fee=data.get('consultation_fee', 0),
        total_amount=total_amount,
        status=VISIT_STATUS_PENDING
    )
    db.session.add(visit)
    db.session.flush() # get visit.id

    _upsert_diagnosis_dict_from_text(diagnosis)

    # Create Prescription Items
    for item in drug_items:
        p_item = PrescriptionItem(
            visit_id=visit.id,
            drug_id=item['drug'].id,
            usage=item['usage'],
            dosage=item['dosage'],
            frequency=item['frequency'],
            timing=item['timing'],
            days=item['days'],
            quantity=item['quantity'],
            price_at_visit=item['price_at_visit'],
            amount=item['amount'],
            original_price=item['price_at_visit'],
            original_amount=item['amount'],
            new_price=item['price_at_visit'],
            new_amount=item['amount'],
            is_scattered=item['is_scattered'],
            purchase_cost=item['purchase_cost']
        )
        db.session.add(p_item)

    db.session.commit()

    # 检查是否为临时人员就诊
    patient = Patient.query.get(patient_id)
    if patient and patient.is_temporary:
        log = OperationLog(
            user_id=int(get_jwt_identity()),
            action_type='temp_patient_visit',
            target_type='visit',
            target_id=visit.id,
            summary=f"临时人员就诊: {patient.name}",
            details=json.dumps({
                "patient_name": patient.name,
                "patient_id": patient.id,
                "diagnosis": visit.diagnosis or ""
            }, ensure_ascii=False)
        )
        db.session.add(log)
        db.session.commit()

    return jsonify({"data": {"visit_id": visit.id}}), 201

@bp.route('/doctor/visits/history', methods=['GET'])
@role_required('doctor')
def get_visit_history():
    user_id = get_jwt_identity()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('size', 20, type=int)

    query = Visit.query.filter_by(doctor_id=int(user_id)).order_by(Visit.timestamp.desc())

    # Optional filters
    start_date = request.args.get('start_date')
    if start_date:
        query = query.filter(Visit.timestamp >= datetime.strptime(start_date, '%Y-%m-%d'))

    # Preload patient information to avoid N+1 queries
    query = query.options(db.joinedload(Visit.patient))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    data = []
    for visit in pagination.items:
        data.append({
            "id": visit.id,
            "patient_id": visit.patient_id,
            "patient_name": visit.patient.name,
            "student_id": visit.patient.student_id,
            "date": _format_local_dt(visit.timestamp, "%Y-%m-%d %H:%M"),
            "diagnosis": _normalize_diagnosis_text_for_output(visit.diagnosis),
            "status": visit.status,
            "total_amount": visit.total_amount,
            "medical_record_incomplete": (
                not (visit.chief_complaint or '').strip()
                and not (visit.present_illness or '').strip()
                and not (visit.physical_exam or '').strip()
            )
        })

    return jsonify({
        "data": data,
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total,
            "pages": pagination.pages
        }
    }), 200

@bp.route('/doctor/visits/<int:visit_id>', methods=['GET'])
@role_required('doctor')
def get_doctor_visit_detail(visit_id):
    user_id = get_jwt_identity()
    # Preload patient, items and drug information to avoid N+1 queries
    visit = Visit.query.options(
        db.joinedload(Visit.patient),
        db.joinedload(Visit.verifier),
        db.joinedload(Visit.rejector),
    ).get_or_404(visit_id)

    # Ensure doctor can only view their own visits (or maybe allow viewing others? For now restrict to own)
    if visit.doctor_id != int(user_id):
        return jsonify({"msg": "Unauthorized to view this visit"}), 403

    items_query = visit.items
    if hasattr(items_query, "options"):
        items_query = items_query.options(db.joinedload(PrescriptionItem.drug))
    items_list = items_query.all() if hasattr(items_query, "all") else list(items_query or [])

    items = []
    for item in items_list:
        items.append({
            "drug_id": item.drug_id,
            "drug_name": item.drug.name,
            "drug_type": item.drug.type,
            "specification": item.drug.specification,
            "usage": item.usage,
            "dosage": item.dosage,
            "frequency": item.frequency,
            "timing": item.timing,
            "days": item.days,
            "quantity": item.quantity,
            "price_at_visit": item.price_at_visit,
            "amount": item.amount,
            "is_scattered": item.is_scattered
        })

    return jsonify({
        "data": {
            "visit_id": visit.id,
            "patient": {
                "name": visit.patient.name,
                "student_id": visit.patient.student_id,
                "gender": visit.patient.gender,
                "grade": visit.patient.grade,
                "college": visit.patient.college,
                "major": visit.patient.major,
                "class_name": visit.patient.class_name,
                "phone": visit.patient.phone
            },
            "created_at": _format_local_dt(visit.timestamp, "%Y-%m-%d %H:%M"),
            "chief_complaint": visit.chief_complaint,
            "present_illness": visit.present_illness,
            "past_history": visit.past_history,
            "physical_exam": visit.physical_exam,
            "diagnosis": _normalize_diagnosis_text_for_output(visit.diagnosis),
            "doctor_advice": visit.doctor_advice,
            "special_note": visit.special_note,
            "consultation_fee": visit.consultation_fee,
            "total_amount": visit.total_amount,
            "status": visit.status,
            "reject_reason": visit.reject_reason,
            "verified_by": visit.verified_by,
            "verified_by_name": visit.verifier.real_name if visit.verifier else None,
            "verified_at": _format_local_dt(visit.verified_at, "%Y-%m-%d %H:%M:%S") if visit.verified_at else None,
            "rejected_by": visit.rejected_by,
            "rejected_by_name": visit.rejector.real_name if visit.rejector else None,
            "rejected_at": _format_local_dt(visit.rejected_at, "%Y-%m-%d %H:%M:%S") if visit.rejected_at else None,
            "items": items
        }
    }), 200

@bp.route('/doctor/visits/<int:visit_id>/medical-record', methods=['PUT'])
@jwt_required()
@role_required('doctor')
def update_visit_medical_record(visit_id):
    user_id = get_jwt_identity()
    visit = Visit.query.get_or_404(visit_id)

    if visit.doctor_id != int(user_id):
        return jsonify({"msg": "Unauthorized to update this visit"}), 403

    if visit.status == 'rejected':
        return jsonify({"msg": "Visit status does not allow modification"}), 400

    data = request.get_json(silent=True) or {}
    allowed_fields = ['chief_complaint', 'present_illness', 'past_history', 'physical_exam', 'doctor_advice', 'special_note']

    # 记录旧值用于日志
    changes = {}
    for field in allowed_fields:
        new_value = data.get(field)
        if new_value is not None:
            new_value = new_value.strip() if isinstance(new_value, str) else new_value
            old_value = getattr(visit, field) or ''
            if new_value and new_value != old_value:
                changes[field] = {"old": old_value, "new": new_value}

    # 执行字段更新
    updated = False
    for field in allowed_fields:
        value = (data.get(field) or '').strip()
        if value:
            setattr(visit, field, value)
            updated = True

    if not updated:
        return jsonify({"msg": "No valid fields to update"}), 400

    # 记录操作日志
    if changes:
        field_names_map = {
            'chief_complaint': '主诉',
            'present_illness': '现病史',
            'past_history': '既往史',
            'physical_exam': '体格检查',
            'doctor_advice': '医生留言',
            'special_note': '特殊备注'
        }
        changed_fields = [field_names_map.get(f, f) for f in changes.keys()]
        summary = f"修改了{'、'.join(changed_fields)}"

        log = OperationLog(
            user_id=int(get_jwt_identity()),
            action_type='visit_edit',
            target_type='visit',
            target_id=visit.id,
            summary=summary,
            details=json.dumps({"changes": changes}, ensure_ascii=False)
        )
        db.session.add(log)

    db.session.commit()
    return jsonify({"msg": "Medical record updated successfully"}), 200


@bp.route('/doctor/visits/<int:visit_id>/revisions', methods=['GET'])
@jwt_required()
@role_required(['doctor', 'admin'])
def get_visit_revisions(visit_id):
    """获取就诊记录的修改历史"""
    logs = OperationLog.query.filter_by(
        target_type='visit',
        target_id=visit_id,
        action_type='visit_edit'
    ).order_by(OperationLog.timestamp.desc()).all()

    data = []
    for log in logs:
        from datetime import timedelta
        local_time = log.timestamp + timedelta(hours=8) if log.timestamp else None
        data.append({
            "id": log.id,
            "user_name": log.user.real_name if log.user else "未知",
            "summary": log.summary,
            "details": json.loads(log.details) if log.details else {},
            "timestamp": local_time.strftime("%Y-%m-%d %H:%M:%S") if local_time else ""
        })

    return jsonify({"data": data}), 200

_TEXT_TEMPLATE_CATEGORIES = {"present_illness", "physical_exam", "doctor_advice"}

@bp.route('/doctor/templates', methods=['GET'])
@jwt_required()
@role_required('doctor')
def list_text_templates():
    user_id = get_jwt_identity()
    try:
        doctor_id = int(user_id)
    except (ValueError, TypeError):
        return jsonify({"msg": "Invalid user identity"}), 401

    category = (request.args.get('category') or '').strip()
    if category not in _TEXT_TEMPLATE_CATEGORIES:
        return jsonify({"msg": "Invalid category"}), 400

    q = (request.args.get('q') or '').strip()
    query = TextTemplate.query.filter_by(doctor_id=doctor_id, category=category)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(TextTemplate.title.ilike(like), TextTemplate.content.ilike(like)))

    rows = query.order_by(TextTemplate.updated_at.desc(), TextTemplate.id.desc()).all()
    data = []
    for row in rows:
        data.append({
            "id": row.id,
            "category": row.category,
            "title": row.title,
            "content": row.content,
            "updated_at": _format_local_dt(row.updated_at, "%Y-%m-%d %H:%M:%S"),
            "created_at": _format_local_dt(row.created_at, "%Y-%m-%d %H:%M:%S"),
        })
    return jsonify({"data": data}), 200

@bp.route('/doctor/templates', methods=['POST'])
@jwt_required()
@role_required('doctor')
def create_text_template():
    user_id = get_jwt_identity()
    try:
        doctor_id = int(user_id)
    except (ValueError, TypeError):
        return jsonify({"msg": "Invalid user identity"}), 401

    data = request.get_json(silent=True) or {}
    category = (data.get('category') or '').strip()
    if category not in _TEXT_TEMPLATE_CATEGORIES:
        return jsonify({"msg": "Invalid category"}), 400

    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    if not title:
        return jsonify({"msg": "Missing required field: title", "field": "title"}), 400
    if not content:
        return jsonify({"msg": "Missing required field: content", "field": "content"}), 400

    tpl = TextTemplate(
        doctor_id=doctor_id,
        category=category,
        title=title,
        content=content,
    )
    db.session.add(tpl)
    db.session.commit()
    return jsonify({"data": {"id": tpl.id}}), 201

@bp.route('/doctor/templates/<int:template_id>', methods=['PUT'])
@jwt_required()
@role_required('doctor')
def update_text_template(template_id):
    user_id = get_jwt_identity()
    try:
        doctor_id = int(user_id)
    except (ValueError, TypeError):
        return jsonify({"msg": "Invalid user identity"}), 401

    tpl = TextTemplate.query.filter_by(id=template_id, doctor_id=doctor_id).first()
    if not tpl:
        return jsonify({"msg": "Template not found"}), 404

    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    if not title:
        return jsonify({"msg": "Missing required field: title", "field": "title"}), 400
    if not content:
        return jsonify({"msg": "Missing required field: content", "field": "content"}), 400

    tpl.title = title
    tpl.content = content
    db.session.commit()
    return jsonify({"msg": "Template updated successfully"}), 200

@bp.route('/doctor/templates/<int:template_id>', methods=['DELETE'])
@jwt_required()
@role_required('doctor')
def delete_text_template(template_id):
    user_id = get_jwt_identity()
    try:
        doctor_id = int(user_id)
    except (ValueError, TypeError):
        return jsonify({"msg": "Invalid user identity"}), 401

    tpl = TextTemplate.query.filter_by(id=template_id, doctor_id=doctor_id).first()
    if not tpl:
        return jsonify({"msg": "Template not found"}), 404

    db.session.delete(tpl)
    db.session.commit()
    return jsonify({"msg": "Template deleted successfully"}), 200
