"""Reading and writing TimescaleDB rows.

Each class here does one job: turn domain records into SQL, and turn SQL rows
back into domain records. No business rules live in this layer, and no SQL lives
outside it.

Three conventions apply throughout:

- Values are always bound as parameters (``%s``), never formatted into the
  statement. This is the difference between a query and an injection.
- Writes are upserts keyed on the natural key, so re-running a collector updates
  the row it wrote last time instead of creating a near-duplicate.
- Rows are converted back into validated models, so a malformed row in the
  database surfaces as a clear validation error rather than spreading further.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from shadow_cpi.db.protocols import BulkExecutor, Row, SqlExecutor
from shadow_cpi.shared import (
    CommodityPrice,
    InstitutionalHolding,
    PipelineHealthEvent,
    Sector,
    normalize_cik,
)

_PRICE_COLUMNS = (
    "entity_name, sector, price, currency, unit, pct_change_1d, pct_change_7d, "
    "recorded_at, source_name, source_url, ingestion_method"
)

_UPSERT_PRICE = f"""
INSERT INTO commodity_prices ({_PRICE_COLUMNS})
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (entity_name, recorded_at) DO UPDATE SET
    sector = EXCLUDED.sector,
    price = EXCLUDED.price,
    currency = EXCLUDED.currency,
    unit = EXCLUDED.unit,
    pct_change_1d = EXCLUDED.pct_change_1d,
    pct_change_7d = EXCLUDED.pct_change_7d,
    source_name = EXCLUDED.source_name,
    source_url = EXCLUDED.source_url,
    ingestion_method = EXCLUDED.ingestion_method
"""

_SELECT_LATEST_PRICE = f"""
SELECT {_PRICE_COLUMNS}
FROM commodity_prices
WHERE entity_name = %s
ORDER BY recorded_at DESC
LIMIT 1
"""

# make_interval keeps the window a bound parameter. Interpolating "30 days" into
# the statement would put caller input into SQL text.
_SELECT_PRICE_HISTORY = f"""
SELECT {_PRICE_COLUMNS}
FROM commodity_prices
WHERE entity_name = %s
  AND recorded_at >= now() - make_interval(days => %s)
ORDER BY recorded_at ASC
"""

# DISTINCT ON returns the first row of each entity group, which combined with the
# ORDER BY gives the newest price per entity in one pass.
_SELECT_LATEST_BY_SECTOR = f"""
SELECT DISTINCT ON (entity_name) {_PRICE_COLUMNS}
FROM commodity_prices
WHERE sector = %s
ORDER BY entity_name, recorded_at DESC
"""

_HOLDING_COLUMNS = (
    "filer_name, filer_cik, stock_ticker, shares_held, market_value_usd, "
    "pct_portfolio, shares_change_qoq, quarter_end, source_url"
)

# Ordering puts the newest quarter first, then the largest position, so the most
# relevant line is the first one a reader sees.
_HOLDINGS_ORDER = " ORDER BY quarter_end DESC, market_value_usd DESC NULLS LAST"

# Both query variants are spelled out rather than assembled at call time: the
# statement text is then a fixed constant, and only values are ever bound.
_SELECT_HOLDERS = (
    f"SELECT {_HOLDING_COLUMNS} FROM institutional_holdings WHERE stock_ticker = %s"
    f"{_HOLDINGS_ORDER}"
)
_SELECT_HOLDERS_FOR_QUARTER = (
    f"SELECT {_HOLDING_COLUMNS} FROM institutional_holdings "
    f"WHERE stock_ticker = %s AND quarter_end = %s{_HOLDINGS_ORDER}"
)
_SELECT_FILER_HOLDINGS = (
    f"SELECT {_HOLDING_COLUMNS} FROM institutional_holdings WHERE filer_cik = %s"
    f"{_HOLDINGS_ORDER}"
)
_SELECT_FILER_HOLDINGS_FOR_QUARTER = (
    f"SELECT {_HOLDING_COLUMNS} FROM institutional_holdings "
    f"WHERE filer_cik = %s AND quarter_end = %s{_HOLDINGS_ORDER}"
)

_UPSERT_HOLDING = f"""
INSERT INTO institutional_holdings ({_HOLDING_COLUMNS})
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (filer_cik, stock_ticker, quarter_end) DO UPDATE SET
    filer_name = EXCLUDED.filer_name,
    shares_held = EXCLUDED.shares_held,
    market_value_usd = EXCLUDED.market_value_usd,
    pct_portfolio = EXCLUDED.pct_portfolio,
    shares_change_qoq = EXCLUDED.shares_change_qoq,
    source_url = EXCLUDED.source_url,
    recorded_at = now()
"""

_EVENT_COLUMNS = "scraper_id, source_name, event_type, message, occurred_at"

_INSERT_EVENT = f"""
INSERT INTO pipeline_health_events ({_EVENT_COLUMNS})
VALUES (%s, %s, %s, %s, %s)
"""

_SELECT_RECENT_EVENTS = (
    f"SELECT {_EVENT_COLUMNS} FROM pipeline_health_events ORDER BY occurred_at DESC LIMIT %s"
)
_SELECT_EVENTS_SINCE = (
    f"SELECT {_EVENT_COLUMNS} FROM pipeline_health_events WHERE occurred_at > %s "
    "ORDER BY occurred_at DESC LIMIT %s"
)

_MAX_EVENT_LIMIT = 500


def _to_price(row: Row) -> CommodityPrice:
    """Convert a database row into a validated price record.

    Args:
        row: Row as returned by the driver.

    Returns:
        The validated record.
    """
    return CommodityPrice.model_validate(dict(row))


def _to_holding(row: Row) -> InstitutionalHolding:
    """Convert a database row into a validated holding record.

    Args:
        row: Row as returned by the driver.

    Returns:
        The validated record.
    """
    return InstitutionalHolding.model_validate(dict(row))


def _to_event(row: Row) -> PipelineHealthEvent:
    """Convert a database row into a validated pipeline event.

    Args:
        row: Row as returned by the driver.

    Returns:
        The validated record.
    """
    return PipelineHealthEvent.model_validate(dict(row))


class TimescalePriceRepository:
    """Stores and retrieves observed prices."""

    def __init__(self, executor: BulkExecutor) -> None:
        """Create the repository.

        Args:
            executor: Database executor, passed in so tests can substitute a fake.
        """
        self._executor = executor

    async def upsert_prices(self, prices: Sequence[CommodityPrice]) -> int:
        """Write prices, updating any that already exist for the same timestamp.

        Args:
            prices: Validated price records. An empty sequence is a no-op and
                does not touch the database.

        Returns:
            How many records were written.
        """
        if not prices:
            return 0
        param_sets = [
            (
                price.entity_name,
                price.sector.value,
                price.price,
                price.currency,
                price.unit,
                price.pct_change_1d,
                price.pct_change_7d,
                price.recorded_at,
                price.source_name,
                price.source_url,
                price.ingestion_method.value,
            )
            for price in prices
        ]
        await self._executor.execute_many(_UPSERT_PRICE, param_sets)
        return len(param_sets)

    async def latest_price(self, entity_name: str) -> CommodityPrice | None:
        """Return the most recent price for one entity.

        Args:
            entity_name: Entity to look up, for example ``Copper``.

        Returns:
            The newest price, or None when nothing has been recorded for it.
        """
        rows = await self._executor.fetch_all(_SELECT_LATEST_PRICE, (entity_name,))
        return _to_price(rows[0]) if rows else None

    async def price_history(self, entity_name: str, days: int) -> list[CommodityPrice]:
        """Return prices for one entity over a recent window, oldest first.

        Oldest first is what charting libraries expect, so the caller never has
        to reverse the list.

        Args:
            entity_name: Entity to look up.
            days: How many days back to read. Must be positive.

        Returns:
            Prices in chronological order.

        Raises:
            ValueError: If ``days`` is not positive.
        """
        if days <= 0:
            raise ValueError("days must be a positive number of days")
        rows = await self._executor.fetch_all(_SELECT_PRICE_HISTORY, (entity_name, days))
        return [_to_price(row) for row in rows]

    async def latest_prices_by_sector(self, sector: Sector) -> list[CommodityPrice]:
        """Return the newest price for every entity in one sector.

        Args:
            sector: Sector to summarise.

        Returns:
            One price per entity, which is what the risk map renders.
        """
        rows = await self._executor.fetch_all(_SELECT_LATEST_BY_SECTOR, (sector.value,))
        return [_to_price(row) for row in rows]


class TimescaleHoldingsRepository:
    """Stores and retrieves quarterly disclosure lines."""

    def __init__(self, executor: BulkExecutor) -> None:
        """Create the repository.

        Args:
            executor: Database executor, passed in so tests can substitute a fake.
        """
        self._executor = executor

    async def upsert_holdings(self, holdings: Sequence[InstitutionalHolding]) -> int:
        """Write holdings, updating any row for the same filer, stock, and quarter.

        Filers do amend their disclosures, so an update has to be possible
        without creating a second, conflicting row for the same quarter.

        Args:
            holdings: Validated holding records. An empty sequence is a no-op.

        Returns:
            How many records were written.
        """
        if not holdings:
            return 0
        param_sets = [
            (
                holding.filer_name,
                holding.filer_cik,
                holding.stock_ticker,
                holding.shares_held,
                holding.market_value_usd,
                holding.pct_portfolio,
                holding.shares_change_qoq,
                holding.quarter_end,
                holding.source_url,
            )
            for holding in holdings
        ]
        await self._executor.execute_many(_UPSERT_HOLDING, param_sets)
        return len(param_sets)

    async def holders_of(
        self,
        ticker: str,
        quarter_end: date | None = None,
    ) -> list[InstitutionalHolding]:
        """Return the managers holding one stock, newest quarter first.

        Args:
            ticker: Ticker symbol. Case is normalized, since this often comes
                from something a person typed.
            quarter_end: Restrict to one quarter, or None for all quarters.

        Returns:
            Matching holdings.
        """
        symbol = ticker.strip().upper()
        if quarter_end is None:
            rows = await self._executor.fetch_all(_SELECT_HOLDERS, (symbol,))
        else:
            rows = await self._executor.fetch_all(
                _SELECT_HOLDERS_FOR_QUARTER, (symbol, quarter_end)
            )
        return [_to_holding(row) for row in rows]

    async def holdings_of_filer(
        self,
        filer_cik: str,
        quarter_end: date | None = None,
    ) -> list[InstitutionalHolding]:
        """Return one manager's positions, newest quarter first.

        Args:
            filer_cik: The manager's identifier, in any accepted form; it is
                normalized to ten digits before the lookup.
            quarter_end: Restrict to one quarter, or None for all quarters.

        Returns:
            Matching holdings.
        """
        cik = normalize_cik(filer_cik)
        if quarter_end is None:
            rows = await self._executor.fetch_all(_SELECT_FILER_HOLDINGS, (cik,))
        else:
            rows = await self._executor.fetch_all(
                _SELECT_FILER_HOLDINGS_FOR_QUARTER, (cik, quarter_end)
            )
        return [_to_holding(row) for row in rows]


class TimescaleHealthEventRepository:
    """Stores and retrieves the collector audit trail."""

    def __init__(self, executor: SqlExecutor) -> None:
        """Create the repository.

        Args:
            executor: Database executor. Only single-statement support is needed
                here, because events are written one at a time as they happen.
        """
        self._executor = executor

    async def record_event(self, event: PipelineHealthEvent) -> None:
        """Append one event to the audit trail.

        Args:
            event: The event to record.
        """
        await self._executor.execute(
            _INSERT_EVENT,
            (
                event.scraper_id,
                event.source_name,
                event.event_type.value,
                event.message,
                event.occurred_at,
            ),
        )

    async def recent_events(
        self,
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[PipelineHealthEvent]:
        """Return the newest events first.

        Args:
            limit: How many events to return, between 1 and 500. The cap exists
                because this feeds a live stream that would otherwise be able to
                request the whole table.
            since: Only return events after this moment, which is how the live
                feed asks for "anything new".

        Returns:
            Matching events, newest first.

        Raises:
            ValueError: If the limit is outside the allowed range.
        """
        if limit <= 0 or limit > _MAX_EVENT_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_EVENT_LIMIT}")

        if since is None:
            rows = await self._executor.fetch_all(_SELECT_RECENT_EVENTS, (limit,))
        else:
            rows = await self._executor.fetch_all(_SELECT_EVENTS_SINCE, (since, limit))
        return [_to_event(row) for row in rows]
