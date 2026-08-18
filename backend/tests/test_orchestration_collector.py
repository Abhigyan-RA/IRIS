"""Tests for the service that runs sources and stores what they produce."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from shadow_cpi.config import build_settings
from shadow_cpi.ingestion.base import IngestionContext, IngestionResult
from shadow_cpi.ingestion.registry import SourceRegistry
from shadow_cpi.orchestration.collector import CollectionService
from shadow_cpi.shared import (
    CommodityPrice,
    IngestionMethod,
    InstitutionalHolding,
    PipelineHealthEvent,
    Sector,
)

SETTINGS = build_settings(
    {
        "GEMINI_API_KEY": "test-gemini-key",
        "BRIGHTDATA_API_KEY": "test-brightdata-key",
        "NEO4J_PASSWORD": "test-neo4j-password",
        "CRON_SECRET": "test-cron-secret",
    }
)

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def _price(entity_name: str = "Copper") -> CommodityPrice:
    return CommodityPrice(
        entity_name=entity_name,
        sector=Sector.METALS,
        price=Decimal("4.52"),
        currency="USD",
        unit="lb",
        recorded_at=NOW,
        source_name="investing.com",
        source_url="https://www.investing.com/commodities/copper",
        ingestion_method=IngestionMethod.BRIGHTDATA_SCRAPE,
    )


def _holding() -> InstitutionalHolding:
    return InstitutionalHolding(
        filer_name="Bridgewater Associates",
        filer_cik="0001350694",
        stock_ticker="NVDA",
        shares_held=1_200_000,
        quarter_end=date(2026, 6, 30),
    )


class RecordingPriceWriter:
    def __init__(self) -> None:
        self.written: list[CommodityPrice] = []

    async def upsert_prices(self, prices: Sequence[CommodityPrice]) -> int:
        self.written.extend(prices)
        return len(prices)


class RecordingHoldingsWriter:
    def __init__(self) -> None:
        self.written: list[InstitutionalHolding] = []

    async def upsert_holdings(self, holdings: Sequence[InstitutionalHolding]) -> int:
        self.written.extend(holdings)
        return len(holdings)


class RecordingEventWriter:
    def __init__(self) -> None:
        self.events: list[PipelineHealthEvent] = []

    async def record_event(self, event: PipelineHealthEvent) -> None:
        self.events.append(event)


class FailingPriceWriter:
    async def upsert_prices(self, prices: Sequence[CommodityPrice]) -> int:
        raise RuntimeError("the database is unreachable")


class UnusedHttpClient:
    async def get_json(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        raise AssertionError("this test's sources do not make requests")

    async def get_text(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        raise AssertionError("this test's sources do not make requests")

    async def post_json(
        self,
        url: str,
        body: Mapping[str, object],
        headers: Mapping[str, str] | None = None,
    ) -> object:
        raise AssertionError("this test's sources do not make requests")


class PriceSource:
    """A source that reports one price."""

    source_id = "price_source"
    source_name = "prices.example"
    is_configured = True

    def __init__(self, context: IngestionContext) -> None:
        self.context = context

    async def ingest(self) -> IngestionResult:
        return IngestionResult(source_name=self.source_name, prices=(_price(),))


class HoldingSource:
    """A source that reports one holding."""

    source_id = "holding_source"
    source_name = "holdings.example"
    is_configured = True

    def __init__(self, context: IngestionContext) -> None:
        self.context = context

    async def ingest(self) -> IngestionResult:
        return IngestionResult(source_name=self.source_name, holdings=(_holding(),))


class UnconfiguredSource:
    """A source whose optional credential is absent."""

    source_id = "unconfigured_source"
    source_name = "optional.example"
    is_configured = False

    def __init__(self, context: IngestionContext) -> None:
        self.context = context

    async def ingest(self) -> IngestionResult:
        raise AssertionError("an unconfigured source must not be run")


class BrokenSource:
    """A source whose upstream is unreachable."""

    source_id = "broken_source"
    source_name = "broken.example"
    is_configured = True

    def __init__(self, context: IngestionContext) -> None:
        self.context = context

    async def ingest(self) -> IngestionResult:
        raise RuntimeError("upstream returned 503")


class EmptySource:
    """A source with nothing new to report."""

    source_id = "empty_source"
    source_name = "quiet.example"
    is_configured = True

    def __init__(self, context: IngestionContext) -> None:
        self.context = context

    async def ingest(self) -> IngestionResult:
        return IngestionResult(source_name=self.source_name)


def _service(
    *sources: type,
    prices: object = None,
    holdings: object = None,
    events: object = None,
) -> tuple[CollectionService, RecordingPriceWriter, RecordingHoldingsWriter, RecordingEventWriter]:
    registry = SourceRegistry()
    for source in sources:
        registry.register(source.source_id, source)

    price_writer = prices if prices is not None else RecordingPriceWriter()
    holding_writer = holdings if holdings is not None else RecordingHoldingsWriter()
    event_writer = events if events is not None else RecordingEventWriter()

    service = CollectionService(
        registry=registry,
        context=IngestionContext(http=UnusedHttpClient(), settings=SETTINGS),
        prices=price_writer,  # type: ignore[arg-type]
        holdings=holding_writer,  # type: ignore[arg-type]
        events=event_writer,  # type: ignore[arg-type]
    )
    return service, price_writer, holding_writer, event_writer  # type: ignore[return-value]


class TestRunningOneSource:
    @pytest.mark.asyncio
    async def test_stores_the_prices_a_source_produced(self) -> None:
        service, prices, _, _ = _service(PriceSource)

        outcome = await service.run_source("price_source")

        assert outcome.prices_written == 1
        assert [price.entity_name for price in prices.written] == ["Copper"]

    @pytest.mark.asyncio
    async def test_stores_the_holdings_a_source_produced(self) -> None:
        service, _, holdings, _ = _service(HoldingSource)

        outcome = await service.run_source("holding_source")

        assert outcome.holdings_written == 1
        assert holdings.written[0].stock_ticker == "NVDA"

    @pytest.mark.asyncio
    async def test_records_a_success_event_saying_what_was_stored(self) -> None:
        service, _, _, events = _service(PriceSource)

        await service.run_source("price_source")

        assert len(events.events) == 1
        event = events.events[0]
        assert event.event_type.value == "success"
        assert event.scraper_id == "price_source"
        assert "1" in (event.message or "")

    @pytest.mark.asyncio
    async def test_a_source_with_nothing_new_is_a_success_not_a_failure(self) -> None:
        """Most sources publish on a schedule, so polling between publications is normal."""
        service, _, _, events = _service(EmptySource)

        outcome = await service.run_source("empty_source")

        assert outcome.error is None
        assert events.events[0].event_type.value == "success"

    @pytest.mark.asyncio
    async def test_an_unconfigured_source_is_skipped_rather_than_run(self) -> None:
        service, _, _, events = _service(UnconfiguredSource)

        outcome = await service.run_source("unconfigured_source")

        assert outcome.skipped is True
        assert outcome.prices_written == 0
        assert events.events == []

    @pytest.mark.asyncio
    async def test_an_unreachable_source_is_recorded_as_a_failed_collection(self) -> None:
        service, _, _, events = _service(BrokenSource)

        outcome = await service.run_source("broken_source")

        assert outcome.error is not None
        assert events.events[0].event_type.value == "collection_failed"
        assert "503" in (events.events[0].message or "")

    @pytest.mark.asyncio
    async def test_a_failure_does_not_raise_out_of_the_service(self) -> None:
        """A scheduled run must survive one bad source and carry on."""
        service, _, _, _ = _service(BrokenSource)

        outcome = await service.run_source("broken_source")

        assert outcome.source_id == "broken_source"

    @pytest.mark.asyncio
    async def test_a_storage_failure_is_reported_rather_than_swallowed(self) -> None:
        service, _, _, events = _service(PriceSource, prices=FailingPriceWriter())

        outcome = await service.run_source("price_source")

        assert outcome.error is not None
        assert "unreachable" in outcome.error
        assert events.events[0].event_type.value == "collection_failed"

    @pytest.mark.asyncio
    async def test_an_unknown_source_is_reported_clearly(self) -> None:
        service, _, _, _ = _service(PriceSource)

        outcome = await service.run_source("not_a_source")

        assert outcome.error is not None
        assert "not_a_source" in outcome.error


class TestRunningEverySource:
    @pytest.mark.asyncio
    async def test_runs_every_registered_source(self) -> None:
        service, prices, holdings, _ = _service(PriceSource, HoldingSource)

        outcomes = await service.run_all()

        assert len(outcomes) == 2
        assert len(prices.written) == 1
        assert len(holdings.written) == 1

    @pytest.mark.asyncio
    async def test_one_broken_source_does_not_stop_the_others(self) -> None:
        service, prices, _, _ = _service(BrokenSource, PriceSource)

        outcomes = await service.run_all()

        assert len(prices.written) == 1
        assert any(outcome.error is not None for outcome in outcomes)
        assert any(outcome.error is None for outcome in outcomes)

    @pytest.mark.asyncio
    async def test_unconfigured_sources_are_reported_as_skipped(self) -> None:
        service, _, _, _ = _service(PriceSource, UnconfiguredSource)

        outcomes = await service.run_all()

        skipped = [outcome for outcome in outcomes if outcome.skipped]
        assert [outcome.source_id for outcome in skipped] == ["unconfigured_source"]

    @pytest.mark.asyncio
    async def test_a_run_with_no_sources_registered_does_nothing_quietly(self) -> None:
        service, _, _, events = _service()

        outcomes = await service.run_all()

        assert outcomes == []
        assert events.events == []
