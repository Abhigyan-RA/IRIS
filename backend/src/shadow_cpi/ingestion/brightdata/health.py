"""Deciding whether a collection run produced usable data.

This is the check the whole self-healing story rests on. A broken scraper does not raise;
it returns nothing, or rows with the value missing. Silence, not an error, is the failure
mode, so every run's output is inspected rather than trusted.

The check asks whether the value can actually be found, not whether a field with a
particular name exists. That distinction matters: each Scraper Studio collector defines its
own output schema, so one calls it ``price`` and another ``baltic_dry_index_value``. Judging
by a fixed field name would report a perfectly healthy collector as a changed website.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Without a value there is nothing worth storing, so this is what defines a broken run.
DEFAULT_REQUIRED_FIELDS: tuple[str, ...] = ("price",)


@dataclass(frozen=True, slots=True)
class HealthVerdict:
    """The outcome of inspecting one run's output.

    Attributes:
        is_healthy: Whether the payload can be used.
        reason: Plain-language explanation, written to the health feed and used when
            asking for a repair.
        missing_fields: What was expected but not found. This is what the repair
            instruction is built from.
    """

    is_healthy: bool
    reason: str
    missing_fields: tuple[str, ...]


def _is_present(value: object) -> bool:
    """Whether a collected value actually carries data.

    Collectors commonly return an empty string rather than omitting a field, which would
    otherwise pass a naive presence check.

    Args:
        value: The collected value.

    Returns:
        True when the value is usable.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _value_at(row: Mapping[str, object], path: str) -> object:
    """Read a value from a row by dotted path.

    Args:
        row: One row from a collector.
        path: Dotted path, such as ``price.value``.

    Returns:
        The value, or None when the path does not exist.
    """
    current: object = row
    for part in path.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            return None
    return current


def check_payload(
    rows: Sequence[Mapping[str, object]],
    required_fields: Sequence[str] = DEFAULT_REQUIRED_FIELDS,
) -> HealthVerdict:
    """Inspect a run's output.

    Args:
        rows: Rows the run produced.
        required_fields: Dotted paths where the value may live. A row counts as usable when
            any one of them holds data, because a collector defines its own field names and
            several spellings are tried.

    Returns:
        A verdict describing whether the payload is usable and, if not, what was missing.

    Example:
        >>> check_payload([{"price": "4.52"}]).is_healthy
        True
        >>> rows = [{"baltic_dry_index_value": 2878}]
        >>> check_payload(rows, ("baltic_dry_index_value",)).is_healthy
        True
        >>> check_payload([]).is_healthy
        False
    """
    if not rows:
        return HealthVerdict(
            is_healthy=False,
            reason="no rows returned, which usually means the page layout changed",
            missing_fields=tuple(required_fields),
        )

    usable = [
        row for row in rows if any(_is_present(_value_at(row, path)) for path in required_fields)
    ]
    if not usable:
        names = ", ".join(required_fields)
        return HealthVerdict(
            is_healthy=False,
            reason=f"rows returned, but none carried a value at: {names}",
            missing_fields=tuple(required_fields),
        )

    return HealthVerdict(
        is_healthy=True,
        reason=f"{len(usable)} rows returned with the expected value",
        missing_fields=(),
    )
