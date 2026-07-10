from sqlalchemy import case


def nulls_last_asc(column):
    """Return portable ascending order clauses with null values last."""
    return (
        case((column.is_(None), 1), else_=0).asc(),
        column.asc(),
    )
