"""The database boundary, expressed as protocols.

Everything that talks to a database in this project depends on the small
interfaces below, never on a driver library directly. Two reasons:

1. Tests can pass in a fake that records SQL, so unit tests need no running
   database and stay fast and deterministic.
2. Swapping or wrapping the driver (connection pooling, retries, logging) does
   not touch a single line of business logic.

The interfaces are deliberately narrow and split by capability. A component that
only reads prices depends on ``PriceReader`` and cannot accidentally write.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from shadow_cpi.shared import (
    CommodityPrice,
    InstitutionalFundSnapshot,
    InstitutionalHolding,
    InstitutionalHoldingEnrichment,
    PipelineHealthEvent,
    Sector,
)

# One row from a query, as a mapping of column name to value.
Row = Mapping[str, object]


@runtime_checkable
class SqlExecutor(Protocol):
    """Runs parameterized SQL.

    Values are always passed separately from the statement. Building SQL by
    string concatenation is how injection happens, so no implementation of this
    interface accepts a pre-formatted statement with values inside it.
    """

    async def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        """Run a statement that returns no rows."""
        ...

    async def fetch_all(self, sql: str, params: Sequence[object] = ()) -> list[Row]:
        """Run a query and return every row."""
        ...


class BulkExecutor(SqlExecutor, Protocol):
    """An executor that can also run one statement against many value sets.

    Kept separate from ``SqlExecutor`` so that components which never write in
    bulk are not required to support it.
    """

    async def execute_many(self, sql: str, param_sets: Sequence[Sequence[object]]) -> None:
        """Run the same statement once per set of values."""
        ...


class PriceWriter(Protocol):
    """Stores observed prices."""

    async def upsert_prices(self, prices: Sequence[CommodityPrice]) -> int:
        """Insert prices, updating any row that already exists.

        Args:
            prices: Validated price records.

        Returns:
            How many rows were written.
        """
        ...


class PriceReader(Protocol):
    """Reads price history."""

    async def latest_price(self, entity_name: str) -> CommodityPrice | None:
        """Return the most recent price for one entity, or None if untracked."""
        ...

    async def price_history(self, entity_name: str, days: int) -> list[CommodityPrice]:
        """Return prices for one entity over the past number of days, oldest first."""
        ...

    async def latest_prices_by_sector(self, sector: Sector) -> list[CommodityPrice]:
        """Return the newest price for every entity in one sector."""
        ...


class HoldingsWriter(Protocol):
    """Stores quarterly disclosure lines."""

    async def upsert_holdings(self, holdings: Sequence[InstitutionalHolding]) -> int:
        """Insert holdings, updating any row for the same filer, stock, and quarter."""
        ...


class HoldingsReader(Protocol):
    """Reads quarterly disclosure lines."""

    async def holders_of(
        self, ticker: str, quarter_end: date | None = None
    ) -> list[InstitutionalHolding]:
        """Return the managers holding one stock, newest quarter first."""
        ...

    async def holdings_of_filer(
        self, filer_cik: str, quarter_end: date | None = None
    ) -> list[InstitutionalHolding]:
        """Return one manager's positions, newest quarter first."""
        ...


class HealthEventWriter(Protocol):
    """Records what happened during a collector run."""

    async def record_event(self, event: PipelineHealthEvent) -> None:
        """Append one event to the audit trail."""
        ...


class HealthEventReader(Protocol):
    """Reads the collector audit trail."""

    async def recent_events(
        self,
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[PipelineHealthEvent]:
        """Return the newest events first, optionally only those after a moment."""
        ...


class InstitutionalEnrichmentWriter(Protocol):
    """Stores scraped analytics that enrich, but never replace, official holdings."""

    async def upsert_fund_snapshots(self, snapshots: Sequence[InstitutionalFundSnapshot]) -> int:
        """Insert or update fund-quarter summaries."""
        ...

    async def upsert_holding_enrichments(
        self, enrichments: Sequence[InstitutionalHoldingEnrichment]
    ) -> int:
        """Insert or update human-readable fields for official holding rows."""
        ...


class InstitutionalIntelligenceReader(Protocol):
    """Reads the complete current institutional view."""

    async def latest_holdings(self) -> list[InstitutionalHolding]:
        """Return every holding from the newest quarter in storage."""
        ...

    async def latest_fund_snapshots(self) -> list[InstitutionalFundSnapshot]:
        """Return the newest public summary for each configured fund."""
        ...

    async def latest_holding_enrichments(self) -> list[InstitutionalHoldingEnrichment]:
        """Return enrichment rows from the newest available quarter."""
        ...
