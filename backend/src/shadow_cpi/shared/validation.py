"""Small validation helpers shared by the models and the ingestion layer."""

from __future__ import annotations

from datetime import UTC, datetime

CIK_LENGTH = 10


def normalize_cik(value: str | int) -> str:
    """Turn a filer identifier into the ten-digit form the SEC uses.

    Filers are identified by a Central Index Key (CIK). The same filer appears in
    the wild as ``1350694``, ``0001350694``, and ``CIK0001350694``. All three mean
    the same company, and storing them as three different strings would split one
    filer's history into three. Normalizing here, once, prevents that.

    Args:
        value: A CIK as an integer or string, with or without leading zeros and
            an optional ``CIK`` prefix.

    Returns:
        The CIK as exactly ten digits.

    Raises:
        ValueError: If the value is empty, non-numeric, or longer than ten digits.

    Example:
        >>> normalize_cik("1350694")
        '0001350694'
        >>> normalize_cik("CIK0001350694")
        '0001350694'
    """
    text = str(value).strip()
    if text.upper().startswith("CIK"):
        text = text[3:].strip()
    if not text.isdigit():
        raise ValueError(f"CIK must contain only digits, got {value!r}")
    if len(text) > CIK_LENGTH:
        raise ValueError(f"CIK cannot be longer than {CIK_LENGTH} digits, got {value!r}")
    return text.zfill(CIK_LENGTH)


def require_utc(value: datetime) -> datetime:
    """Require a timezone-aware timestamp and return it in UTC.

    Time-series data is meaningless if half the rows are in local time and half
    in UTC, and a timestamp without a timezone cannot be interpreted safely on a
    machine in another region. Everything is therefore stored in UTC, and a naive
    timestamp is refused rather than assumed to be UTC.

    Args:
        value: The timestamp to check.

    Returns:
        The same moment in time, expressed in UTC.

    Raises:
        ValueError: If the timestamp has no timezone information.
    """
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("timestamp must include a timezone, for example 2026-08-15T09:00:00Z")
    return value.astimezone(UTC)
