import math
import re
import uuid


PACK_SPEC_RE = re.compile(r"^\s*(?:.*?[xX×*＊]\s*)?\d+\s*[^\d/\s]+(?:\s*/\s*\S+)?\s*$")
PACK_AMOUNT_RE = re.compile(r"[xX×*＊]\s*(?P<count>\d+)\s*(?P<unit>[^\d/\s]+)\s*/\s*(?P<pack_unit>\S+)\s*$")
PACK_SIMPLE_RE = re.compile(r"^\s*(?P<count>\d+)\s*(?P<unit>[^\d/\s]+)\s*/\s*(?P<pack_unit>\S+)\s*$")
PACK_NOSLASH_RE = re.compile(r"^\s*(?:.*?[xX×*＊]\s*)?(?P<count>\d+)\s*(?P<unit>[^\d/\s]+)\s*$")
MIN_UNIT_RE = re.compile(r"^\s*(?P<count>\d+)\s*(?P<unit>[^\d\s]+)\s*$")


class ValidationError(Exception):
    def __init__(self, message, field=None, item_index=None):
        super().__init__(message)
        self.message = message
        self.field = field
        self.item_index = item_index


def validate_pack_spec(spec_text):
    if not spec_text or not str(spec_text).strip():
        raise ValidationError("Missing pack_specification", field="pack_specification")
    s = str(spec_text).strip()
    if not PACK_SPEC_RE.match(s):
        raise ValidationError(
            "整份规格格式不正确（示例：20mg×100粒/瓶 或 100粒/瓶 或 100粒）",
            field="pack_specification",
        )

    m = PACK_AMOUNT_RE.search(s)
    if not m:
        m = PACK_SIMPLE_RE.match(s)
    if not m:
        m = PACK_NOSLASH_RE.match(s)
        if not m:
            raise ValidationError(
                "无法解析整份规格中的包装量（示例：20mg×100粒/瓶 或 100粒/瓶 或 100粒）",
                field="pack_specification",
            )

    pack_amount = int(m.group("count"))
    unit_name = str(m.group("unit")).strip()
    pack_unit = str(m.groupdict().get("pack_unit") or "").strip() or "盒"

    if pack_amount <= 0:
        raise ValidationError("Invalid pack amount", field="pack_specification")
    if not unit_name:
        raise ValidationError("Invalid unit in pack_specification", field="pack_specification")
    if not pack_unit:
        raise ValidationError("Invalid pack unit in pack_specification", field="pack_specification")

    return {
        "pack_amount": pack_amount,
        "unit_name": unit_name,
        "pack_unit": pack_unit,
    }


def parse_min_sale_unit(min_sale_unit_text):
    if not min_sale_unit_text or not str(min_sale_unit_text).strip():
        raise ValidationError("Missing min_sale_unit", field="min_sale_unit")
    m = MIN_UNIT_RE.match(str(min_sale_unit_text).strip())
    if not m:
        raise ValidationError("Invalid min_sale_unit format", field="min_sale_unit")
    count = int(m.group("count"))
    unit_name = str(m.group("unit")).strip()
    if count <= 0 or not unit_name:
        raise ValidationError("Invalid min_sale_unit", field="min_sale_unit")
    return {"min_sale_amount": count, "unit_name": unit_name}


def validate_prices(pack_price, min_sale_price, pack_amount, min_sale_amount):
    try:
        pack_price_val = float(pack_price)
    except Exception:
        raise ValidationError("Invalid pack_price", field="pack_price")
    if pack_price_val <= 0:
        raise ValidationError("pack_price must be > 0", field="pack_price")

    if min_sale_price is None:
        return {"pack_price": pack_price_val, "min_sale_price": None, "threshold": None}

    try:
        min_sale_price_val = float(min_sale_price)
    except Exception:
        raise ValidationError("Invalid min_sale_price", field="min_sale_price")
    if min_sale_price_val <= 0:
        raise ValidationError("min_sale_price must be > 0", field="min_sale_price")

    if pack_amount <= 0 or min_sale_amount <= 0:
        raise ValidationError("Invalid pack/min_sale amounts", field="min_sale_unit")

    if pack_amount % min_sale_amount != 0:
        raise ValidationError("pack_amount must be divisible by min_sale_amount", field="min_sale_unit")

    threshold = pack_price_val * (min_sale_amount / pack_amount)
    if min_sale_price_val <= threshold:
        raise ValidationError("min_sale_price too low", field="min_sale_price")

    return {"pack_price": pack_price_val, "min_sale_price": min_sale_price_val, "threshold": threshold}


def compute_initial_stocks(inbound_packs, pack_amount, min_sale_amount=None):
    try:
        packs = int(inbound_packs)
    except Exception:
        raise ValidationError("Invalid inbound_quantity", field="inbound_quantity")
    if packs <= 0:
        raise ValidationError("inbound_quantity must be > 0", field="inbound_quantity")

    total_units = packs * int(pack_amount)
    if min_sale_amount is None:
        return {"packs": packs, "retail_units": None, "total_units": total_units}

    retail_units = total_units // int(min_sale_amount)
    return {"packs": packs, "retail_units": retail_units, "total_units": total_units}


def new_group_code():
    return str(uuid.uuid4())


def recompute_variant_stocks(total_units, pack_amount, retail_amount=None):
    pack_stock = int(total_units) // int(pack_amount)
    if retail_amount is None:
        return {"pack_stock": pack_stock, "retail_stock": None}
    retail_stock = int(total_units) // int(retail_amount)
    return {"pack_stock": pack_stock, "retail_stock": retail_stock}


def compute_deduct_units(quantity, unit_amount):
    return int(quantity) * int(unit_amount)

