"""Tests for the scraped price collectors."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

import pytest

from shadow_cpi.config import build_settings
from shadow_cpi.ingestion.base import IngestionContext
from shadow_cpi.ingestion.brightdata.collectors import (
    SCRAPED_SOURCES,
    ScrapedPriceIngestor,
    ScrapedSource,
    parse_scraped_price,
)
from shadow_cpi.ingestion.registry import default_registry
from shadow_cpi.shared import IngestionMethod, PipelineHealthEvent, Sector

MINIMUM_ENV = {
    "GEMINI_API_KEY": "test-gemini-key",
    "BRIGHTDATA_API_KEY": "test-brightdata-key",
    "NEO4J_PASSWORD": "test-neo4j-password",
    "CRON_SECRET": "test-cron-secret",
}

SETTINGS = build_settings(MINIMUM_ENV)

COPPER = SCRAPED_SOURCES["lme_copper_scraper"]


class FakeRunner:
    """Returns scripted rows in place of fetching and reading a real page."""

    def __init__(self, rows: Sequence[Mapping[str, object]], healed: bool = False) -> None:
        self.rows = list(rows)
        self.healed = healed
        self.calls: list[tuple[str, str, str]] = []

    async def run(
        self,
        collector_id: str,
        source_name: str,
        url: str,
        description: str,
        entity_name: str,
    ) -> object:
        from shadow_cpi.ingestion.brightdata.self_heal import RunOutcome

        self.calls.append((collector_id, source_name, url))
        return RunOutcome(rows=self.rows, healed=self.healed, reason="scripted")


class RecordingEventWriter:
    def __init__(self) -> None:
        self.events: list[PipelineHealthEvent] = []

    async def record_event(self, event: PipelineHealthEvent) -> None:
        self.events.append(event)


class UnusedHttpClient:
    async def get_json(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        raise AssertionError("the runner is faked, so no request should be made")

    async def get_text(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        raise AssertionError("the runner is faked, so no request should be made")

    async def post_json(
        self,
        url: str,
        body: Mapping[str, object],
        headers: Mapping[str, str] | None = None,
    ) -> object:
        raise AssertionError("the runner is faked, so no request should be made")


def _ingestor(rows: Sequence[Mapping[str, object]], healed: bool = False) -> ScrapedPriceIngestor:
    context = IngestionContext(http=UnusedHttpClient(), settings=SETTINGS)
    return ScrapedPriceIngestor(context, source=COPPER, runner=FakeRunner(rows, healed))


class TestPriceTextParsing:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("4.52", Decimal("4.52")),
            ("$4.52", Decimal("4.52")),
            ("4,520.75", Decimal("4520.75")),
            ("  4.52  ", Decimal("4.52")),
            ("USD 4.52", Decimal("4.52")),
            ("-37.63", Decimal("-37.63")),
            ("+1.80", Decimal("1.80")),
            ("1.80%", Decimal("1.80")),
        ],
    )
    def test_reads_the_number_out_of_scraped_text(self, raw: str, expected: Decimal) -> None:
        """Scraped values arrive as display text, with currency and separators."""
        assert parse_scraped_price(raw) == expected

    def test_a_number_is_accepted_directly(self) -> None:
        assert parse_scraped_price(4.52) == Decimal("4.52")

    @pytest.mark.parametrize("raw", ["", "   ", "n/a", "--", None, "unchanged"])
    def test_values_that_are_not_numbers_are_rejected(self, raw: object) -> None:
        assert parse_scraped_price(raw) is None


class TestScrapedPriceIngestor:
    def test_source_is_identified_for_schedules_and_logs(self) -> None:
        ingestor = _ingestor([{"price": "4.52"}])

        assert ingestor.source_id == "lme_copper_scraper"
        assert ingestor.source_name == "investing.com"

    def test_a_scraped_source_needs_a_collector_to_be_configured(self) -> None:
        """A commercial site is collected by a Scraper Studio collector, or not at all."""
        context = IngestionContext(http=UnusedHttpClient(), settings=SETTINGS)

        assert ScrapedPriceIngestor(context, source=COPPER).is_configured is False

    def test_a_scraped_source_with_a_collector_is_ready(self) -> None:
        with_collector = build_settings(
            {**MINIMUM_ENV, "SCRAPER_STUDIO_COLLECTORS": "lme_copper_scraper=c_abc123"}
        )
        context = IngestionContext(http=UnusedHttpClient(), settings=with_collector)

        assert ScrapedPriceIngestor(context, source=COPPER).is_configured is True

    def test_a_government_page_needs_no_collector(self) -> None:
        """It publishes openly, so it is read directly and costs nothing."""
        eia = SCRAPED_SOURCES["eia_wti_page"]
        context = IngestionContext(http=UnusedHttpClient(), settings=SETTINGS)

        assert ScrapedPriceIngestor(context, source=eia).is_configured is True

    @pytest.mark.asyncio
    async def test_maps_a_scraped_row_to_a_price_record(self) -> None:
        result = await _ingestor([{"price": "4.52", "change_pct": "1.8"}]).ingest()

        price = result.prices[0]
        assert price.entity_name == "Copper"
        assert price.sector is Sector.METALS
        assert price.price == Decimal("4.52")
        assert price.unit == "lb"
        assert price.pct_change_1d == Decimal("1.8")
        assert price.ingestion_method is IngestionMethod.BRIGHTDATA_SCRAPE

    @pytest.mark.asyncio
    async def test_records_the_page_the_value_came_from(self) -> None:
        result = await _ingestor([{"price": "4.52"}]).ingest()

        assert result.prices[0].source_url == COPPER.url

    @pytest.mark.asyncio
    async def test_daily_change_is_optional(self) -> None:
        result = await _ingestor([{"price": "4.52"}]).ingest()

        assert result.prices[0].pct_change_1d is None

    @pytest.mark.asyncio
    async def test_an_unparseable_change_does_not_discard_a_valid_price(self) -> None:
        result = await _ingestor([{"price": "4.52", "change_pct": "unchanged"}]).ingest()

        assert result.prices[0].price == Decimal("4.52")
        assert result.prices[0].pct_change_1d is None

    @pytest.mark.asyncio
    async def test_rows_whose_price_cannot_be_read_are_skipped(self) -> None:
        result = await _ingestor([{"price": "n/a"}, {"price": "4.52"}]).ingest()

        assert len(result.prices) == 1

    @pytest.mark.asyncio
    async def test_a_run_that_could_not_be_repaired_yields_nothing(self) -> None:
        """Storing nothing is correct here; a stale badge is better than a wrong price."""
        result = await _ingestor([]).ingest()

        assert result.record_count == 0

    @pytest.mark.asyncio
    async def test_a_nested_value_is_read_by_path(self) -> None:
        """A generated collector nests its values, for example price.value."""
        rows = [{"price": {"value": 6.719, "currency": "USD"}, "price_change_percent": "(+1.65%)"}]

        result = await _ingestor(rows).ingest()

        assert result.prices[0].price == Decimal("6.719")
        assert result.prices[0].pct_change_1d == Decimal("1.65")

    @pytest.mark.asyncio
    async def test_the_configured_collector_is_the_one_that_runs(self) -> None:
        runner = FakeRunner([{"price": "4.52"}])
        context = IngestionContext(http=UnusedHttpClient(), settings=SETTINGS)

        await ScrapedPriceIngestor(context, source=COPPER, runner=runner).ingest()

        assert runner.calls == [("lme_copper_scraper", "investing.com", COPPER.url)]


class TestShippedSources:
    def test_each_scraped_source_is_fully_described(self) -> None:
        for source_id, source in SCRAPED_SOURCES.items():
            assert source.collector_id == source_id
            assert source.url.startswith("https://")
            assert source.entity_name
            assert source.extraction_prompt
            assert isinstance(source, ScrapedSource)

    def test_extraction_prompts_describe_data_rather_than_markup(self) -> None:
        """Describing meaning instead of position is what survives a redesign."""
        for source in SCRAPED_SOURCES.values():
            lowered = source.extraction_prompt.lower()
            assert "css" not in lowered
            assert "xpath" not in lowered
            assert "<" not in lowered

    def test_the_metals_and_freight_sources_are_covered(self) -> None:
        entities = {source.entity_name for source in SCRAPED_SOURCES.values()}

        assert "Copper" in entities
        assert "FBX_Global" in entities
        assert "Baltic_Dry_Index" in entities

    def test_every_scraped_source_registers_itself(self) -> None:
        registered = set(default_registry.source_ids())

        assert registered >= set(SCRAPED_SOURCES)

    def test_a_registered_scraped_source_can_be_built(self) -> None:
        context = IngestionContext(http=UnusedHttpClient(), settings=SETTINGS)

        built = default_registry.build("lme_copper_scraper", context)

        assert isinstance(built, ScrapedPriceIngestor)
        assert built.source_id == "lme_copper_scraper"
