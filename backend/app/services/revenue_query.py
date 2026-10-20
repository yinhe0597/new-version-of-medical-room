from sqlalchemy import case, func

from backend.app import db
from backend.app.models import Drug, PrescriptionItem


def fetch_revenue_weights(visit_ids):
    """Aggregate prescription amounts by revenue category for each visit.

    The amount expression mirrors ``allocate_payment_revenue``: prefer the
    adjusted amount, clamp negatives to zero, and round each item to cents
    before summing. That keeps historical allocation results stable.
    """
    visit_ids = [visit_id for visit_id in visit_ids if visit_id]
    if not visit_ids:
        return {}

    raw_amount = func.coalesce(PrescriptionItem.new_amount, PrescriptionItem.amount, 0)
    amount = case(
        (raw_amount < 0, 0),
        else_=func.round(raw_amount, 2),
    )
    raw_cost = func.coalesce(PrescriptionItem.purchase_cost, 0)
    cost = case(
        (raw_cost < 0, 0),
        else_=func.round(raw_cost, 2),
    )
    drug_type = func.coalesce(Drug.type, 1)

    rows = (
        db.session.query(
            PrescriptionItem.visit_id.label("visit_id"),
            func.coalesce(
                func.sum(case((drug_type == 1, amount), else_=0)), 0
            ).label("drug"),
            func.coalesce(
                func.sum(
                    case(
                        (drug_type.notin_((1, 3)), amount),
                        else_=0,
                    )
                ),
                0,
            ).label("service"),
            func.coalesce(
                func.sum(case((drug_type == 3, amount), else_=0)), 0
            ).label("consumable"),
            func.coalesce(func.sum(cost), 0).label("cost"),
        )
        .outerjoin(Drug, PrescriptionItem.drug_id == Drug.id)
        .filter(PrescriptionItem.visit_id.in_(visit_ids))
        .group_by(PrescriptionItem.visit_id)
        .all()
    )

    return {
        int(row.visit_id): {
            "drug": row.drug,
            "service": row.service,
            "consumable": row.consumable,
            "cost": row.cost,
        }
        for row in rows
    }
