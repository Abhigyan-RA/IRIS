"""Where a tracked price applies, and how fresh it is expected to be.

Both are presentation facts rather than measurements, so they live here as small
declared tables instead of being inferred:

- The map needs a region for each tracked entity. The price records themselves have
  no region, because a spot price is a number rather than a place, so the mapping is
  declared. Anything unmapped is shown as global, which is true of most benchmarks.
- Each category publishes at a different cadence, so "out of date" means something
  different per category. A price older than its target is labelled stale in the
  response. A visibly stale number is safe to show; a silently stale one is not.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from shadow_cpi.shared import Sector

DEFAULT_REGION = "Global"

# Region each tracked entity belongs to. Extend as entities are added.
ENTITY_REGIONS: dict[str, str] = {
    "Steel_HRC_US": "North America",
    "WTI_Crude": "North America",
    "WTI_Crude_Delayed": "North America",
    "Natural_Gas": "North America",
    "Wheat": "North America",
    "Corn": "North America",
    "Soybeans": "North America",
    "Brent_Crude": "Europe",
    "Gold": "Global",
    "Aluminum": "Global",
    "Copper": "Global",
    "FBX_Global": "Global",
    "Baltic_Dry_Index": "Global",
    # China outbound lanes
    "FBX01_China_to_North_America_West_Coast": "Asia Pacific",
    "FBX03_China_to_North_America_East_Coast": "Asia Pacific",
    "FBX11_China_to_Northern_Europe": "Asia Pacific",
    "FBX13_China_to_Mediterranean": "Asia Pacific",
    # Return lanes to China
    "FBX02_North_America_West_Coast_to_China": "North America",
    "FBX04_North_America_East_Coast_to_China": "North America",
    "FBX12_Northern_Europe_to_China": "Europe",
    "FBX14_Mediterranean_to_China": "Europe",
    # Trans-Atlantic lanes
    "FBX21_North_America_East_Coast_to_Northern_Europe": "North America",
    "FBX22_Northern_Europe_to_North_American_East_Coast": "Europe",
    # South America lanes
    "FBX24_Europe_to_South_America_East_Coast": "South America",
    "FBX26_Europe_to_South_America_West_Coast": "South America",
}

# How old a price may be before it is labelled stale, by category. Freight and
# energy move intraday; crop reports are daily; disclosures are quarterly.
FRESHNESS_TARGETS: dict[Sector, timedelta] = {
    Sector.FREIGHT: timedelta(hours=6),
    Sector.ENERGY: timedelta(hours=6),
    Sector.METALS: timedelta(hours=6),
    Sector.AGRICULTURE: timedelta(hours=24),
}

_FALLBACK_TARGET = timedelta(hours=24)


def region_for(entity_name: str) -> str:
    """Return the region a tracked entity belongs to.

    Args:
        entity_name: Entity as stored, for example ``Steel_HRC_US``.

    Returns:
        The region, or ``Global`` when the entity is not tied to one place.
    """
    return ENTITY_REGIONS.get(entity_name, DEFAULT_REGION)


def is_stale(sector: Sector, recorded_at: datetime, now: datetime) -> bool:
    """Whether a price is older than its category's freshness target.

    Args:
        sector: Category the price belongs to.
        recorded_at: When the price was observed.
        now: The current time, passed in so this stays testable.

    Returns:
        True when the price is older than its target.
    """
    target = FRESHNESS_TARGETS.get(sector, _FALLBACK_TARGET)
    return (now - recorded_at) > target
