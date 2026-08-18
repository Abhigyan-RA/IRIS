"""Price endpoints: the risk map and one entity's trend.

The risk map is the landing view: it answers "what changed" before anyone asks a
question. The trend endpoint backs the drill-down chart for a single entity.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from shadow_cpi.api.dependencies import require_prices
from shadow_cpi.api.freshness import is_stale, region_for
from shadow_cpi.db.protocols import PriceReader
from shadow_cpi.shared import CommodityPrice, Sector

# A month of history is the default chart window. The upper bound stops one
# request asking for years of data and tying up the database.
_DEFAULT_TREND_DAYS = 30
_MAX_TREND_DAYS = 365

_PERCENT_PRECISION = Decimal("0.001")

router = APIRouter(prefix="/api", tags=["prices"])


class RiskMapEntry(BaseModel):
    """One tracked entity as shown on the map.

    Attributes:
        entity_name: What was priced.
        region: Where it applies, or ``Global``.
        sector: Which category it belongs to.
        price: Most recent price.
        currency: Currency of the price.
        unit: What one unit refers to.
        pct_change_1d: Change since the previous published price, in percent.
        pct_change_7d: Change over the past week, in percent.
        recorded_at: When the price was observed.
        source_name: Where it came from.
        source_url: Exact page or endpoint it came from.
        ingestion_method: Whether it came from an official API or a scrape.
        is_stale: Whether the price is older than its category's freshness target.
    """

    entity_name: str
    region: str
    sector: Sector
    price: Decimal
    currency: str
    unit: str
    pct_change_1d: Decimal | None
    pct_change_7d: Decimal | None
    recorded_at: datetime
    source_name: str
    source_url: str
    ingestion_method: str
    is_stale: bool


class RiskMapSector(BaseModel):
    """One category's entries.

    Attributes:
        sector: The category.
        entries: Its entities, largest move first.
    """

    sector: Sector
    entries: list[RiskMapEntry]


class RiskMapResponse(BaseModel):
    """The whole map.

    Attributes:
        generated_at: When this response was assembled.
        sectors: Categories that have data. A category with nothing recorded is
            omitted rather than shown empty.
    """

    generated_at: datetime
    sectors: list[RiskMapSector]


class TrendPoint(BaseModel):
    """One point on a trend chart.

    Attributes:
        recorded_at: When the price was observed.
        price: The price.
    """

    recorded_at: datetime
    price: Decimal


class TrendResponse(BaseModel):
    """Price history for one entity.

    Attributes:
        entity_name: What was priced.
        sector: Which category it belongs to.
        currency: Currency of the prices.
        unit: What one unit refers to.
        days: Length of the window requested.
        points: The observations, oldest first.
        change_pct_over_window: Change from the first to the last observation, or
            None when there is only one observation.
        latest_price: The most recent price in the window.
        source_name: Where the newest price came from.
        source_url: Exact page or endpoint it came from.
    """

    entity_name: str
    sector: Sector
    currency: str
    unit: str
    days: int
    points: list[TrendPoint]
    change_pct_over_window: Decimal | None
    latest_price: Decimal
    source_name: str
    source_url: str


def _to_entry(price: CommodityPrice, now: datetime) -> RiskMapEntry:
    """Convert a stored price into a map entry.

    Args:
        price: The stored price.
        now: Current time, used to judge staleness.

    Returns:
        The entry as the map renders it.
    """
    return RiskMapEntry(
        entity_name=price.entity_name,
        region=region_for(price.entity_name),
        sector=price.sector,
        price=price.price,
        currency=price.currency,
        unit=price.unit,
        pct_change_1d=price.pct_change_1d,
        pct_change_7d=price.pct_change_7d,
        recorded_at=price.recorded_at,
        source_name=price.source_name,
        source_url=price.source_url,
        ingestion_method=price.ingestion_method.value,
        is_stale=is_stale(price.sector, price.recorded_at, now),
    )


def _move_size(entry: RiskMapEntry) -> Decimal:
    """Return how far an entity moved, ignoring direction.

    Entities with no reported change sort last: an unknown move is not a small
    move, but it is not news either.

    Args:
        entry: The entry to measure.

    Returns:
        The absolute daily change, or zero when none was reported.
    """
    return abs(entry.pct_change_1d) if entry.pct_change_1d is not None else Decimal(0)


@router.get("/risk-map", response_model=RiskMapResponse, summary="Live cost spikes by sector")
async def read_risk_map(
    prices: Annotated[PriceReader, Depends(require_prices)],
) -> RiskMapResponse:
    """Return the newest price for every tracked entity, grouped by category.

    Args:
        prices: Price store to read from.

    Returns:
        The map, with the largest mover first in each category.
    """
    now = datetime.now(UTC)
    groups: list[RiskMapSector] = []

    for sector in Sector:
        latest = await prices.latest_prices_by_sector(sector)
        if not latest:
            continue
        entries = sorted(
            (_to_entry(price, now) for price in latest),
            key=_move_size,
            reverse=True,
        )
        groups.append(RiskMapSector(sector=sector, entries=entries))

    return RiskMapResponse(generated_at=now, sectors=groups)


@router.get(
    "/commodities/{entity_name}/trend",
    response_model=TrendResponse,
    summary="Price history for one entity",
)
async def read_trend(
    prices: Annotated[PriceReader, Depends(require_prices)],
    entity_name: Annotated[str, Path(min_length=1, max_length=255)],
    days: Annotated[int, Query(ge=1, le=_MAX_TREND_DAYS)] = _DEFAULT_TREND_DAYS,
) -> TrendResponse:
    """Return recent price history for one entity.

    Args:
        prices: Price store to read from.
        entity_name: Entity to look up.
        days: How many days of history to return.

    Returns:
        The observations, oldest first, with the change across the window.

    Raises:
        HTTPException: If nothing has ever been recorded for the entity.
    """
    history = await prices.price_history(entity_name, days)
    if not history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No price history recorded for {entity_name!r}",
        )

    newest = history[-1]
    oldest = history[0]
    change = None
    if len(history) > 1 and oldest.price != 0:
        change = ((newest.price - oldest.price) / oldest.price * Decimal(100)).quantize(
            _PERCENT_PRECISION, rounding=ROUND_HALF_UP
        )

    return TrendResponse(
        entity_name=newest.entity_name,
        sector=newest.sector,
        currency=newest.currency,
        unit=newest.unit,
        days=days,
        points=[TrendPoint(recorded_at=price.recorded_at, price=price.price) for price in history],
        change_pct_over_window=change,
        latest_price=newest.price,
        source_name=newest.source_name,
        source_url=newest.source_url,
    )
