"""Answering free-form questions from stored data.

A model asked "what is copper doing" will answer confidently from whatever it
absorbed during training, which may be years old and may be wrong. That is the
failure this module exists to prevent.

So the question is never sent alone. The relevant rows are retrieved first, the
model is given only those, and it is instructed to answer from them and cite them.
If nothing relevant was found, the model is not called at all and the answer says
there is no data. A plain "I do not have that" is more useful than a fluent
sentence with an invented number in it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from shadow_cpi.ai.prompts import COPILOT_SYSTEM, COPILOT_USER
from shadow_cpi.ai.protocols import TextModel
from shadow_cpi.db.protocols import HoldingsReader, PriceReader
from shadow_cpi.shared import CommodityPrice, InstitutionalHolding, Sector

MAX_QUESTION_LENGTH = 500

# Words shorter than this match too much to be evidence that a question refers to a
# particular entity: "us" would match half the catalogue.
_MIN_MATCH_WORD_LENGTH = 2

# How much history to retrieve per mentioned entity.
_TREND_DAYS = 30

# Tickers are written in capitals, which is what makes them findable in a question
# without a dictionary of every symbol in existence.
_TICKER_PATTERN = re.compile(r"\b[A-Z]{2,5}\b")

# Words that look like tickers but are ordinary English in a finance question.
_TICKER_STOPWORDS = frozenset(
    {"CPI", "USD", "EUR", "GBP", "AND", "THE", "FOR", "WHAT", "WHO", "HOW", "WHY", "SEC", "API"}
)

_NO_DATA_ANSWER = (
    "I do not have data covering that question yet. "
    "Nothing in the collected prices, supply-chain relationships, or filings matches it."
)


@dataclass(frozen=True, slots=True)
class CopilotAnswer:
    """An answer and the evidence behind it.

    Attributes:
        answer: The reply, in plain language.
        sources: URLs of the rows the answer was based on, so any claim can be
            checked at its origin.
        data_as_of: Timestamp of the newest piece of evidence used, or None when no
            price data was involved.
    """

    answer: str
    sources: list[str] = field(default_factory=list)
    data_as_of: datetime | None = None


class GroundedCopilot:
    """Answers questions using retrieved rows, never from the model's memory."""

    def __init__(
        self,
        model: TextModel,
        prices: PriceReader | None = None,
        holdings: HoldingsReader | None = None,
        neo4j_driver: object | None = None,
    ) -> None:
        """Create the copilot.

        Args:
            model: The model to ask.
            prices: Price store to retrieve from, if configured.
            holdings: Holdings store to retrieve from, if configured.
            neo4j_driver: Neo4j async driver. A fresh session is opened per ask()
                call so this never shares a socket with an HTTP request handler.
        """
        self._model = model
        self._prices = prices
        self._holdings = holdings
        self._neo4j_driver = neo4j_driver

    async def ask(self, question: str) -> CopilotAnswer:
        """Answer a question from stored data.

        Args:
            question: The question, in plain language.

        Returns:
            The answer with its sources. When nothing relevant is stored, the answer
            says so and the model is not called.

        Raises:
            ValueError: If the question is empty or unreasonably long.
            GeminiError: If the model call fails, including when the daily cap is
                reached. Reporting that is better than answering without evidence.
        """
        cleaned = question.strip()
        if not cleaned or len(cleaned) > MAX_QUESTION_LENGTH:
            raise ValueError(f"A question must be between 1 and {MAX_QUESTION_LENGTH} characters")

        prices = await self._retrieve_prices(cleaned)
        holdings = await self._retrieve_holdings(cleaned)
        relationships = await self._retrieve_relationships(prices)

        if not prices and not holdings and not relationships:
            return CopilotAnswer(answer=_NO_DATA_ANSWER)

        prompt = COPILOT_USER.format(
            question=cleaned,
            price_rows=_describe_prices(prices),
            graph_rows="\n".join(relationships) or "none found",
            holdings_rows=_describe_holdings(holdings),
        )
        answer = await self._model.generate_text(COPILOT_SYSTEM, prompt)

        sources = sorted(
            {price.source_url for price in prices}
            | {holding.source_url for holding in holdings if holding.source_url}
        )
        newest = max((price.recorded_at for price in prices), default=None)
        return CopilotAnswer(answer=answer.strip(), sources=sources, data_as_of=newest)

    async def _retrieve_prices(self, question: str) -> list[CommodityPrice]:
        """Find price rows relevant to a question.

        Every tracked entity's latest price is fetched, then narrowed to those the question
        names. A question that names nothing keeps them all: "what moved most this week" is
        an ordinary question, and answering it with "no data" because no entity was spelled
        out would be a refusal on a technicality.

        Args:
            question: The question being answered.

        Returns:
            Matching prices, oldest first.
        """
        if self._prices is None:
            return []

        latest: list[CommodityPrice] = []
        for sector in Sector:
            latest.extend(await self._prices.latest_prices_by_sector(sector))
        if not latest:
            return []

        lowered = question.lower()
        matched = [price for price in latest if _mentions(lowered, price.entity_name)]
        if not matched:
            # A general question about the market. Everything tracked is the evidence.
            return sorted(latest, key=lambda price: price.recorded_at)

        # A trend is more useful than a single number, so the history of the first
        # match is included as well.
        history = await self._prices.price_history(matched[0].entity_name, _TREND_DAYS)
        combined = {(price.entity_name, price.recorded_at): price for price in [*matched, *history]}
        return sorted(combined.values(), key=lambda price: price.recorded_at)

    async def _retrieve_holdings(self, question: str) -> list[InstitutionalHolding]:
        """Find holdings relevant to a question.

        Args:
            question: The question being answered.

        Returns:
            Holdings for any ticker mentioned in the question.
        """
        if self._holdings is None:
            return []

        tickers = {
            candidate
            for candidate in _TICKER_PATTERN.findall(question)
            if candidate not in _TICKER_STOPWORDS
        }
        rows: list[InstitutionalHolding] = []
        for ticker in sorted(tickers):
            rows.extend(await self._holdings.holders_of(ticker))
        return rows

    async def _retrieve_relationships(self, prices: list[CommodityPrice]) -> list[str]:
        """Find supply-chain context for the commodities in play.

        Args:
            prices: Prices already retrieved, which name the commodities to look up.

        Returns:
            One line per relationship found.
        """
        if self._neo4j_driver is None or not prices:
            return []

        from neo4j import AsyncDriver

        from shadow_cpi.db.neo4j.repository import Neo4jSupplyChainRepository
        from shadow_cpi.db.neo4j.session import Neo4jSessionAdapter

        commodity = prices[-1].entity_name
        driver: AsyncDriver = self._neo4j_driver  # type: ignore[assignment]
        async with driver.session() as session:
            graph = Neo4jSupplyChainRepository(Neo4jSessionAdapter(session))
            links = await graph.ripple_effect(commodity)
        return [f"{link.source} {link.relationship} {link.target}" for link in links]


def _mentions(lowered_question: str, entity_name: str) -> bool:
    """Whether a question refers to a tracked entity.

    Stored names such as ``WTI_Crude`` are written for a database, not typed by a
    person, so the parts are matched individually.

    Args:
        lowered_question: The question in lower case.
        entity_name: Entity name as stored.

    Returns:
        True when the question appears to refer to the entity.
    """
    words = [
        part
        for part in entity_name.lower().replace("_", " ").split()
        if len(part) > _MIN_MATCH_WORD_LENGTH
    ]
    return any(word in lowered_question for word in words)


def _describe_prices(prices: list[CommodityPrice]) -> str:
    """Render price rows for the prompt.

    Args:
        prices: Prices to describe.

    Returns:
        One line per price, including its source so the model can cite it.
    """
    if not prices:
        return "none found"
    return "\n".join(
        f"- {price.entity_name} ({price.sector.value}): {price.price} {price.currency} per "
        f"{price.unit} at {price.recorded_at:%Y-%m-%d %H:%M} UTC "
        f"(change 1 day: {_percent_or_unknown(price.pct_change_1d)}, "
        f"change 7 days: {_percent_or_unknown(price.pct_change_7d)}) "
        f"[source: {price.source_name} {price.source_url}]"
        for price in prices
    )


def _percent_or_unknown(value: Decimal | None) -> str:
    """Render a percentage change, or say plainly that none was reported.

    A bare ``None`` in the evidence invites the model to treat it as zero, which would turn
    "we do not know" into "it did not move".

    Args:
        value: The change, or None when the source did not publish one.

    Returns:
        The value with a percent sign, or ``not reported``.
    """
    return "not reported" if value is None else f"{value}%"


def _describe_holdings(holdings: list[InstitutionalHolding]) -> str:
    """Render holdings for the prompt.

    Args:
        holdings: Holdings to describe.

    Returns:
        One line per holding, including its filing so the model can cite it.
    """
    if not holdings:
        return "none found"
    return "\n".join(
        f"- {holding.filer_name} held {holding.shares_held} shares of "
        f"{holding.stock_ticker} at {holding.quarter_end} "
        f"(change since prior quarter: {holding.shares_change_qoq}) "
        f"[source: {holding.source_url}]"
        for holding in holdings
    )
