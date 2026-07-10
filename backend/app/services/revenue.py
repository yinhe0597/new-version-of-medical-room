from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


CENT = Decimal("0.01")
REVENUE_KEYS = ("consultation", "drug", "service", "consumable")


def _decimal(value):
    try:
        result = Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    return result if result.is_finite() else Decimal("0")


def _money(value):
    return _decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _allocate(total, weights, keys):
    total = _money(total)
    positive_weights = {key: max(_decimal(weights.get(key)), Decimal("0")) for key in keys}
    weight_total = sum(positive_weights.values(), Decimal("0"))
    result = {key: Decimal("0") for key in keys}
    if total == 0 or weight_total == 0:
        return result

    for key in keys:
        result[key] = (total * positive_weights[key] / weight_total).quantize(
            CENT, rounding=ROUND_HALF_UP
        )

    residual = total - sum(result.values(), Decimal("0"))
    if residual:
        target = max(keys, key=lambda key: positive_weights[key])
        result[target] += residual
    return result


def allocate_payment_revenue(payment, visit, items):
    """Return an actual-revenue breakdown that always reconciles to Payment.amount."""
    original = {key: Decimal("0") for key in REVENUE_KEYS}
    original["consultation"] = max(_money(getattr(visit, "consultation_fee", 0)), Decimal("0"))
    cost = Decimal("0")

    for item in items:
        amount = item.new_amount if item.new_amount is not None else item.amount
        amount = max(_money(amount), Decimal("0"))
        drug = getattr(item, "drug", None)
        drug_type = int(getattr(drug, "type", 1) or 1)
        if drug_type == 1:
            original["drug"] += amount
        elif drug_type == 3:
            original["consumable"] += amount
        else:
            original["service"] += amount
        cost += max(_money(getattr(item, "purchase_cost", 0)), Decimal("0"))

    actual_total = max(_money(getattr(payment, "amount", 0)), Decimal("0"))
    explicit_consult = getattr(payment, "actual_consultation_fee", None)
    explicit_items = getattr(payment, "actual_drug_amount", None)

    if explicit_consult is not None and explicit_items is not None:
        consultation = max(_money(explicit_consult), Decimal("0"))
        item_total = max(_money(explicit_items), Decimal("0"))
        if abs((consultation + item_total) - actual_total) <= CENT:
            actual = {key: Decimal("0") for key in REVENUE_KEYS}
            actual["consultation"] = consultation
            actual.update(_allocate(
                item_total,
                original,
                ("drug", "service", "consumable"),
            ))
        else:
            actual = _allocate(actual_total, original, REVENUE_KEYS)
    else:
        actual = _allocate(actual_total, original, REVENUE_KEYS)

    # A zero-weight historical record still needs to reconcile to its payment.
    if actual_total and not any(actual.values()):
        actual["drug"] = actual_total
    residual = actual_total - sum(actual.values(), Decimal("0"))
    if residual:
        target = max(REVENUE_KEYS, key=lambda key: original[key])
        if not original[target]:
            target = "drug"
        actual[target] += residual

    return {
        "consultation": float(actual["consultation"]),
        "drug": float(actual["drug"]),
        "service": float(actual["service"]),
        "consumable": float(actual["consumable"]),
        "total": float(actual_total),
        "cost": float(cost),
        "profit": float(actual_total - cost),
        "original_total": float(sum(original.values(), Decimal("0"))),
    }
