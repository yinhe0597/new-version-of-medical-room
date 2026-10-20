from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_CENT = Decimal("0.01")


def parse_nonnegative_money(value, field="amount"):
    if isinstance(value, bool):
        raise ValueError(field)
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(field)
    if not amount.is_finite() or amount < 0:
        raise ValueError(field)
    try:
        return float(amount.quantize(_CENT, rounding=ROUND_HALF_UP))
    except InvalidOperation:
        raise ValueError(field)
