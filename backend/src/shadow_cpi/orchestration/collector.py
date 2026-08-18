"""Running sources and storing what they produce.

This is the piece that turns a collection of source classes into a working pipeline:
build a source, ask it for records, write those records, and record what happened. Until
something does that, the databases stay empty however many sources exist.

Two rules shape it. A failure in one source never stops the others, because a scheduled
run that gives up at the first unreachable website collects nothing all day. And every
run leaves a trace in the health feed, so an empty screen can always be explained.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from shadow_cpi.db.protocols import HealthEventWriter, HoldingsWriter, PriceWriter
from shadow_cpi.ingestion.base import IngestionContext
from shadow_cpi.ingestion.changes import HistoryChangeCalculator, PriceHistoryReader
from shadow_cpi.ingestion.registry import SourceRegistry, default_registry
from shadow_cpi.shared import CommodityPrice, PipelineEventType, PipelineHealthEvent


@dataclass(frozen=True, slots=True)
class CollectionOutcome:
    """What one source's run achieved.

    Attributes:
        source_id: Which source ran.
        source_name: Where it reads from.
        prices_written: How many price records were stored.
        holdings_written: How many holding records were stored.
        skipped: True when the source was not run because it is not configured, which
            is a normal state for the sources whose credentials are optional.
        error: Plain-language reason the run failed, or None when it did not.
    """

    source_id: str
    source_name: str
    prices_written: int = 0
    holdings_written: int = 0
    skipped: bool = False
    error: str | None = None

    @property
    def records_written(self) -> int:
        """Total records stored by this run.

        Returns:
            Prices plus holdings.
        """
        return self.prices_written + self.holdings_written


@dataclass(frozen=True, slots=True)
class CollectionStores:
    """Where a run writes what it collected.

    The three always travel together, and grouping them keeps the service's constructor
    about one thing: what to run, and where the results go.

    Attributes:
        prices: Where price records are stored.
        holdings: Where holding records are stored.
        events: Where the record of each run is written.
    """

    prices: PriceWriter
    holdings: HoldingsWriter
    events: HealthEventWriter


class CollectionService:
    """Runs sources and stores their output."""

    def __init__(
        self,
        registry: SourceRegistry,
        context: IngestionContext,
        stores: CollectionStores,
        changes: HistoryChangeCalculator | None = None,
    ) -> None:
        """Create the service.

        Args:
            registry: Where sources are looked up. Injected so a run can be narrowed to
                a subset, and so tests need no real sources.
            context: Shared HTTP client and settings handed to each source.
            stores: Where the results are written.
            changes: Works out changes a source did not publish, from readings already
                stored. Optional, because a deployment can choose to keep only what each
                source states.
        """
        self._registry = registry
        self._context = context
        self._prices = stores.prices
        self._holdings = stores.holdings
        self._events = stores.events
        self._changes = changes

    async def run_source(self, source_id: str) -> CollectionOutcome:
        """Run one source and store what it produced.

        Args:
            source_id: Identifier of the source to run.

        Returns:
            What the run achieved, including a readable reason if it failed. Failures are
            returned rather than raised, because the caller is usually a scheduled run
            that must continue with the remaining sources.
        """
        try:
            ingestor = self._registry.build(source_id, self._context)
        except KeyError as error:
            return CollectionOutcome(
                source_id=source_id,
                source_name="unknown",
                error=str(error).strip("'"),
            )

        source_name = getattr(ingestor, "source_name", source_id)

        # Sources whose credentials are optional report whether they can run. Skipping
        # is deliberate and quiet: a deployment without an EIA key is a valid
        # deployment, not a fault worth logging every hour.
        if getattr(ingestor, "is_configured", True) is False:
            return CollectionOutcome(source_id=source_id, source_name=source_name, skipped=True)

        try:
            result = await ingestor.ingest()
            prices: Sequence[CommodityPrice] = result.prices
            if self._changes is not None:
                # Done before storing, so the stored row carries the change and every
                # reader of it agrees rather than each recomputing its own.
                prices = await self._changes.fill(list(prices))
            prices_written = await self._prices.upsert_prices(prices)
            holdings_written = await self._holdings.upsert_holdings(result.holdings)
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            await self._record(source_id, source_name, PipelineEventType.COLLECTION_FAILED, reason)
            return CollectionOutcome(source_id=source_id, source_name=source_name, error=reason)

        await self._record(
            source_id,
            source_name,
            PipelineEventType.SUCCESS,
            f"[OK] stored {prices_written} prices and {holdings_written} holdings",
        )
        return CollectionOutcome(
            source_id=source_id,
            source_name=source_name,
            prices_written=prices_written,
            holdings_written=holdings_written,
        )

    async def run_all(self) -> list[CollectionOutcome]:
        """Run every registered source, in identifier order.

        Returns:
            One outcome per source. Sources are run one after another rather than at
            once, so a slow source cannot combine with others to exhaust the database
            connection pool or a provider's rate limit.
        """
        return [await self.run_source(source_id) for source_id in self._registry.source_ids()]

    async def _record(
        self,
        source_id: str,
        source_name: str,
        event_type: PipelineEventType,
        message: str,
    ) -> None:
        """Write one entry to the health feed.

        Args:
            source_id: Source the entry concerns.
            source_name: Where that source reads from.
            event_type: What kind of entry this is.
            message: Human-readable detail.
        """
        await self._events.record_event(
            PipelineHealthEvent(
                scraper_id=source_id,
                source_name=source_name,
                event_type=event_type,
                message=message,
                occurred_at=datetime.now(UTC),
            )
        )


def build_default_service(
    context: IngestionContext,
    stores: CollectionStores,
    history: PriceHistoryReader | None = None,
) -> CollectionService:
    """Build a service over every source the application knows about.

    Args:
        context: Shared HTTP client and settings.
        stores: Where the results are written.
        history: Where earlier readings are read from, so changes a source does not publish
            can be worked out. Optional: without it, only what a source states is stored.

    Returns:
        A service backed by the application's source registry.
    """
    # Importing these packages is what registers the sources.
    import shadow_cpi.ingestion.brightdata
    import shadow_cpi.ingestion.official  # noqa: F401

    return CollectionService(
        registry=default_registry,
        context=context,
        stores=stores,
        changes=None if history is None else HistoryChangeCalculator(history),
    )
