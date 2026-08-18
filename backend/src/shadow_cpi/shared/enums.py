"""The vocabulary of the system: sectors, ingestion methods, and event types.

These are small, closed sets. Keeping them as enums rather than loose strings
means a typo fails immediately at the boundary instead of quietly creating a
second spelling of "metals" that no query will ever match.
"""

from __future__ import annotations

from enum import StrEnum


class Sector(StrEnum):
    """The four categories of price data this platform tracks."""

    FREIGHT = "freight"
    ENERGY = "energy"
    METALS = "metals"
    AGRICULTURE = "agriculture"


class IngestionMethod(StrEnum):
    """How a record was obtained.

    Stored with every price so that any number on the dashboard can be traced
    back to how it was collected, not just where it came from.
    """

    OFFICIAL_API = "official_api"
    BRIGHTDATA_SCRAPE = "brightdata_scrape"


class PipelineEventType(StrEnum):
    """Stages in the life of a collector run.

    A healthy run records ``SUCCESS``. A run that failed for an ordinary reason, such as
    a source being unreachable or unconfigured, records ``COLLECTION_FAILED``.

    When a website changes its layout the sequence is ``DOM_SHIFT_DETECTED``, then
    ``SELF_HEAL_TRIGGERED``, then either ``SELF_HEAL_RESOLVED`` or ``SELF_HEAL_FAILED``.
    Those four are reserved for that path, so that a plain outage is never mistaken for
    a site redesign.
    """

    SUCCESS = "success"
    COLLECTION_FAILED = "collection_failed"
    DOM_SHIFT_DETECTED = "dom_shift_detected"
    SELF_HEAL_TRIGGERED = "self_heal_triggered"
    SELF_HEAL_RESOLVED = "self_heal_resolved"
    SELF_HEAL_FAILED = "self_heal_failed"
