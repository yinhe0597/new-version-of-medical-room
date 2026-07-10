import math

from sqlalchemy import select

from backend.app import db
from backend.app.models import (
    DrugStockGroup,
    InventoryRecord,
    OperationLog,
    Visit,
    INVENTORY_OPERATION_DISPENSE,
    INVENTORY_OPERATION_REVERSAL,
    VISIT_STATUS_REVOKED,
)


def _group_ledger_variant(group):
    if group.retail_drug is not None and int(group.retail_amount or 0) > 0:
        return group.retail_drug, int(group.retail_amount)
    if group.pack_drug is not None and int(group.pack_amount or 0) > 0:
        return group.pack_drug, int(group.pack_amount)
    return None, 0


def backfill_revoked_inventory_movements(logger=None):
    """Create balancing ledger rows for revoked visits from pre-ledger versions."""
    ledger_visit_ids = select(InventoryRecord.visit_id).where(
        InventoryRecord.operation_type == INVENTORY_OPERATION_DISPENSE,
        InventoryRecord.visit_id.isnot(None),
    )
    visits = Visit.query.filter(
        Visit.status == VISIT_STATUS_REVOKED,
        Visit.revoked_at.isnot(None),
        ~Visit.id.in_(ledger_visit_ids),
    ).all()
    created = 0

    execution_logs = {}
    visit_ids = [visit.id for visit in visits]
    if visit_ids:
        logs = OperationLog.query.filter(
            OperationLog.action_type == "nurse_execute",
            OperationLog.target_type == "visit",
            OperationLog.target_id.in_(visit_ids),
        ).order_by(OperationLog.timestamp.asc(), OperationLog.id.asc()).all()
        for log in logs:
            execution_logs.setdefault(log.target_id, log)

    for visit in visits:
        ordinary = {}
        grouped = {}
        invalid = False
        for item in list(visit.items or []):
            drug = item.drug
            if drug is None or (drug.type not in (1, 3) and drug.type is not None):
                continue
            quantity = int(item.quantity or 0)
            if quantity <= 0:
                continue
            if drug.stock_group_code:
                unit_amount = int(drug.unit_amount or 0)
                if unit_amount <= 0:
                    invalid = True
                    break
                grouped[drug.stock_group_code] = (
                    grouped.get(drug.stock_group_code, 0) + quantity * unit_amount
                )
            else:
                deduction = math.ceil(quantity / int(drug.conversion_rate or 1)) if item.is_scattered else quantity
                current = ordinary.get(drug.id)
                if current is None:
                    ordinary[drug.id] = [drug, int(deduction)]
                else:
                    current[1] += int(deduction)

        if invalid:
            if logger:
                logger.warning("Skipped revoked ledger backfill for visit %s: invalid unit amount", visit.id)
            continue

        execution_log = execution_logs.get(visit.id)
        original_time = (
            execution_log.timestamp if execution_log and execution_log.timestamp
            else visit.verified_at or visit.timestamp
        )
        original_nurse = (
            execution_log.user_id if execution_log and execution_log.user_id
            else visit.verified_by or visit.revoked_by
        )
        reversal_nurse = visit.revoked_by or original_nurse
        pending = []
        for drug, deduction in ordinary.values():
            pending.extend([
                InventoryRecord(
                    drug_id=drug.id,
                    nurse_id=original_nurse,
                    visit_id=visit.id,
                    old_stock=deduction,
                    new_stock=0,
                    operation_type=INVENTORY_OPERATION_DISPENSE,
                    remark=f"历史撤销交易出库补记: visit={visit.id}",
                    timestamp=original_time,
                ),
                InventoryRecord(
                    drug_id=drug.id,
                    nurse_id=reversal_nurse,
                    visit_id=visit.id,
                    old_stock=0,
                    new_stock=deduction,
                    operation_type=INVENTORY_OPERATION_REVERSAL,
                    remark=f"历史撤销交易返库补记: visit={visit.id}",
                    timestamp=visit.revoked_at,
                ),
            ])

        for group_code, base_units in grouped.items():
            group = DrugStockGroup.query.filter_by(group_code=group_code).first()
            primary_drug, primary_amount = _group_ledger_variant(group) if group else (None, 0)
            if primary_drug is None or primary_amount <= 0 or base_units % primary_amount != 0:
                invalid = True
                break
            quantity = base_units // primary_amount
            pending.extend([
                InventoryRecord(
                    drug_id=primary_drug.id,
                    nurse_id=original_nurse,
                    visit_id=visit.id,
                    old_stock=quantity,
                    new_stock=0,
                    operation_type=INVENTORY_OPERATION_DISPENSE,
                    remark=f"历史撤销交易出库补记: visit={visit.id}",
                    timestamp=original_time,
                ),
                InventoryRecord(
                    drug_id=primary_drug.id,
                    nurse_id=reversal_nurse,
                    visit_id=visit.id,
                    old_stock=0,
                    new_stock=quantity,
                    operation_type=INVENTORY_OPERATION_REVERSAL,
                    remark=f"历史撤销交易返库补记: visit={visit.id}",
                    timestamp=visit.revoked_at,
                ),
            ])

        if invalid:
            if logger:
                logger.warning("Skipped revoked ledger backfill for visit %s: invalid stock group", visit.id)
            continue
        db.session.add_all(pending)
        created += len(pending)

    if created:
        db.session.commit()
    return created
