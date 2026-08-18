"""Tests for the grounded copilot and the anomaly reviewer."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from shadow_cpi.ai.anomaly import AnomalyReviewer
from shadow_cpi.ai.copilot import GroundedCopilot
from shadow_cpi.ai.gemini import GeminiError, GeminiQuotaExceededError
from shadow_cpi.db.neo4j.repository import RippleLink
from shadow_cpi.shared import (
    CommodityPrice,
    IngestionMethod,
    InstitutionalHolding,
    Sector,
)

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def _price(entity_name: str = "Copper", price: str = "4.52", days_ago: int = 0) -> CommodityPrice:
    return CommodityPrice(
        entity_name=entity_name,
        sector=Sector.METALS,
        price=Decimal(price),
        currency="USD",
        unit="lb",
        recorded_at=NOW - timedelta(days=days_ago),
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
        market_value_usd=Decimal("144000000.00"),
        pct_portfolio=Decimal("7.02"),
        shares_change_qoq=150_000,
        quarter_end=date(2026, 6, 30),
        source_url="https://www.sec.gov/edgar/browse/?CIK=0001350694",
    )


class ScriptedModel:
    def __init__(self, replies: list[str] | None = None, error: Exception | None = None) -> None:
        self.replies = list(replies or [])
        self.error = error
        self.text_calls: list[tuple[str, str]] = []
        self.model_calls: list[tuple[str, str]] = []

    async def generate_text(
        self, system_instruction: str, user_prompt: str, temperature: float = 0.0
    ) -> str:
        self.text_calls.append((system_instruction, user_prompt))
        if self.error is not None:
            raise self.error
        return self.replies.pop(0) if self.replies else ""

    async def generate_model(
        self,
        system_instruction: str,
        user_prompt: str,
        schema: type,
        temperature: float = 0.0,
    ) -> object:
        self.model_calls.append((system_instruction, user_prompt))
        if self.error is not None:
            raise self.error
        import json

        return schema.model_validate(json.loads(self.replies.pop(0)))


class FakePriceReader:
    def __init__(
        self,
        latest: CommodityPrice | None = None,
        history: list[CommodityPrice] | None = None,
        by_sector: dict[Sector, list[CommodityPrice]] | None = None,
    ) -> None:
        self._latest = latest
        self._history = history or []
        self._by_sector = by_sector or {}

    async def latest_price(self, entity_name: str) -> CommodityPrice | None:
        return self._latest

    async def price_history(self, entity_name: str, days: int) -> list[CommodityPrice]:
        return self._history

    async def latest_prices_by_sector(self, sector: Sector) -> list[CommodityPrice]:
        return self._by_sector.get(sector, [])


class FakeHoldingsReader:
    def __init__(self, holdings: list[InstitutionalHolding] | None = None) -> None:
        self._holdings = holdings or []

    async def holders_of(self, ticker: str, quarter_end: date | None = None):
        return self._holdings

    async def holdings_of_filer(self, filer_cik: str, quarter_end: date | None = None):
        return self._holdings


class FakeGraphReader:
    def __init__(self, links: list[RippleLink] | None = None) -> None:
        self._links = links or []

    async def ripple_effect(self, commodity: str, max_depth: int = 2) -> list[RippleLink]:
        return self._links

    async def filers_exposed_to(self, commodity: str) -> list[dict[str, object]]:
        return []


def _copilot(
    model: ScriptedModel,
    prices: FakePriceReader | None = None,
    holdings: FakeHoldingsReader | None = None,
    graph: FakeGraphReader | None = None,
) -> GroundedCopilot:
    return GroundedCopilot(
        model=model,
        prices=prices,
        holdings=holdings,
        graph=graph,
    )


class TestGrounding:
    @pytest.mark.asyncio
    async def test_answers_using_the_retrieved_data(self) -> None:
        model = ScriptedModel(["Copper is 4.52 USD per pound [investing.com]."])
        copilot = _copilot(
            model,
            prices=FakePriceReader(
                by_sector={Sector.METALS: [_price()]}, latest=_price(), history=[_price()]
            ),
        )

        answer = await copilot.ask("what is copper doing")

        assert "4.52" in answer.answer
        assert answer.sources

    @pytest.mark.asyncio
    async def test_the_retrieved_prices_are_put_in_the_prompt(self) -> None:
        """The model must answer from supplied data, so the data has to be there."""
        model = ScriptedModel(["Copper is up."])
        copilot = _copilot(
            model, prices=FakePriceReader(by_sector={Sector.METALS: [_price()]}, latest=_price())
        )

        await copilot.ask("what is copper doing")

        prompt = model.text_calls[0][1]
        assert "Copper" in prompt
        assert "4.52" in prompt
        assert "investing.com" in prompt

    @pytest.mark.asyncio
    async def test_holdings_are_included_when_a_ticker_is_mentioned(self) -> None:
        model = ScriptedModel(["Bridgewater increased its position."])
        copilot = _copilot(
            model,
            prices=FakePriceReader(),
            holdings=FakeHoldingsReader([_holding()]),
        )

        await copilot.ask("who holds NVDA")

        assert "Bridgewater Associates" in model.text_calls[0][1]

    @pytest.mark.asyncio
    async def test_graph_context_is_included_when_a_commodity_is_mentioned(self) -> None:
        model = ScriptedModel(["Copper feeds electric vehicles."])
        copilot = _copilot(
            model,
            prices=FakePriceReader(by_sector={Sector.METALS: [_price()]}),
            graph=FakeGraphReader(
                [RippleLink("Copper", "REQUIRED_FOR", "EV Battery Manufacturing", "Industry", 0.18)]
            ),
        )

        await copilot.ask("what does copper affect")

        assert "EV Battery Manufacturing" in model.text_calls[0][1]

    @pytest.mark.asyncio
    async def test_sources_are_returned_alongside_the_answer(self) -> None:
        model = ScriptedModel(["Copper is 4.52 USD per pound."])
        copilot = _copilot(
            model, prices=FakePriceReader(by_sector={Sector.METALS: [_price()]}, latest=_price())
        )

        answer = await copilot.ask("what is copper doing")

        assert "https://www.investing.com/commodities/copper" in answer.sources

    @pytest.mark.asyncio
    async def test_the_answer_reports_how_fresh_its_evidence_was(self) -> None:
        model = ScriptedModel(["Copper is 4.52 USD per pound."])
        copilot = _copilot(
            model,
            prices=FakePriceReader(by_sector={Sector.METALS: [_price(days_ago=3)]}),
        )

        answer = await copilot.ask("what is copper doing")

        assert answer.data_as_of is not None


class TestRefusals:
    @pytest.mark.asyncio
    async def test_a_question_with_no_data_behind_it_says_so(self) -> None:
        """Better a plain "no data" than a fluent answer from nowhere."""
        model = ScriptedModel(["never used"])
        copilot = _copilot(model, prices=FakePriceReader())

        answer = await copilot.ask("what is the price of unobtainium")

        assert answer.answer.startswith("I do not have")
        assert answer.sources == []
        assert model.text_calls == []

    @pytest.mark.asyncio
    async def test_an_empty_question_is_refused(self) -> None:
        copilot = _copilot(ScriptedModel(), prices=FakePriceReader())

        with pytest.raises(ValueError, match="question"):
            await copilot.ask("   ")

    @pytest.mark.asyncio
    async def test_an_overlong_question_is_refused(self) -> None:
        copilot = _copilot(ScriptedModel(), prices=FakePriceReader())

        with pytest.raises(ValueError, match="question"):
            await copilot.ask("why " * 2000)

    @pytest.mark.asyncio
    async def test_a_model_failure_is_reported_rather_than_faked(self) -> None:
        model = ScriptedModel(error=GeminiError("model unavailable"))
        copilot = _copilot(
            model, prices=FakePriceReader(by_sector={Sector.METALS: [_price()]}, latest=_price())
        )

        with pytest.raises(GeminiError):
            await copilot.ask("what is copper doing")

    @pytest.mark.asyncio
    async def test_reaching_the_daily_cap_is_reported_clearly(self) -> None:
        model = ScriptedModel(error=GeminiQuotaExceededError("cap reached"))
        copilot = _copilot(
            model, prices=FakePriceReader(by_sector={Sector.METALS: [_price()]}, latest=_price())
        )

        with pytest.raises(GeminiQuotaExceededError):
            await copilot.ask("what is copper doing")


class TestAnomalyReviewer:
    @pytest.mark.asyncio
    async def test_flags_an_unusual_move(self) -> None:
        model = ScriptedModel(
            ['{"is_anomaly": true, "severity": "high", "explanation": "a 40 percent jump"}']
        )
        history = [_price(price="4.00", days_ago=2), _price(price="5.60", days_ago=0)]

        finding = await AnomalyReviewer(model).review("Copper", history)

        assert finding is not None
        assert finding.is_anomaly is True
        assert finding.severity == "high"

    @pytest.mark.asyncio
    async def test_a_normal_series_is_not_flagged(self) -> None:
        model = ScriptedModel(
            ['{"is_anomaly": false, "severity": "low", "explanation": "within the usual range"}']
        )
        history = [_price(price="4.50", days_ago=2), _price(price="4.52", days_ago=0)]

        finding = await AnomalyReviewer(model).review("Copper", history)

        assert finding is not None
        assert finding.is_anomaly is False

    @pytest.mark.asyncio
    async def test_the_series_is_given_to_the_model(self) -> None:
        model = ScriptedModel(['{"is_anomaly": false, "severity": "low", "explanation": "steady"}'])
        history = [_price(price="4.50", days_ago=1), _price(price="4.52", days_ago=0)]

        await AnomalyReviewer(model).review("Copper", history)

        prompt = model.model_calls[0][1]
        assert "4.50" in prompt
        assert "4.52" in prompt

    @pytest.mark.asyncio
    async def test_a_series_too_short_to_judge_is_skipped(self) -> None:
        model = ScriptedModel(["never used"])

        finding = await AnomalyReviewer(model).review("Copper", [_price()])

        assert finding is None
        assert model.model_calls == []

    @pytest.mark.asyncio
    async def test_a_model_failure_yields_no_finding(self) -> None:
        model = ScriptedModel(error=GeminiError("model unavailable"))
        history = [_price(price="4.50", days_ago=1), _price(price="4.52", days_ago=0)]

        assert await AnomalyReviewer(model).review("Copper", history) is None

    @pytest.mark.asyncio
    async def test_an_unrecognised_severity_is_rejected(self) -> None:
        model = ScriptedModel(
            ['{"is_anomaly": true, "severity": "catastrophic", "explanation": "big"}']
        )
        history = [_price(price="4.50", days_ago=1), _price(price="9.00", days_ago=0)]

        assert await AnomalyReviewer(model).review("Copper", history) is None
