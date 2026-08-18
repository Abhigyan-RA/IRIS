"""Contract tests for the institutional holdings and supply-chain graph endpoints."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from shadow_cpi.api.app import create_app
from shadow_cpi.api.dependencies import ApiDependencies
from shadow_cpi.config import build_settings
from shadow_cpi.db.neo4j.repository import RippleLink
from shadow_cpi.shared import InstitutionalHolding

SETTINGS = build_settings(
    {
        "GEMINI_API_KEY": "test-gemini-key",
        "BRIGHTDATA_API_KEY": "test-brightdata-key",
        "NEO4J_PASSWORD": "test-neo4j-password",
        "CRON_SECRET": "test-cron-secret",
    }
)


def _holding(
    ticker: str = "NVDA",
    filer_name: str = "Bridgewater Associates",
    shares: int = 1_200_000,
    change: int | None = 150_000,
    value: str = "144000000.00",
) -> InstitutionalHolding:
    return InstitutionalHolding(
        filer_name=filer_name,
        filer_cik="0001350694",
        stock_ticker=ticker,
        shares_held=shares,
        market_value_usd=Decimal(value),
        pct_portfolio=Decimal("7.02"),
        shares_change_qoq=change,
        quarter_end=date(2026, 6, 30),
        source_url="https://www.sec.gov/edgar/browse/?CIK=0001350694",
    )


class FakeHoldingsReader:
    """Serves canned holdings and records how it was queried."""

    def __init__(self, holdings: list[InstitutionalHolding] | None = None) -> None:
        self._holdings = holdings or []
        self.holder_calls: list[tuple[str, date | None]] = []
        self.filer_calls: list[tuple[str, date | None]] = []

    async def holders_of(
        self, ticker: str, quarter_end: date | None = None
    ) -> list[InstitutionalHolding]:
        self.holder_calls.append((ticker, quarter_end))
        return self._holdings

    async def holdings_of_filer(
        self, filer_cik: str, quarter_end: date | None = None
    ) -> list[InstitutionalHolding]:
        self.filer_calls.append((filer_cik, quarter_end))
        return self._holdings


class FakeGraphReader:
    """Serves canned traversal results."""

    def __init__(
        self,
        links: list[RippleLink] | None = None,
        exposure: list[dict[str, object]] | None = None,
    ) -> None:
        self._links = links or []
        self._exposure = exposure or []
        self.ripple_calls: list[tuple[str, int]] = []

    async def ripple_effect(self, commodity: str, max_depth: int = 2) -> list[RippleLink]:
        self.ripple_calls.append((commodity, max_depth))
        return self._links

    async def filers_exposed_to(self, commodity: str) -> list[dict[str, object]]:
        return self._exposure


def _client(
    holdings: FakeHoldingsReader | None = None,
    graph: FakeGraphReader | None = None,
) -> TestClient:
    app = create_app(
        SETTINGS,
        dependencies=ApiDependencies(holdings=holdings, graph=graph),
    )
    return TestClient(app)


class TestHoldersOfStock:
    def test_returns_the_funds_holding_a_stock(self) -> None:
        client = _client(holdings=FakeHoldingsReader([_holding()]))

        body = client.get("/api/institutional/holders/NVDA").json()

        assert body["ticker"] == "NVDA"
        assert body["holders"][0]["filer_name"] == "Bridgewater Associates"
        assert body["holders"][0]["shares_held"] == 1_200_000

    def test_quarter_over_quarter_change_is_reported_in_shares_and_percent(self) -> None:
        client = _client(holdings=FakeHoldingsReader([_holding(shares=1_200_000, change=150_000)]))

        holder = client.get("/api/institutional/holders/NVDA").json()["holders"][0]

        assert holder["shares_change_qoq"] == 150_000
        assert holder["delta_pct"] == "14.286"

    def test_a_reduced_position_reports_a_negative_change(self) -> None:
        client = _client(holdings=FakeHoldingsReader([_holding(shares=800_000, change=-200_000)]))

        holder = client.get("/api/institutional/holders/NVDA").json()["holders"][0]

        assert holder["delta_pct"] == "-20.000"

    def test_a_brand_new_position_has_no_percentage_change(self) -> None:
        """There is nothing to compare against, so the field is empty rather than zero."""
        client = _client(holdings=FakeHoldingsReader([_holding(change=None)]))

        holder = client.get("/api/institutional/holders/NVDA").json()["holders"][0]

        assert holder["shares_change_qoq"] is None
        assert holder["delta_pct"] is None

    def test_a_lowercase_ticker_is_accepted(self) -> None:
        holdings = FakeHoldingsReader([_holding()])
        client = _client(holdings=holdings)

        response = client.get("/api/institutional/holders/nvda")

        assert response.status_code == 200
        assert holdings.holder_calls[0][0] == "nvda"

    def test_a_stock_nobody_reported_returns_an_empty_list_not_an_error(self) -> None:
        response = _client(holdings=FakeHoldingsReader()).get("/api/institutional/holders/NVDA")

        assert response.status_code == 200
        assert response.json()["holders"] == []

    def test_holders_can_be_narrowed_to_one_quarter(self) -> None:
        holdings = FakeHoldingsReader([_holding()])
        client = _client(holdings=holdings)

        client.get("/api/institutional/holders/NVDA", params={"quarter_end": "2026-06-30"})

        assert holdings.holder_calls[0][1] == date(2026, 6, 30)

    def test_an_unparseable_quarter_is_refused(self) -> None:
        client = _client(holdings=FakeHoldingsReader([_holding()]))

        response = client.get(
            "/api/institutional/holders/NVDA", params={"quarter_end": "last quarter"}
        )

        assert response.status_code == 422

    def test_an_absurd_ticker_is_refused_before_reaching_the_database(self) -> None:
        holdings = FakeHoldingsReader()
        client = _client(holdings=holdings)

        response = client.get(f"/api/institutional/holders/{'A' * 40}")

        assert response.status_code == 422
        assert holdings.holder_calls == []


class TestFilerHoldings:
    def test_returns_one_funds_positions(self) -> None:
        client = _client(holdings=FakeHoldingsReader([_holding(), _holding("AAPL")]))

        body = client.get("/api/institutional/filer/0001350694/holdings").json()

        assert body["filer_cik"] == "0001350694"
        assert {holding["stock_ticker"] for holding in body["holdings"]} == {"NVDA", "AAPL"}

    def test_the_fund_name_comes_from_the_filings(self) -> None:
        client = _client(holdings=FakeHoldingsReader([_holding()]))

        body = client.get("/api/institutional/filer/0001350694/holdings").json()

        assert body["filer_name"] == "Bridgewater Associates"

    def test_an_unpadded_identifier_is_accepted(self) -> None:
        """Filer identifiers are written several ways; all of them mean one fund."""
        holdings = FakeHoldingsReader([_holding()])
        client = _client(holdings=holdings)

        response = client.get("/api/institutional/filer/1350694/holdings")

        assert response.status_code == 200
        assert holdings.filer_calls[0][0] == "1350694"

    def test_an_identifier_that_is_not_a_number_is_refused(self) -> None:
        holdings = FakeHoldingsReader()
        client = _client(holdings=holdings)

        response = client.get("/api/institutional/filer/not-a-cik/holdings")

        assert response.status_code == 422
        assert holdings.filer_calls == []

    def test_a_fund_with_no_filings_returns_an_empty_list(self) -> None:
        response = _client(holdings=FakeHoldingsReader()).get(
            "/api/institutional/filer/0001350694/holdings"
        )

        assert response.status_code == 200
        assert response.json()["holdings"] == []
        assert response.json()["filer_name"] is None


class TestRippleEffect:
    def test_returns_the_chain_downstream_of_a_commodity(self) -> None:
        client = _client(
            graph=FakeGraphReader(
                [
                    RippleLink("Copper", "REFINED_INTO", "Stator Coil", "Component", None),
                    RippleLink(
                        "Stator Coil", "REQUIRED_FOR", "EV Battery Manufacturing", "Industry", 0.18
                    ),
                ]
            )
        )

        body = client.get("/api/graph/ripple/Copper").json()

        assert body["commodity"] == "Copper"
        assert [link["target"] for link in body["links"]] == [
            "Stator Coil",
            "EV Battery Manufacturing",
        ]

    def test_nodes_are_listed_for_drawing_the_graph(self) -> None:
        client = _client(
            graph=FakeGraphReader(
                [RippleLink("Copper", "REFINED_INTO", "Stator Coil", "Component", None)]
            )
        )

        body = client.get("/api/graph/ripple/Copper").json()

        assert {node["name"] for node in body["nodes"]} == {"Copper", "Stator Coil"}

    def test_affected_industries_are_summarised(self) -> None:
        client = _client(
            graph=FakeGraphReader(
                [
                    RippleLink("Copper", "REFINED_INTO", "Stator Coil", "Component", None),
                    RippleLink("Copper", "IMPACTS_COST_OF", "Construction", "Industry", 0.24),
                ]
            )
        )

        body = client.get("/api/graph/ripple/Copper").json()

        assert body["affected_industries"] == ["Construction"]

    def test_the_traversal_depth_can_be_chosen(self) -> None:
        graph = FakeGraphReader()
        client = _client(graph=graph)

        client.get("/api/graph/ripple/Copper", params={"depth": 3})

        assert graph.ripple_calls == [("Copper", 3)]

    def test_an_excessive_depth_is_refused(self) -> None:
        graph = FakeGraphReader()
        client = _client(graph=graph)

        response = client.get("/api/graph/ripple/Copper", params={"depth": 99})

        assert response.status_code == 422
        assert graph.ripple_calls == []

    def test_a_commodity_with_nothing_downstream_returns_an_empty_graph(self) -> None:
        response = _client(graph=FakeGraphReader()).get("/api/graph/ripple/Unobtainium")

        assert response.status_code == 200
        assert response.json()["links"] == []
        assert response.json()["explanation"] is None

    def test_funds_exposed_to_the_commodity_are_included(self) -> None:
        client = _client(
            graph=FakeGraphReader(
                exposure=[
                    {
                        "filer": "Bridgewater Associates",
                        "cik": "0001350694",
                        "ticker": "NVDA",
                    }
                ]
            )
        )

        body = client.get("/api/graph/ripple/Copper").json()

        assert body["exposed_filers"][0]["filer"] == "Bridgewater Associates"


class TestUnconfiguredStores:
    def test_holdings_endpoint_reports_unavailability_rather_than_failing(self) -> None:
        response = _client().get("/api/institutional/holders/NVDA")

        assert response.status_code == 503
        assert "holdings" in response.json()["detail"].lower()

    def test_graph_endpoint_reports_unavailability_rather_than_failing(self) -> None:
        response = _client().get("/api/graph/ripple/Copper")

        assert response.status_code == 503
        assert "graph" in response.json()["detail"].lower()
