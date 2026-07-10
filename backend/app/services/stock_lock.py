from contextlib import contextmanager
from functools import wraps
from threading import RLock

from flask import jsonify
from backend.app import db


_stock_mutation_lock = RLock()


class StockMutationBusy(RuntimeError):
    pass


@contextmanager
def stock_mutation_guard():
    """Serialize stock state transitions across threads and MySQL instances."""
    with _stock_mutation_lock:
        lock_connection = None
        mysql_lock_acquired = False
        if db.engine.dialect.name == "mysql":
            lock_connection = db.engine.connect()
            mysql_lock_acquired = lock_connection.exec_driver_sql(
                "SELECT GET_LOCK('medical_room_stock_mutation', 15)"
            ).scalar() == 1
            if not mysql_lock_acquired:
                lock_connection.close()
                raise StockMutationBusy("stock mutation lock is busy")
        try:
            yield
        finally:
            if mysql_lock_acquired and lock_connection is not None:
                try:
                    lock_connection.exec_driver_sql(
                        "SELECT RELEASE_LOCK('medical_room_stock_mutation')"
                    )
                finally:
                    lock_connection.close()


def serialized_stock_mutation(fn):
    """Serialize stock writes inside one application process."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            with stock_mutation_guard():
                return fn(*args, **kwargs)
        except StockMutationBusy:
            return jsonify({"msg": "库存操作繁忙，请稍后重试"}), 503

    return wrapper


def lock_stock_rows(items):
    """Lock all stock rows used by prescription items in deterministic order."""
    from backend.app.models import Drug, DrugStockGroup

    drug_ids = sorted({item.drug_id for item in items if item.drug_id is not None})
    group_codes = sorted({
        item.drug.stock_group_code
        for item in items
        if item.drug is not None and item.drug.stock_group_code
    })

    if drug_ids:
        (
            db.session.query(Drug)
            .filter(Drug.id.in_(drug_ids))
            .order_by(Drug.id.asc())
            .with_for_update()
            .populate_existing()
            .all()
        )
    if group_codes:
        (
            db.session.query(DrugStockGroup)
            .filter(DrugStockGroup.group_code.in_(group_codes))
            .order_by(DrugStockGroup.group_code.asc())
            .with_for_update()
            .populate_existing()
            .all()
        )
