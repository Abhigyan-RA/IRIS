"""Tests for filling in price changes from stored history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from shadow_cpi.ingestion.changes import HistoryChangeCalculator
from shadow_cpi.shared import CommodityPrice, IngestionMethod, Sector

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _price(
    price: str,
    *,
    recorded_at: datetime = NOW,
    change_1d: Decimal | None = None,
    change_7d: Decimal | None = None,
    entity_name: str = "Copper",
) -> CommodityPrice:
    return CommodityPrice(
        entity_name=entity_name,
        sector=Sector.METALS,
        price=Decimal(price),
        currency="USD",
        unit="lb",
        pct_change_1d=change_1d,
        pct_change_7d=change_7d,
        recorded_at=recorded_at,
        source_name="investing.com",
        source_url="https://www.investing.com/commodities/copper",
        ingestion_method=IngestionMethod.BRIGHTDATA_SCRAPE,
    )


class FakeHistory:
    """History reader that answers from a fixed list."""

    def __init__(self, history: list[CommodityPrice]) -> None:
        self._history = history
        self.requests: list[tuple[str, int]] = []

    async def price_history(self, entity_name: str, days: int) -> list[CommodityPrice]:
        self.requests.append((entity_name, days))
        return [row for row in self._history if row.entity_name == entity_name]


class TestFillingInWeeklyChange:
    @pytest.mark.asyncio
    async def test_a_weekly_change_is_computed_from_stored_history(self) -> None:
        history = FakeHistory([_price("100", recorded_at=NOW - timedelta(days=7))])
        calculator = HistoryChangeCalculator(history)

        [enriched] = await calculator.fill([_price("110")])

        assert enriched.pct_change_7d == Decimal("10.00")

    @pytest.mark.asyncio
    async def test_a_daily_change_is_computed_when_the_source_reported_none(self) -> None:
        history = FakeHistory([_price("80", recorded_at=NOW - timedelta(days=1))])
        calculator = HistoryChangeCalculator(history)

        [enriched] = await calculator.fill([_price("84")])

        assert enriched.pct_change_1d == Decimal("5.00")

    @pytest.mark.asyncio
    async def test_a_change_the_source_reported_is_left_alone(self) -> None:
        """The page's own figure is authoritative: it knows its previous close, we infer."""
        history = FakeHistory([_price("80", recorded_at=NOW - timedelta(days=1))])
        calculator = HistoryChangeCalculator(history)

        [enriched] = await calculator.fill([_price("84", change_1d=Decimal("0.58"))])

        assert enriched.pct_change_1d == Decimal("0.58")

    @pytest.mark.asyncio
    async def test_nothing_is_invented_when_there_is_no_history(self) -> None:
        calculator = HistoryChangeCalculator(FakeHistory([]))

        [enriched] = await calculator.fill([_price("110")])

        assert enriched.pct_change_1d is None
        assert enriched.pct_change_7d is None

    @pytest.mark.asyncio
    async def test_the_nearest_reading_to_a_week_ago_is_used(self) -> None:
        """Collection is daily at best, so an exact seven-day-old reading rarely exists."""
        history = FakeHistory(
            [
                _price("100", recorded_at=NOW - timedelta(days=8)),
                _price("105", recorded_at=NOW - timedelta(days=6, hours=20)),
                _price("120", recorded_at=NOW - timedelta(hours=2)),
            ]
        )
        calculator = HistoryChangeCalculator(FakeHistory(history._history))

        [enriched] = await calculator.fill([_price("126")])

        assert enriched.pct_change_7d == Decimal("20.00")

    @pytest.mark.asyncio
    async def test_a_reading_from_today_is_not_treated_as_a_week_old(self) -> None:
        history = FakeHistory([_price("125", recorded_at=NOW - timedelta(hours=1))])
        calculator = HistoryChangeCalculator(history)

        [enriched] = await calculator.fill([_price("126")])

        assert enriched.pct_change_7d is None

    @pytest.mark.asyncio
    async def test_a_previous_price_of_zero_is_not_divided_by(self) -> None:
        history = FakeHistory([_price("0", recorded_at=NOW - timedelta(days=7))])
        calculator = HistoryChangeCalculator(history)

        [enriched] = await calculator.fill([_price("110")])

        assert enriched.pct_change_7d is None

    @pytest.mark.asyncio
    async def test_each_entity_is_looked_up_once_however_many_rows_it_has(self) -> None:
        history = FakeHistory([_price("100", recorded_at=NOW - timedelta(days=7))])
        calculator = HistoryChangeCalculator(history)

        await calculator.fill([_price("110"), _price("111")])

        assert history.requests == [("Copper", 8)]

    @pytest.mark.asyncio
    async def test_a_fall_is_reported_as_negative(self) -> None:
        history = FakeHistory([_price("100", recorded_at=NOW - timedelta(days=7))])
        calculator = HistoryChangeCalculator(history)

        [enriched] = await calculator.fill([_price("90")])

        assert enriched.pct_change_7d == Decimal("-10.00")

    @pytest.mark.asyncio
    async def test_an_unreadable_history_does_not_stop_the_run(self) -> None:
        """A price is worth storing even if the change beside it could not be worked out."""

        class BrokenHistory:
            async def price_history(self, entity_name: str, days: int) -> list[CommodityPrice]:
                raise RuntimeError("database unavailable")

        calculator = HistoryChangeCalculator(BrokenHistory())

        [enriched] = await calculator.fill([_price("110")])

        assert enriched.price == Decimal("110")
        assert enriched.pct_change_7d is None
