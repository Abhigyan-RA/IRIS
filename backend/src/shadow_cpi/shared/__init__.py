"""Types and validation shared across the backend.

Import from this package rather than from the modules inside it, so that internal
files can be reorganised without breaking callers:

    from shadow_cpi.shared import CommodityPrice, Sector
"""

from shadow_cpi.shared.enums import IngestionMethod, PipelineEventType, Sector
from shadow_cpi.shared.models import (
    CommodityPrice,
    InstitutionalHolding,
    PipelineHealthEvent,
)
from shadow_cpi.shared.validation import CIK_LENGTH, normalize_cik, require_utc

__all__ = [
    "CIK_LENGTH",
    "CommodityPrice",
    "IngestionMethod",
    "InstitutionalHolding",
    "PipelineEventType",
    "PipelineHealthEvent",
    "Sector",
    "normalize_cik",
    "require_utc",
]
