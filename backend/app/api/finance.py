from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.app import db
from backend.app.api import bp
from backend.app.models import Payment, Visit, PrescriptionItem, Drug, User, OperationLog
from backend.app.utils.decorators import role_required
from datetime import datetime, date, timedelta
from sqlalchemy import func

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


@bp.route('/finance/dashboard/summary', methods=['GET'])
@role_required(['admin', 'finance'])
def finance_dashboard_summary():
    """财务看板：聚合指标数据"""
    from datetime import time

    now = datetime.now()
    today_start = datetime.combine(now.date(), time.min)
    today_end = today_start + timedelta(days=1)

    month_start = datetime(now.year, now.month, 1)
    if now.month == 12:
        month_end = datetime(now.year + 1, 1, 1)
    else:
        month_end = datetime(now.year, now.month + 1, 1)

    # 上月同期
    prev_month = now.month - 1
    prev_year = now.year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1
    prev_month_start = datetime(prev_year, prev_month, 1)
    if prev_month == 12:
        prev_month_end = datetime(prev_year + 1, 1, 1)
    else:
        prev_month_end = datetime(prev_year, prev_month + 1, 1)

    # 今日营收
    today_revenue = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.payment_date >= today_start,
        Payment.payment_date < today_end
    ).scalar() or 0.0

    # 本月营收
    month_revenue = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.payment_date >= month_start,
        Payment.payment_date < month_end
    ).scalar() or 0.0

    # 本月成本
    month_cost = db.session.query(func.coalesce(func.sum(PrescriptionItem.purchase_cost), 0)).filter(
        PrescriptionItem.visit_id.in_(db.select(Payment.visit_id).where(
            Payment.payment_date >= month_start,
            Payment.payment_date < month_end
        ))
    ).scalar() or 0.0

    month_profit = month_revenue - month_cost

    # 上月营收
    prev_month_revenue = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.payment_date >= prev_month_start,
        Payment.payment_date < prev_month_end
    ).scalar() or 0.0

    # 本月就诊人次
    month_visit_count = db.session.query(func.count(func.distinct(Payment.visit_id))).filter(
        Payment.payment_date >= month_start,
        Payment.payment_date < month_end
    ).scalar() or 0

    # 增长率
    if prev_month_revenue > 0:
        growth_rate = round((month_revenue - prev_month_revenue) / prev_month_revenue * 100, 2)
    else:
        growth_rate = 0.0

    return jsonify({
        "data": {
            "today_revenue": round(today_revenue, 2),
            "month_revenue": round(month_revenue, 2),
            "month_cost": round(month_cost, 2),
            "month_profit": round(month_profit, 2),
            "prev_month_revenue": round(prev_month_revenue, 2),
            "growth_rate": growth_rate,
            "month_visit_count": month_visit_count,
        }
    }), 200


@bp.route('/finance/profit-trend', methods=['GET'])
@role_required(['admin', 'finance'])
def finance_profit_trend():
    """近N天营收/成本/利润趋势"""
    days = request.args.get('days', 30, type=int)
    if days < 1:
        days = 1
    if days > 365:
        days = 365

    now = datetime.now()
    start_date = datetime.combine((now - timedelta(days=days - 1)).date(), datetime.min.time())

    # 按天分组聚合
    results = db.session.query(
        func.date(Payment.payment_date).label('day'),
        func.coalesce(func.sum(Payment.amount), 0).label('revenue'),
        func.count(func.distinct(Payment.visit_id)).label('visit_count'),
    ).filter(
        Payment.payment_date >= start_date,
        Payment.payment_date < now
    ).group_by(
        func.date(Payment.payment_date)
    ).order_by(
        func.date(Payment.payment_date)
    ).all()

    # 构建按天索引
    revenue_by_day = {}
    cost_by_day = {}
    visit_by_day = {}
    for r in results:
        day_str = r.day
        revenue_by_day[day_str] = float(r.revenue or 0)
        visit_by_day[day_str] = int(r.visit_count or 0)

    # 计算每天的成本
    if results:
        day_ranges = [(r.day, r.day) for r in results]
        for day_str, _ in day_ranges:
            day_start = datetime.strptime(day_str, '%Y-%m-%d')
            day_end = day_start + timedelta(days=1)
            visit_ids = db.session.query(Payment.visit_id).filter(
                Payment.payment_date >= day_start,
                Payment.payment_date < day_end
            ).subquery()
            cost = db.session.query(func.coalesce(func.sum(PrescriptionItem.purchase_cost), 0)).filter(
                PrescriptionItem.visit_id.in_(visit_ids)
            ).scalar() or 0.0
            cost_by_day[day_str] = float(cost)

    trend = []
    for i in range(days):
        d = (start_date + timedelta(days=i)).date()
        day_str = d.strftime('%Y-%m-%d')
        rev = revenue_by_day.get(day_str, 0.0)
        cost = cost_by_day.get(day_str, 0.0)
        trend.append({
            "date": day_str,
            "revenue": round(rev, 2),
            "cost": round(cost, 2),
            "profit": round(rev - cost, 2),
            "visit_count": visit_by_day.get(day_str, 0),
        })

    return jsonify({"data": trend}), 200


@bp.route('/finance/revenue/by-type', methods=['GET'])
@role_required(['admin', 'finance'])
def finance_revenue_by_type():
    """按收入类型统计（药品/诊疗/耗材/诊察费）"""
    start_time_str = request.args.get('start_time')
    end_time_str = request.args.get('end_time')
    now = datetime.now()

    if start_time_str or end_time_str:
        start = parse_dt(start_time_str, is_end=False) if start_time_str else None
        end = parse_dt(end_time_str, is_end=True) if end_time_str else None
        if start is None:
            start = datetime.combine((now - timedelta(days=30)).date(), datetime.min.time())
        if end is None:
            end = now
    else:
        start = datetime.combine((now - timedelta(days=30)).date(), datetime.min.time())
        end = now

    payments = Payment.query.filter(
        Payment.payment_date >= start,
        Payment.payment_date < end
    ).all()

    drug_revenue = 0.0
    service_revenue = 0.0
    consumable_revenue = 0.0
    consultation_revenue = 0.0

    visit_ids = [p.visit_id for p in payments if p.visit_id]
    items_by_visit = {}
    if visit_ids:
        items = PrescriptionItem.query.options(
            db.joinedload(PrescriptionItem.drug)
        ).filter(PrescriptionItem.visit_id.in_(visit_ids)).all()
        for it in items:
            items_by_visit.setdefault(it.visit_id, []).append(it)

    for p in payments:
        v = Visit.query.get(p.visit_id)
        if v is None:
            continue
        consultation_revenue += float(v.consultation_fee or 0.0)
        for it in items_by_visit.get(v.id, []):
            amount_val = it.new_amount if it.new_amount is not None else it.amount
            amount_val = float(amount_val or 0.0)
            d = getattr(it, "drug", None)
            drug_type = int(getattr(d, "type", 1) or 1)
            if drug_type == 1:
                drug_revenue += amount_val
            elif drug_type == 3:
                consumable_revenue += amount_val
            else:
                service_revenue += amount_val

    return jsonify({
        "data": {
            "drug_revenue": round(drug_revenue, 2),
            "service_revenue": round(service_revenue, 2),
            "consumable_revenue": round(consumable_revenue, 2),
            "consultation_revenue": round(consultation_revenue, 2),
            "total": round(drug_revenue + service_revenue + consumable_revenue + consultation_revenue, 2),
            "range": {
                "start": start.strftime("%Y-%m-%d %H:%M:%S"),
                "end": (end - timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S"),
            }
        }
    }), 200
