"""Contract tests for the MCP tools that AI agents and IDEs call."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from shadow_cpi.api.dependencies import ApiDependencies
from shadow_cpi.db.neo4j.repository import RippleLink
from shadow_cpi.mcp_server.server import TOOL_NAMES, build_server
from shadow_cpi.shared import (
    CommodityPrice,
    IngestionMethod,
    InstitutionalHolding,
    Sector,
)

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def _price(price: str = "4.52", recorded_at: datetime = NOW) -> CommodityPrice:
    return CommodityPrice(
        entity_name="Copper",
        sector=Sector.METALS,
        price=Decimal(price),
        currency="USD",
        unit="lb",
        recorded_at=recorded_at,
        source_name="investing.com",
        source_url="https://www.investing.com/commodities/copper",
        ingestion_method=IngestionMethod.BRIGHTDATA_SCRAPE,
    )


def _holding(
    filer_name: str = "Bridgewater Associates", change: int | None = 150_000
) -> InstitutionalHolding:
    return InstitutionalHolding(
        filer_name=filer_name,
        filer_cik="0001350694",
        stock_ticker="NVDA",
        shares_held=1_200_000,
        market_value_usd=Decimal("144000000.00"),
        pct_portfolio=Decimal("7.02"),
        shares_change_qoq=change,
        quarter_end=date(2026, 6, 30),
        source_url="https://www.sec.gov/edgar/browse/?CIK=0001350694",
    )


class FakePriceReader:
    def __init__(
        self,
        latest: CommodityPrice | None = None,
        history: list[CommodityPrice] | None = None,
    ) -> None:
        self._latest = latest
        self._history = history or []

    async def latest_price(self, entity_name: str) -> CommodityPrice | None:
        return self._latest

    async def price_history(self, entity_name: str, days: int) -> list[CommodityPrice]:
        return self._history

    async def latest_prices_by_sector(self, sector: Sector) -> list[CommodityPrice]:
        return []


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
        self.calls: list[tuple[str, int]] = []

    async def ripple_effect(self, commodity: str, max_depth: int = 2) -> list[RippleLink]:
        self.calls.append((commodity, max_depth))
        return self._links

    async def filers_exposed_to(self, commodity: str) -> list[dict[str, object]]:
        return []


async def _call(
    dependencies: ApiDependencies, tool: str, arguments: dict[str, object]
) -> dict[str, object]:
    """Call a tool the way a connected agent would, and return its structured result."""
    server = build_server(dependencies)
    result = await server.call_tool(tool, arguments)
    # FastMCP returns (content blocks, structured payload).
    return result[1] if isinstance(result, tuple) else result


class TestToolCatalogue:
    @pytest.mark.asyncio
    async def test_the_documented_tools_are_offered(self) -> None:
        server = build_server(ApiDependencies())

        listed = {tool.name for tool in await server.list_tools()}

        assert listed == set(TOOL_NAMES)

    @pytest.mark.asyncio
    async def test_every_tool_describes_what_it_returns(self) -> None:
        """An agent relies on the declared schema to use a tool correctly."""
        server = build_server(ApiDependencies())

        for tool in await server.list_tools():
            assert tool.description
            assert tool.inputSchema
            assert tool.outputSchema is not None


class TestPriceTrendTool:
    @pytest.mark.asyncio
    async def test_returns_the_latest_price_and_trend(self) -> None:
        history = [_price("4.00"), _price("4.52")]
        dependencies = ApiDependencies(prices=FakePriceReader(latest=history[-1], history=history))

        payload = await _call(dependencies, "get_commodity_price_trend", {"commodity": "Copper"})

        assert payload["price"] == 4.52
        assert payload["currency"] == "USD"
        assert payload["trend_pct"] == 13.0

    @pytest.mark.asyncio
    async def test_the_answer_carries_its_source(self) -> None:
        history = [_price()]
        dependencies = ApiDependencies(prices=FakePriceReader(latest=history[0], history=history))

        payload = await _call(dependencies, "get_commodity_price_trend", {"commodity": "Copper"})

        assert payload["source_url"].startswith("https://")
        assert payload["source_name"] == "investing.com"

    @pytest.mark.asyncio
    async def test_an_untracked_commodity_says_so_plainly(self) -> None:
        """Agents cope with a clear "not found" far better than with an exception."""
        dependencies = ApiDependencies(prices=FakePriceReader())

        payload = await _call(
            dependencies, "get_commodity_price_trend", {"commodity": "Unobtainium"}
        )

        assert payload["found"] is False
        assert "Unobtainium" in payload["message"]

    @pytest.mark.asyncio
    async def test_an_unconfigured_store_is_reported_not_hidden(self) -> None:
        payload = await _call(
            ApiDependencies(), "get_commodity_price_trend", {"commodity": "Copper"}
        )

        assert payload["found"] is False
        assert "not available" in payload["message"]


class TestSupplyChainTool:
    @pytest.mark.asyncio
    async def test_returns_the_industries_a_commodity_feeds_into(self) -> None:
        dependencies = ApiDependencies(
            graph=FakeGraphReader(
                [
                    RippleLink("Copper", "REFINED_INTO", "Stator Coil", "Component", None),
                    RippleLink(
                        "Stator Coil",
                        "REQUIRED_FOR",
                        "EV Battery Manufacturing",
                        "Industry",
                        0.18,
                    ),
                ]
            )
        )

        payload = await _call(dependencies, "analyze_supply_chain_impact", {"commodity": "Copper"})

        assert payload["industries"] == ["EV Battery Manufacturing"]
        assert payload["components"] == ["Stator Coil"]

    @pytest.mark.asyncio
    async def test_a_commodity_with_nothing_mapped_returns_empty_lists(self) -> None:
        dependencies = ApiDependencies(graph=FakeGraphReader())

        payload = await _call(
            dependencies, "analyze_supply_chain_impact", {"commodity": "Unobtainium"}
        )

        assert payload["industries"] == []
        assert payload["found"] is False

    @pytest.mark.asyncio
    async def test_the_traversal_depth_is_bounded(self) -> None:
        graph = FakeGraphReader()
        dependencies = ApiDependencies(graph=graph)

        await _call(
            dependencies,
            "analyze_supply_chain_impact",
            {"commodity": "Copper", "max_depth": 99},
        )

        assert graph.calls[0][1] <= 5


class TestInstitutionalHoldersTool:
    @pytest.mark.asyncio
    async def test_returns_the_funds_holding_a_stock(self) -> None:
        dependencies = ApiDependencies(holdings=FakeHoldingsReader([_holding()]))

        payload = await _call(dependencies, "get_institutional_holders", {"ticker": "NVDA"})

        holder = payload["holders"][0]
        assert holder["filer"] == "Bridgewater Associates"
        assert holder["delta_pct"] == 14.286
        assert holder["shares_held"] == 1_200_000

    @pytest.mark.asyncio
    async def test_a_new_position_reports_no_change_rather_than_zero(self) -> None:
        dependencies = ApiDependencies(holdings=FakeHoldingsReader([_holding(change=None)]))

        payload = await _call(dependencies, "get_institutional_holders", {"ticker": "NVDA"})

        assert payload["holders"][0]["delta_pct"] is None

    @pytest.mark.asyncio
    async def test_a_stock_nobody_reported_returns_an_empty_list(self) -> None:
        dependencies = ApiDependencies(holdings=FakeHoldingsReader())

        payload = await _call(dependencies, "get_institutional_holders", {"ticker": "NVDA"})

        assert payload["holders"] == []
        assert payload["found"] is False


class TestPipelineHealthTool:
    @pytest.mark.asyncio
    async def test_reports_how_fresh_the_data_is(self) -> None:
        dependencies = ApiDependencies(prices=FakePriceReader(latest=_price()))

        payload = await _call(dependencies, "check_data_freshness", {"commodity": "Copper"})

        assert payload["found"] is True
        assert payload["recorded_at"].startswith("2026-08-15")
        assert isinstance(payload["is_stale"], bool)

    @pytest.mark.asyncio
    async def test_an_untracked_commodity_says_so(self) -> None:
        dependencies = ApiDependencies(prices=FakePriceReader())

        payload = await _call(dependencies, "check_data_freshness", {"commodity": "Nope"})

        assert payload["found"] is False


class TestCopilotTool:
    @pytest.mark.asyncio
    async def test_returns_a_grounded_answer_with_its_sources(self) -> None:
        from shadow_cpi.ai.copilot import CopilotAnswer

        class FakeCopilot:
            async def ask(self, question: str) -> CopilotAnswer:
                return CopilotAnswer(
                    answer="Copper is 4.52 USD per pound.",
                    sources=["https://www.investing.com/commodities/copper"],
                    data_as_of=NOW,
                )

        payload = await _call(
            ApiDependencies(copilot=FakeCopilot()),
            "ask_shadow_cpi_copilot",
            {"question": "what is copper doing"},
        )

        assert payload["found"] is True
        assert "4.52" in payload["answer"]
        assert payload["sources"] == ["https://www.investing.com/commodities/copper"]

    @pytest.mark.asyncio
    async def test_a_missing_copilot_is_reported_in_the_payload(self) -> None:
        """An agent can relay a reason; it cannot relay an exception."""
        payload = await _call(
            ApiDependencies(), "ask_shadow_cpi_copilot", {"question": "what is copper doing"}
        )

        assert payload["found"] is False
        assert "not available" in payload["answer"]

    @pytest.mark.asyncio
    async def test_a_model_failure_is_reported_in_the_payload(self) -> None:
        from shadow_cpi.ai.gemini import GeminiQuotaExceededError

        class FailingCopilot:
            async def ask(self, question: str) -> object:
                raise GeminiQuotaExceededError("daily cap reached")

        payload = await _call(
            ApiDependencies(copilot=FailingCopilot()),
            "ask_shadow_cpi_copilot",
            {"question": "what is copper doing"},
        )

        assert payload["found"] is False
        assert "cap" in payload["answer"]
