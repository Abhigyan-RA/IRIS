"""Helpers shared by the source modules."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Percentage changes are stored with three decimal places, matching the column.
_PERCENT_PRECISION = Decimal("0.001")


def percent_change(current: Decimal, previous: Decimal) -> Decimal | None:
    """Return the percentage change between two prices.

    Args:
        current: The newer price.
        previous: The older price to compare against.

    Returns:
        The change in percent, rounded to three decimal places, or None when the
        earlier price is zero and a percentage would be meaningless.

    Example:
        >>> percent_change(Decimal("110"), Decimal("100"))
        Decimal('10.000')
    """
    if previous == 0:
        return None
    try:
        change = (current - previous) / previous * Decimal(100)
    except (InvalidOperation, ZeroDivisionError):  # pragma: no cover - guarded above
        return None
    return change.quantize(_PERCENT_PRECISION, rounding=ROUND_HALF_UP)
