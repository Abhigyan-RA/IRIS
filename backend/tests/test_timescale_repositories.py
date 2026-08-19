"""Tests for the classes that read and write TimescaleDB rows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from shadow_cpi.db.timescale.repositories import (
    TimescaleHealthEventRepository,
    TimescaleHoldingsRepository,
    TimescalePriceRepository,
)
from shadow_cpi.shared import (
    CommodityPrice,
    IngestionMethod,
    InstitutionalFundSnapshot,
    InstitutionalHolding,
    InstitutionalHoldingEnrichment,
    PipelineEventType,
    PipelineHealthEvent,
    Sector,
)

RECORDED_AT = datetime(2026, 8, 15, 9, 0, tzinfo=UTC)


class FakeExecutor:
    """Records statements and returns canned rows, so no database is needed."""

    def __init__(self, rows: Sequence[Mapping[str, object]] = ()) -> None:
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.batches: list[tuple[str, list[tuple[object, ...]]]] = []
        self._rows = list(rows)

    async def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        self.statements.append((sql, tuple(params)))

    async def execute_many(self, sql: str, param_sets: Sequence[Sequence[object]]) -> None:
        self.batches.append((sql, [tuple(params) for params in param_sets]))

    async def fetch_all(
        self, sql: str, params: Sequence[object] = ()
    ) -> list[Mapping[str, object]]:
        self.statements.append((sql, tuple(params)))
        return self._rows


PRICE_ROW: Mapping[str, object] = {
    "entity_name": "Copper",
    "sector": "metals",
    "price": Decimal("4.52"),
    "currency": "USD",
    "unit": "lb",
    "pct_change_1d": Decimal("1.8"),
    "pct_change_7d": None,
    "recorded_at": RECORDED_AT,
    "source_name": "investing.com",
    "source_url": "https://www.investing.com/commodities/copper",
    "ingestion_method": "brightdata_scrape",
}

HOLDING_ROW: Mapping[str, object] = {
    "filer_name": "Bridgewater Associates",
    "filer_cik": "0001350694",
    "stock_ticker": "NVDA",
    "shares_held": 1_200_000,
    "market_value_usd": Decimal("144000000.00"),
    "pct_portfolio": Decimal("7.02"),
    "shares_change_qoq": 150_000,
    "quarter_end": date(2026, 6, 30),
    "source_url": "https://www.sec.gov/edgar/browse/?CIK=0001350694",
}

EVENT_ROW: Mapping[str, object] = {
    "scraper_id": "whalewisdom_13f_scraper",
    "source_name": "whalewisdom.com",
    "event_type": "self_heal_resolved",
    "message": "[RESOLVED] data ingestion resumed",
    "occurred_at": RECORDED_AT,
}


def _price(entity_name: str = "Copper") -> CommodityPrice:
    return CommodityPrice(
        entity_name=entity_name,
        sector=Sector.METALS,
        price=Decimal("4.52"),
        currency="USD",
        unit="lb",
        pct_change_1d=Decimal("1.8"),
        recorded_at=RECORDED_AT,
        source_name="investing.com",
        source_url="https://www.investing.com/commodities/copper",
        ingestion_method=IngestionMethod.BRIGHTDATA_SCRAPE,
    )


def _holding(ticker: str = "NVDA") -> InstitutionalHolding:
    return InstitutionalHolding(
        filer_name="Bridgewater Associates",
        filer_cik="0001350694",
        stock_ticker=ticker,
        shares_held=1_200_000,
        market_value_usd=Decimal("144000000.00"),
        pct_portfolio=Decimal("7.02"),
        shares_change_qoq=150_000,
        quarter_end=date(2026, 6, 30),
        source_url="https://www.sec.gov/edgar/browse/?CIK=0001350694",
    )


class TestPriceRepositoryWrites:
    @pytest.mark.asyncio
    async def test_writes_all_prices_in_one_batch(self) -> None:
        executor = FakeExecutor()

        written = await TimescalePriceRepository(executor).upsert_prices(
            [_price("Copper"), _price("Brent")]
        )

        assert written == 2
        assert len(executor.batches) == 1
        assert len(executor.batches[0][1]) == 2

    @pytest.mark.asyncio
    async def test_reruns_update_instead_of_duplicating(self) -> None:
        executor = FakeExecutor()

        await TimescalePriceRepository(executor).upsert_prices([_price()])

        sql = executor.batches[0][0]
        assert "ON CONFLICT (entity_name, recorded_at)" in sql
        assert "DO UPDATE SET" in sql

    @pytest.mark.asyncio
    async def test_values_are_bound_as_parameters(self) -> None:
        """Values must never be formatted into the statement text."""
        executor = FakeExecutor()

        await TimescalePriceRepository(executor).upsert_prices([_price()])

        sql, param_sets = executor.batches[0]
        assert sql.count("%s") == len(param_sets[0])
        assert "Copper" not in sql
        assert "Copper" in param_sets[0]

    @pytest.mark.asyncio
    async def test_empty_input_touches_the_database_at_all(self) -> None:
        executor = FakeExecutor()

        written = await TimescalePriceRepository(executor).upsert_prices([])

        assert written == 0
        assert executor.batches == []
        assert executor.statements == []


class TestPriceRepositoryReads:
    @pytest.mark.asyncio
    async def test_latest_price_returns_a_model(self) -> None:
        repository = TimescalePriceRepository(FakeExecutor([PRICE_ROW]))

        price = await repository.latest_price("Copper")

        assert price is not None
        assert price.entity_name == "Copper"
        assert price.sector is Sector.METALS
        assert price.ingestion_method is IngestionMethod.BRIGHTDATA_SCRAPE

    @pytest.mark.asyncio
    async def test_latest_price_returns_none_for_an_untracked_entity(self) -> None:
        repository = TimescalePriceRepository(FakeExecutor([]))

        assert await repository.latest_price("Unobtainium") is None

    @pytest.mark.asyncio
    async def test_latest_price_filters_by_entity_using_a_parameter(self) -> None:
        executor = FakeExecutor([PRICE_ROW])

        await TimescalePriceRepository(executor).latest_price("Copper")

        sql, params = executor.statements[0]
        assert "WHERE entity_name = %s" in sql
        assert params == ("Copper",)

    @pytest.mark.asyncio
    async def test_history_is_returned_oldest_first_for_charting(self) -> None:
        executor = FakeExecutor([PRICE_ROW])

        await TimescalePriceRepository(executor).price_history("Copper", days=30)

        sql, params = executor.statements[0]
        assert "ORDER BY recorded_at ASC" in sql
        assert params == ("Copper", 30)

    @pytest.mark.asyncio
    async def test_history_rejects_a_nonsensical_window(self) -> None:
        repository = TimescalePriceRepository(FakeExecutor())

        with pytest.raises(ValueError, match="days"):
            await repository.price_history("Copper", days=0)

    @pytest.mark.asyncio
    async def test_sector_view_returns_one_row_per_entity(self) -> None:
        executor = FakeExecutor([PRICE_ROW])

        prices = await TimescalePriceRepository(executor).latest_prices_by_sector(Sector.METALS)

        sql, params = executor.statements[0]
        assert "DISTINCT ON (entity_name)" in sql
        assert params == ("metals",)
        assert len(prices) == 1


class TestHoldingsRepository:
    @pytest.mark.asyncio
    async def test_writes_holdings_in_one_batch(self) -> None:
        executor = FakeExecutor()

        written = await TimescaleHoldingsRepository(executor).upsert_holdings(
            [_holding("NVDA"), _holding("AAPL")]
        )

        assert written == 2
        assert len(executor.batches[0][1]) == 2

    @pytest.mark.asyncio
    async def test_restating_a_quarter_updates_the_existing_row(self) -> None:
        executor = FakeExecutor()

        await TimescaleHoldingsRepository(executor).upsert_holdings([_holding()])

        assert "ON CONFLICT (filer_cik, stock_ticker, quarter_end)" in executor.batches[0][0]

    @pytest.mark.asyncio
    async def test_empty_input_writes_nothing(self) -> None:
        executor = FakeExecutor()

        assert await TimescaleHoldingsRepository(executor).upsert_holdings([]) == 0
        assert executor.batches == []

    @pytest.mark.asyncio
    async def test_holders_of_a_ticker_are_returned_newest_quarter_first(self) -> None:
        executor = FakeExecutor([HOLDING_ROW])

        holders = await TimescaleHoldingsRepository(executor).holders_of("NVDA")

        sql, params = executor.statements[0]
        assert "WHERE stock_ticker = %s" in sql
        assert "ORDER BY quarter_end DESC" in sql
        assert params == ("NVDA",)
        assert holders[0].filer_name == "Bridgewater Associates"

    @pytest.mark.asyncio
    async def test_holders_can_be_narrowed_to_one_quarter(self) -> None:
        executor = FakeExecutor([HOLDING_ROW])

        await TimescaleHoldingsRepository(executor).holders_of("NVDA", date(2026, 6, 30))

        sql, params = executor.statements[0]
        assert "quarter_end = %s" in sql
        assert params == ("NVDA", date(2026, 6, 30))

    @pytest.mark.asyncio
    async def test_a_lowercase_ticker_is_matched_after_normalizing(self) -> None:
        """Callers type tickers by hand, so the lookup normalizes the case."""
        executor = FakeExecutor([HOLDING_ROW])

        await TimescaleHoldingsRepository(executor).holders_of("nvda")

        assert executor.statements[0][1] == ("NVDA",)

    @pytest.mark.asyncio
    async def test_filer_holdings_are_looked_up_by_normalized_cik(self) -> None:
        executor = FakeExecutor([HOLDING_ROW])

        await TimescaleHoldingsRepository(executor).holdings_of_filer("1350694")

        sql, params = executor.statements[0]
        assert "WHERE filer_cik = %s" in sql
        assert params == ("0001350694",)


class TestHealthEventRepository:
    @pytest.mark.asyncio
    async def test_records_one_event(self) -> None:
        executor = FakeExecutor()
        event = PipelineHealthEvent(
            scraper_id="whalewisdom_13f_scraper",
            source_name="whalewisdom.com",
            event_type=PipelineEventType.DOM_SHIFT_DETECTED,
            message="[WARNING] price missing from every row",
            occurred_at=RECORDED_AT,
        )

        await TimescaleHealthEventRepository(executor).record_event(event)

        sql, params = executor.statements[0]
        assert "INSERT INTO pipeline_health_events" in sql
        assert "dom_shift_detected" in params

    @pytest.mark.asyncio
    async def test_recent_events_are_newest_first_and_limited(self) -> None:
        executor = FakeExecutor([EVENT_ROW])

        events = await TimescaleHealthEventRepository(executor).recent_events(limit=10)

        sql, params = executor.statements[0]
        assert "ORDER BY occurred_at DESC" in sql
        assert params == (10,)
        assert events[0].event_type is PipelineEventType.SELF_HEAL_RESOLVED

    @pytest.mark.asyncio
    async def test_recent_events_can_start_from_a_moment(self) -> None:
        executor = FakeExecutor([EVENT_ROW])

        await TimescaleHealthEventRepository(executor).recent_events(limit=5, since=RECORDED_AT)

        sql, params = executor.statements[0]
        assert "occurred_at > %s" in sql
        assert params == (RECORDED_AT, 5)

    @pytest.mark.asyncio
    async def test_limit_must_be_sensible(self) -> None:
        repository = TimescaleHealthEventRepository(FakeExecutor())

        with pytest.raises(ValueError, match="limit"):
            await repository.recent_events(limit=0)

    @pytest.mark.asyncio
    async def test_limit_is_capped_to_protect_the_database(self) -> None:
        repository = TimescaleHealthEventRepository(FakeExecutor())

        with pytest.raises(ValueError, match="limit"):
            await repository.recent_events(limit=100_000)


FUND_SNAPSHOT_ROW: dict[str, object] = {
    "filer_name": "Bridgewater Associates",
    "filer_cik": "0001350694",
    "report_period": date(2026, 6, 30),
    "filing_date": date(2026, 8, 14),
    "reported_value_usd": Decimal("20200000000.00"),
    "discretionary_aum_usd": None,
    "top_10_concentration_pct": None,
    "holdings_count": 509,
    "portfolio_turnover_pct": None,
    "whale_score": None,
    "source_name": "whalewisdom.com",
    "source_url": "https://whalewisdom.com/filer/bridgewater-associates-lp",
    "ingestion_method": "brightdata_scrape",
    "observed_at": RECORDED_AT,
}

ENRICHMENT_ROW: dict[str, object] = {
    "filer_cik": "0001350694",
    "stock_ticker": "NVDA",
    "quarter_end": date(2026, 6, 30),
    "stock_name": "NVIDIA Corporation",
    "previous_pct_portfolio": Decimal("6.100"),
    "rank": 3,
    "reported_pct_change_shares": Decimal("14.000"),
    "quarter_first_owned": "Q1 2024",
    "estimated_avg_price": Decimal("111.4200"),
    "source_name": "whalewisdom.com",
    "source_url": "https://whalewisdom.com/filer/bridgewater-associates-lp",
    "ingestion_method": "brightdata_scrape",
    "observed_at": RECORDED_AT,
}


def _fund_snapshot() -> InstitutionalFundSnapshot:
    return InstitutionalFundSnapshot.model_validate(FUND_SNAPSHOT_ROW)


def _enrichment() -> InstitutionalHoldingEnrichment:
    return InstitutionalHoldingEnrichment.model_validate(ENRICHMENT_ROW)


class TestInstitutionalEnrichmentRepository:
    @pytest.mark.asyncio
    async def test_writes_fund_snapshots_without_touching_official_holdings(self) -> None:
        executor = FakeExecutor()

        written = await TimescaleHoldingsRepository(executor).upsert_fund_snapshots(
            [_fund_snapshot()]
        )

        assert written == 1
        sql, rows = executor.batches[0]
        assert "institutional_fund_snapshots" in sql
        assert "institutional_holdings" not in sql
        assert rows[0][1] == "0001350694"

    @pytest.mark.asyncio
    async def test_writes_holding_enrichment_separately(self) -> None:
        executor = FakeExecutor()

        written = await TimescaleHoldingsRepository(executor).upsert_holding_enrichments(
            [_enrichment()]
        )

        assert written == 1
        sql, rows = executor.batches[0]
        assert "institutional_holding_enrichments" in sql
        assert rows[0][1] == "NVDA"

    @pytest.mark.asyncio
    async def test_reads_every_official_holding_from_the_newest_quarter(self) -> None:
        executor = FakeExecutor([HOLDING_ROW])

        holdings = await TimescaleHoldingsRepository(executor).latest_holdings()

        sql, params = executor.statements[0]
        assert "MAX(quarter_end)" in sql
        assert params == ()
        assert holdings[0].stock_ticker == "NVDA"

    @pytest.mark.asyncio
    async def test_reads_the_newest_snapshot_for_each_fund(self) -> None:
        executor = FakeExecutor([FUND_SNAPSHOT_ROW])

        snapshots = await TimescaleHoldingsRepository(executor).latest_fund_snapshots()

        sql, _ = executor.statements[0]
        assert "DISTINCT ON (filer_cik)" in sql
        assert snapshots[0].holdings_count == 509

    @pytest.mark.asyncio
    async def test_reads_enrichment_from_the_newest_quarter(self) -> None:
        executor = FakeExecutor([ENRICHMENT_ROW])

        rows = await TimescaleHoldingsRepository(executor).latest_holding_enrichments()

        sql, _ = executor.statements[0]
        assert "MAX(quarter_end)" in sql
        assert rows[0].stock_name == "NVIDIA Corporation"
