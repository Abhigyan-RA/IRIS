"""Working out how much a price has moved, from prices already stored.

Most pages publish a daily change beside the price and nothing else. That is enough to say
what happened yesterday and useless for the question people actually ask, which is whether
something is trending. Once a few days of readings exist, the weekly change can be worked out
from them.

Two rules keep this honest. A figure the source published is never overwritten: the page
knows its own previous close, while we can only compare the readings we happened to take. And
nothing is invented: when no earlier reading exists, the change stays empty and the screen
says so, rather than showing a confident zero.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Protocol

from shadow_cpi.shared import CommodityPrice

# How far either side of the target a reading may sit and still count. Collection is daily at
# best and can miss a day, so demanding an exact age would leave the change permanently empty.
_TOLERANCE = timedelta(days=2)

_DAY = timedelta(days=1)
_WEEK = timedelta(days=7)

# Percentages are reported to two places, which is how every source quotes them.
_PLACES = Decimal("0.01")


class PriceHistoryReader(Protocol):
    """Reads previously stored prices for one entity."""

    async def price_history(self, entity_name: str, days: int) -> list[CommodityPrice]:
        """Return stored readings for an entity.

        Args:
            entity_name: Entity to look up.
            days: How far back to look.

        Returns:
            The readings, in any order.
        """
        ...


class HistoryChangeCalculator:
    """Fills in missing changes on freshly collected prices."""

    def __init__(self, history: PriceHistoryReader) -> None:
        """Create the calculator.

        Args:
            history: Where earlier readings are read from.
        """
        self._history = history

    async def fill(self, prices: list[CommodityPrice]) -> list[CommodityPrice]:
        """Add daily and weekly changes where they are missing.

        Args:
            prices: Freshly collected prices.

        Returns:
            The same prices, with changes added where earlier readings allow it. A failure
            to read history returns the prices untouched: a price is worth storing even when
            the change beside it could not be worked out.
        """
        if not prices:
            return prices

        # One lookup per entity, however many rows share it: a freight page produces a dozen
        # rows and querying per row would multiply the work for no extra information.
        histories: dict[str, list[CommodityPrice]] = {}
        for entity_name in dict.fromkeys(price.entity_name for price in prices):
            try:
                histories[entity_name] = await self._history.price_history(entity_name, 8)
            except Exception:
                histories[entity_name] = []

        return [self._filled(price, histories.get(price.entity_name, [])) for price in prices]

    def _filled(
        self,
        price: CommodityPrice,
        history: list[CommodityPrice],
    ) -> CommodityPrice:
        """Add whichever changes are missing from one price.

        Args:
            price: The freshly collected price.
            history: Earlier readings for the same entity.

        Returns:
            The price, with changes added where possible.
        """
        daily = price.pct_change_1d
        if daily is None:
            daily = self._change_over(price, history, _DAY)

        weekly = price.pct_change_7d
        if weekly is None:
            weekly = self._change_over(price, history, _WEEK)

        if daily == price.pct_change_1d and weekly == price.pct_change_7d:
            return price
        return price.model_copy(update={"pct_change_1d": daily, "pct_change_7d": weekly})

    def _change_over(
        self,
        price: CommodityPrice,
        history: list[CommodityPrice],
        span: timedelta,
    ) -> Decimal | None:
        """Compare a price with the nearest reading roughly one span ago.

        Args:
            price: The current reading.
            history: Earlier readings for the same entity.
            span: How far back to compare against.

        Returns:
            The percentage change, or None when no reading sits close enough to that age, or
            when the earlier price was zero and a percentage would be meaningless.
        """
        target = price.recorded_at - span
        candidates = [
            row
            for row in history
            if row.recorded_at < price.recorded_at and abs(row.recorded_at - target) <= _TOLERANCE
        ]
        if not candidates:
            return None

        previous = min(candidates, key=lambda row: abs(row.recorded_at - target))
        if previous.price == 0:
            return None

        change = (price.price - previous.price) / previous.price * Decimal(100)
        return change.quantize(_PLACES)
